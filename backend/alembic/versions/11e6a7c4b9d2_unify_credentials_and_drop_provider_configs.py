"""unify credentials and drop provider configs

Revision ID: 11e6a7c4b9d2
Revises: f3d5c7b9a1e2
Create Date: 2026-02-22 22:05:00.000000
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "11e6a7c4b9d2"
down_revision = "f3d5c7b9a1e2"
branch_labels = None
depends_on = None


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _drop_index_if_exists(name: str, table_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {idx["name"] for idx in inspector.get_indexes(table_name)}
    if name in existing:
        op.drop_index(name, table_name=table_name)


def _json_param(value) -> str:
    return json.dumps(value if value is not None else {})


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    credentials_value_sql = "CAST(:credentials AS jsonb)" if dialect == "postgresql" else ":credentials"
    config_value_sql = "CAST(:config AS jsonb)" if dialect == "postgresql" else ":config"

    # 1) Schema shape changes
    op.add_column(
        "integration_credentials",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("integration_credentials", "tenant_id", existing_type=sa.UUID(), nullable=True)

    # 2) Category data migration part A (artifact_secret -> custom)
    if dialect == "postgresql":
        op.execute(
            """
            UPDATE integration_credentials
            SET category = 'custom'
            WHERE category::text = 'artifact_secret'
            """
        )
    else:
        op.execute(
            """
            UPDATE integration_credentials
            SET category = 'custom'
            WHERE category = 'artifact_secret'
            """
        )

    # 3) Enum replacement for postgres (drop artifact_secret, add tool_provider)
    if dialect == "postgresql":
        op.execute("ALTER TYPE integrationcredentialcategory RENAME TO integrationcredentialcategory_old")
        op.execute(
            "CREATE TYPE integrationcredentialcategory AS ENUM ('llm_provider', 'vector_store', 'tool_provider', 'custom')"
        )
        op.execute(
            """
            ALTER TABLE integration_credentials
            ALTER COLUMN category TYPE integrationcredentialcategory
            USING category::text::integrationcredentialcategory
            """
        )
        op.execute("DROP TYPE integrationcredentialcategory_old")

    # 4) Category data migration part B (custom web_search/serper/tavily/exa -> tool_provider)
    if dialect == "postgresql":
        op.execute(
            """
            UPDATE integration_credentials
            SET category = 'tool_provider',
                provider_key = COALESCE(NULLIF(provider_variant, ''), 'serper'),
                provider_variant = NULL
            WHERE category::text = 'custom'
              AND provider_key = 'web_search'
            """
        )
        op.execute(
            """
            UPDATE integration_credentials
            SET category = 'tool_provider',
                provider_variant = NULL
            WHERE category::text = 'custom'
              AND provider_key IN ('serper', 'tavily', 'exa')
            """
        )
    else:
        op.execute(
            """
            UPDATE integration_credentials
            SET category = 'tool_provider',
                provider_key = COALESCE(NULLIF(provider_variant, ''), 'serper'),
                provider_variant = NULL
            WHERE category = 'custom'
              AND provider_key = 'web_search'
            """
        )
        op.execute(
            """
            UPDATE integration_credentials
            SET category = 'tool_provider',
                provider_variant = NULL
            WHERE category = 'custom'
              AND provider_key IN ('serper', 'tavily', 'exa')
            """
        )

    # 5) Env-only platform defaults: remove any platform-scoped provider credentials.
    if dialect == "postgresql":
        op.execute(
            """
            DELETE FROM integration_credentials
            WHERE tenant_id IS NULL
              AND category::text IN ('llm_provider', 'vector_store', 'tool_provider')
            """
        )
    else:
        op.execute(
            """
            DELETE FROM integration_credentials
            WHERE tenant_id IS NULL
              AND category IN ('llm_provider', 'vector_store', 'tool_provider')
            """
        )

    # 6) Relax old uniqueness and add new default-centric constraints
    _drop_index_if_exists("uq_integration_credentials_variant", "integration_credentials")
    _drop_index_if_exists("uq_integration_credentials_no_variant", "integration_credentials")
    _drop_index_if_exists("ix_integration_credentials_lookup", "integration_credentials")

    op.create_index(
        "ix_integration_credentials_lookup",
        "integration_credentials",
        ["tenant_id", "category", "provider_key", "provider_variant"],
        unique=False,
    )
    op.create_index(
        "uq_integration_credentials_default_with_variant",
        "integration_credentials",
        ["tenant_id", "category", "provider_key", "provider_variant"],
        unique=True,
        postgresql_where=sa.text("is_default = true AND provider_variant IS NOT NULL"),
        sqlite_where=sa.text("is_default = 1 AND provider_variant IS NOT NULL"),
    )
    op.create_index(
        "uq_integration_credentials_default_no_variant",
        "integration_credentials",
        ["tenant_id", "category", "provider_key"],
        unique=True,
        postgresql_where=sa.text("is_default = true AND provider_variant IS NULL"),
        sqlite_where=sa.text("is_default = 1 AND provider_variant IS NULL"),
    )
    # 7) Migrate provider_configs -> integration_credentials.
    # NOTE: We intentionally do not drop provider_configs in this migration.
    # In some production environments DROP TABLE on this relation can crash or
    # sever the DB session due to lock/infra behavior. Runtime no longer depends
    # on this table, so cleanup can be done later in a controlled manual step.
    if _table_exists(bind, "provider_configs"):
        provider_rows = bind.execute(
            sa.text(
                """
                SELECT tenant_id, provider::text AS provider, provider_variant, credentials, is_enabled, created_at, updated_at
                FROM provider_configs
                WHERE tenant_id IS NOT NULL
                """
            )
        ).mappings().all()
        for row in provider_rows:
            tenant_id = row["tenant_id"]
            provider_key = str(row["provider"] or "").lower()
            provider_variant = row["provider_variant"]
            credentials = row["credentials"] or {}
            is_enabled = bool(row["is_enabled"])

            existing = bind.execute(
                sa.text(
                    """
                    SELECT id
                    FROM integration_credentials
                    WHERE tenant_id IS NOT DISTINCT FROM :tenant_id
                      AND category::text = 'llm_provider'
                      AND provider_key = :provider_key
                      AND provider_variant IS NOT DISTINCT FROM :provider_variant
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "provider_key": provider_key,
                    "provider_variant": provider_variant,
                },
            ).mappings().first()

            if existing:
                bind.execute(
                    sa.text(
                        f"""
                        UPDATE integration_credentials
                        SET credentials = {credentials_value_sql},
                            is_enabled = :is_enabled,
                            is_default = true
                        WHERE id = :id
                        """
                    ),
                    {
                        "credentials": _json_param(credentials),
                        "is_enabled": is_enabled,
                        "id": existing["id"],
                    },
                )
            else:
                bind.execute(
                    sa.text(
                        f"""
                        INSERT INTO integration_credentials (
                            id, tenant_id, category, provider_key, provider_variant,
                            display_name, credentials, is_enabled, is_default, created_at, updated_at
                        ) VALUES (
                            :id, :tenant_id, 'llm_provider', :provider_key, :provider_variant,
                            :display_name, {credentials_value_sql}, :is_enabled, true, :created_at, :updated_at
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "tenant_id": tenant_id,
                        "provider_key": provider_key,
                        "provider_variant": provider_variant,
                        "display_name": f"{provider_key.title()} Default",
                        "credentials": _json_param(credentials),
                        "is_enabled": is_enabled,
                        "created_at": row["created_at"] or datetime.now(timezone.utc),
                        "updated_at": row["updated_at"] or datetime.now(timezone.utc),
                    },
                )
        # Deliberately skip DROP TABLE here; see note above.

    # 8) Migrate model binding inline api_key -> credential row and strip inline keys
    if _table_exists(bind, "model_provider_bindings"):
        rows = bind.execute(
            sa.text(
                """
                SELECT id, tenant_id, provider::text AS provider, credentials_ref, config
                FROM model_provider_bindings
                """
            )
        ).mappings().all()
        for row in rows:
            config = row["config"] or {}
            if not isinstance(config, dict):
                continue
            api_key = config.get("api_key")
            if not api_key:
                continue
            provider_key = str(row["provider"] or "").lower()
            provider_variant = config.get("provider_variant")
            credential_id = row["credentials_ref"]

            if credential_id is None:
                existing = bind.execute(
                    sa.text(
                        """
                        SELECT id, credentials
                        FROM integration_credentials
                        WHERE tenant_id IS NOT DISTINCT FROM :tenant_id
                          AND category::text = 'llm_provider'
                          AND provider_key = :provider_key
                          AND provider_variant IS NOT DISTINCT FROM :provider_variant
                        ORDER BY is_default DESC, updated_at DESC
                        LIMIT 1
                        """
                    ),
                    {
                        "tenant_id": row["tenant_id"],
                        "provider_key": provider_key,
                        "provider_variant": provider_variant,
                    },
                ).mappings().first()
                if existing:
                    credential_id = existing["id"]
                    creds_payload = existing["credentials"] or {}
                    if "api_key" not in creds_payload:
                        creds_payload["api_key"] = api_key
                        bind.execute(
                            sa.text(
                                f"UPDATE integration_credentials SET credentials = {credentials_value_sql} WHERE id = :id"
                            ),
                            {"credentials": _json_param(creds_payload), "id": credential_id},
                        )
                else:
                    credential_id = str(uuid.uuid4())
                    bind.execute(
                        sa.text(
                            f"""
                            INSERT INTO integration_credentials (
                                id, tenant_id, category, provider_key, provider_variant,
                                display_name, credentials, is_enabled, is_default, created_at, updated_at
                            ) VALUES (
                                :id, :tenant_id, 'llm_provider', :provider_key, :provider_variant,
                                :display_name, {credentials_value_sql}, true, true, :created_at, :updated_at
                            )
                            """
                        ),
                        {
                            "id": credential_id,
                            "tenant_id": row["tenant_id"],
                            "provider_key": provider_key,
                            "provider_variant": provider_variant,
                            "display_name": f"{provider_key.title()} Auto Migrated",
                            "credentials": _json_param({"api_key": api_key}),
                            "created_at": datetime.now(timezone.utc),
                            "updated_at": datetime.now(timezone.utc),
                        },
                    )
            config.pop("api_key", None)
            bind.execute(
                sa.text(
                    f"""
                    UPDATE model_provider_bindings
                    SET credentials_ref = COALESCE(credentials_ref, :credentials_ref),
                        config = {config_value_sql}
                    WHERE id = :id
                    """
                ),
                {"credentials_ref": credential_id, "config": _json_param(config), "id": row["id"]},
            )

    op.alter_column("integration_credentials", "is_default", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Recreate provider_configs table for compatibility when absent.
    if not _table_exists(bind, "provider_configs"):
        op.create_table(
            "provider_configs",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("tenant_id", sa.UUID(), nullable=True),
            sa.Column("provider", sa.Enum("openai", "anthropic", "google", "azure", "gemini", "huggingface", "local", "cohere", "groq", "mistral", "together", "custom", name="modelprovidertype"), nullable=False),
            sa.Column("provider_variant", sa.String(), nullable=True),
            sa.Column("credentials", sa.JSON(), nullable=False),
            sa.Column("is_enabled", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    _drop_index_if_exists("uq_integration_credentials_platform_default_no_variant", "integration_credentials")
    _drop_index_if_exists("uq_integration_credentials_platform_default_with_variant", "integration_credentials")
    _drop_index_if_exists("uq_integration_credentials_default_no_variant", "integration_credentials")
    _drop_index_if_exists("uq_integration_credentials_default_with_variant", "integration_credentials")
    _drop_index_if_exists("ix_integration_credentials_lookup", "integration_credentials")

    op.create_index(
        "uq_integration_credentials_variant",
        "integration_credentials",
        ["tenant_id", "category", "provider_key", "provider_variant"],
        unique=True,
        postgresql_where=sa.text("provider_variant IS NOT NULL"),
        sqlite_where=sa.text("provider_variant IS NOT NULL"),
    )
    op.create_index(
        "uq_integration_credentials_no_variant",
        "integration_credentials",
        ["tenant_id", "category", "provider_key"],
        unique=True,
        postgresql_where=sa.text("provider_variant IS NULL"),
        sqlite_where=sa.text("provider_variant IS NULL"),
    )

    op.alter_column("integration_credentials", "tenant_id", existing_type=sa.UUID(), nullable=False)
    op.drop_column("integration_credentials", "is_default")

    if dialect == "postgresql":
        op.execute("ALTER TYPE integrationcredentialcategory RENAME TO integrationcredentialcategory_new")
        op.execute(
            "CREATE TYPE integrationcredentialcategory AS ENUM ('llm_provider', 'vector_store', 'artifact_secret', 'custom')"
        )
        op.execute(
            """
            ALTER TABLE integration_credentials
            ALTER COLUMN category TYPE integrationcredentialcategory
            USING (
                CASE
                    WHEN category::text = 'tool_provider' THEN 'custom'
                    ELSE category::text
                END
            )::integrationcredentialcategory
            """
        )
        op.execute("DROP TYPE integrationcredentialcategory_new")
