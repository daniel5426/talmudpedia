from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REVISION = "d4e5f6a7b8c9"
PREVIOUS_REVISION = "c3d4e5f6a7b8"
ENUM_TYPES = {
    "resourcepolicyprincipaltype",
    "resourcepolicyresourcetype",
    "resourcepolicyruletype",
    "resourcepolicyquotaunit",
    "resourcepolicyquotawindow",
}
NEW_TABLES = {
    "resource_policy_sets",
    "resource_policy_set_includes",
    "resource_policy_rules",
    "resource_policy_assignments",
    "resource_policy_quota_counters",
    "resource_policy_quota_reservations",
}


def _base_database_url() -> str:
    url = (
        os.getenv("DATABASE_URL_LOCAL")
        or os.getenv("DATABASE_URL")
        or os.getenv("ALEMBIC_DATABASE_URL")
        or ""
    ).strip()
    if not url:
        pytest.skip("DATABASE_URL_LOCAL or DATABASE_URL is required for real DB migration tests.")
    return url


def _as_psycopg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _make_alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


class TempDatabase:
    def __init__(self, base_url: str):
        self._base_async_url = base_url
        self._base_sync_url = _as_psycopg_url(base_url)
        self.name = f"resource_policy_test_{uuid4().hex[:8]}"
        self.database_url = str(make_url(self._base_async_url).set(database=self.name))
        self.sync_database_url = str(make_url(self._base_sync_url).set(database=self.name))

    def __enter__(self):
        admin_url = str(make_url(self._base_sync_url).set(database="postgres"))
        self._admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with self._admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{self.name}"'))
        return self

    def __exit__(self, exc_type, exc, tb):
        self._admin_engine.dispose()
        admin_url = str(make_url(self._base_sync_url).set(database="postgres"))
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{self.name}" WITH (FORCE)'))
        admin_engine.dispose()


@pytest.mark.real_db
def test_resource_policy_migration_upgrade_and_downgrade_cover_schema_indexes_and_types():
    with TempDatabase(_base_database_url()) as temp_db:
        config = _make_alembic_config()
        previous_env = os.environ.get("ALEMBIC_DATABASE_URL")
        os.environ["ALEMBIC_DATABASE_URL"] = temp_db.database_url
        try:
            command.upgrade(config, PREVIOUS_REVISION)
            engine = create_engine(temp_db.sync_database_url)
            with engine.connect() as conn:
                conn.execute(text("CREATE TYPE resourcepolicyprincipaltype AS ENUM ('tenant_user', 'published_app_account', 'embedded_external_user')"))
                conn.commit()

            command.upgrade(config, REVISION)
            inspector = inspect(engine)
            assert NEW_TABLES.issubset(set(inspector.get_table_names()))

            published_app_columns = {column["name"] for column in inspector.get_columns("published_apps")}
            agent_columns = {column["name"] for column in inspector.get_columns("agents")}
            run_columns = {column["name"] for column in inspector.get_columns("agent_runs")}
            assert "default_policy_set_id" in published_app_columns
            assert "default_embed_policy_set_id" in agent_columns
            assert "external_user_id" in run_columns

            with engine.connect() as conn:
                index_names = {
                    row[0]
                    for row in conn.execute(
                        text(
                            """
                            SELECT indexname
                            FROM pg_indexes
                            WHERE schemaname = 'public'
                            """
                        )
                    )
                }
                enum_names = {
                    row[0]
                    for row in conn.execute(
                        text(
                            """
                            SELECT typname
                            FROM pg_type
                            WHERE typname = ANY(:names)
                            """
                        ),
                        {"names": list(ENUM_TYPES)},
                    )
                }
                assert {
                    "uq_resource_policy_assignments_tenant_user",
                    "uq_resource_policy_assignments_app_account",
                    "uq_resource_policy_assignments_embedded_user",
                    "uq_resource_policy_rules_allow_resource",
                    "uq_resource_policy_rules_quota_resource",
                }.issubset(index_names)
                assert enum_names == ENUM_TYPES

                conn.execute(text("INSERT INTO tenants (id, name, slug) VALUES (gen_random_uuid(), 'tenant', 'tenant-migration')"))
                conn.commit()

            command.downgrade(config, PREVIOUS_REVISION)
            inspector = inspect(engine)
            assert not (NEW_TABLES & set(inspector.get_table_names()))
            assert "default_policy_set_id" not in {column["name"] for column in inspector.get_columns("published_apps")}
            assert "default_embed_policy_set_id" not in {column["name"] for column in inspector.get_columns("agents")}
            assert "external_user_id" not in {column["name"] for column in inspector.get_columns("agent_runs")}

            with engine.connect() as conn:
                remaining_types = {
                    row[0]
                    for row in conn.execute(
                        text(
                            """
                            SELECT typname
                            FROM pg_type
                            WHERE typname = ANY(:names)
                            """
                        ),
                        {"names": list(ENUM_TYPES)},
                    )
                }
                assert remaining_types == set()

            command.upgrade(config, REVISION)
            inspector = inspect(engine)
            assert NEW_TABLES.issubset(set(inspector.get_table_names()))
            engine.dispose()
        finally:
            if previous_env is None:
                os.environ.pop("ALEMBIC_DATABASE_URL", None)
            else:
                os.environ["ALEMBIC_DATABASE_URL"] = previous_env
