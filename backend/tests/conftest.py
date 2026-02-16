import asyncio
import os
import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import types
from sqlalchemy.dialects import postgresql
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

USE_REAL_DB = os.getenv("TEST_USE_REAL_DB") == "1"
sqlite3.register_adapter(UUID, lambda value: str(value))
os.environ.setdefault("APPS_BUILDER_BUILD_AUTOMATION_ENABLED", "0")
os.environ.setdefault("APPS_PUBLISH_JOB_EAGER", "1")
os.environ.setdefault("APPS_PUBLISH_MOCK_MODE", "1")

if USE_REAL_DB:
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parents[1] / ".env"
        load_dotenv(env_path)
    except Exception:
        pass

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.postgres.base import Base
from app.db.postgres.session import get_db
from app.db.postgres.models.identity import User, OrgMembership, MembershipStatus


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


class SQLiteUUID(types.TypeDecorator):
    impl = types.String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        import uuid as _uuid

        return _uuid.UUID(value)


def _normalize_sqlite_metadata_types() -> None:
    """Make SQLAlchemy metadata SQLite-friendly before tests build ORM expressions."""
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, (postgresql.ENUM, types.Enum)):
                column.type = types.String(50)
            elif isinstance(column.type, postgresql.UUID):
                column.type = SQLiteUUID()
            elif isinstance(column.type, postgresql.JSONB):
                column.type = types.JSON()


if not USE_REAL_DB:
    # Load all model tables and coerce types eagerly so early ORM expression
    # construction (before test_engine fixture) uses SQLite-safe types.
    import app.db.postgres.models  # noqa: F401

    _normalize_sqlite_metadata_types()


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


def pytest_collection_modifyitems(config, items):
    if USE_REAL_DB:
        return
    skip_real_db = pytest.mark.skip(reason="TEST_USE_REAL_DB=1 is required for real DB tests.")
    for item in items:
        if "real_db" in item.keywords:
            item.add_marker(skip_real_db)


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    if USE_REAL_DB:
        from app.db.postgres.engine import engine as real_engine
        yield real_engine
        return

    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        import app.db.postgres.models
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    from app.db.postgres.engine import sessionmaker as global_sessionmaker
    import app.db.postgres.engine as engine_module
    import app.db.postgres.session as session_module

    session_factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)

    original_factory = engine_module.sessionmaker
    original_session_factory = session_module.sessionmaker
    engine_module.sessionmaker = session_factory
    session_module.sessionmaker = session_factory

    async with session_factory() as session:
        yield session
        await session.rollback()

    engine_module.sessionmaker = original_factory
    session_module.sessionmaker = original_session_factory


@pytest_asyncio.fixture
async def client(db_session):
    import vector_store as vector_store_module

    class _TestVectorStore:
        def __init__(self, *args, **kwargs):
            self.index = None

        def similarity_search(self, *args, **kwargs):
            return []

        def add_documents(self, *args, **kwargs):
            return []

    vector_store_module.VectorStore = _TestVectorStore

    from main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _resolve_tenant_id(engine) -> UUID:
    tenant_id = os.getenv("TEST_TENANT_ID")
    if tenant_id:
        return UUID(tenant_id)

    email = os.getenv("TEST_TENANT_EMAIL")
    if not email:
        raise RuntimeError("TEST_TENANT_EMAIL or TEST_TENANT_ID must be set for real DB tests.")

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if not user:
            raise RuntimeError(f"No user found for TEST_TENANT_EMAIL={email}")

        membership = await session.scalar(
            select(OrgMembership).where(
                OrgMembership.user_id == user.id,
                OrgMembership.status == MembershipStatus.active,
            )
        )
        if not membership:
            membership = await session.scalar(
                select(OrgMembership).where(OrgMembership.user_id == user.id)
            )
        if not membership:
            raise RuntimeError(f"No org membership found for user {email}")

        return membership.tenant_id


@pytest_asyncio.fixture(scope="session")
async def test_tenant_id(test_engine):
    if not USE_REAL_DB:
        pytest.skip("TEST_USE_REAL_DB=1 is required for tenant-scoped tests.")
    return await _resolve_tenant_id(test_engine)


@pytest_asyncio.fixture(scope="session")
async def test_user_id(test_engine):
    if not USE_REAL_DB:
        pytest.skip("TEST_USE_REAL_DB=1 is required for tenant-scoped tests.")
    email = os.getenv("TEST_TENANT_EMAIL")
    if not email:
        raise RuntimeError("TEST_TENANT_EMAIL must be set to resolve test user.")

    session_factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if not user:
            raise RuntimeError(f"No user found for TEST_TENANT_EMAIL={email}")
        return user.id


@pytest.fixture
def run_prefix():
    return f"test-{uuid4().hex[:8]}"
