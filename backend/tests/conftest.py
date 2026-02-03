import sys
import os
import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import Column, String, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB as PG_JSONB

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.postgres.base import Base
from app.db.postgres.session import get_db
from main import app

# Database URL for testing
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture()
async def test_engine():

    """Create a test engine with SQLite in-memory."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # SQLite compatibility for Postgres types
    from sqlalchemy import event, types
    from sqlalchemy.dialects import postgresql
    import json
    import uuid

    class SQLiteUUID(types.TypeDecorator):
        impl = types.String(36)
        cache_ok = True
        def process_bind_param(self, value, dialect):
            if value is None: return value
            return str(value)
        def process_result_value(self, value, dialect):
            if value is None: return value
            return uuid.UUID(value)

    class SQLiteJSON(types.TypeDecorator):
        impl = types.JSON
        cache_ok = True
        def process_bind_param(self, value, dialect):
            if value is None: return value
            return value # types.JSON handles dict to string
        def process_result_value(self, value, dialect):
            return value

    @event.listens_for(Base.metadata, "before_create")
    def receive_before_create(target, connection, **kw):
        """Map Postgres types to SQLite-compatible types."""
        for table in target.tables.values():
            for column in table.columns:
                if isinstance(column.type, (postgresql.ENUM, types.Enum)):
                    column.type = types.String(50)
                elif isinstance(column.type, postgresql.UUID):
                    column.type = SQLiteUUID()
                elif isinstance(column.type, postgresql.JSONB):
                    column.type = types.JSON()
    
    async with engine.begin() as conn:
        import app.db.postgres.models
        await conn.run_sync(Base.metadata.create_all)

    
    yield engine
    await engine.dispose()



@pytest_asyncio.fixture
async def db_session(test_engine):
    """Create a new database session for a test."""
    from app.db.postgres.engine import sessionmaker as global_sessionmaker
    import app.db.postgres.engine
    
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    
    # Patch the global sessionmaker so background tasks in AgentExecutorService use the test DB
    original_factory = app.db.postgres.engine.sessionmaker
    app.db.postgres.engine.sessionmaker = session_factory
    
    async with session_factory() as session:
        yield session
        await session.rollback()
    
    # Restore (though usually not necessary for in-memory tests, good practice)
    app.db.postgres.engine.sessionmaker = original_factory

@pytest_asyncio.fixture
async def client(db_session):
    """Create a new FastAPI TestClient."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

@pytest.fixture
def artifact_context():
    """Fixture to provide an ArtifactContext for testing operators."""
    from app.rag.pipeline.operator_executor import ArtifactContext
    
    def _create_context(data=None, config=None, metadata=None):
        return ArtifactContext(
            input_data=data or [],
            config=config or {},
            metadata=metadata or {}
        )
    
    return _create_context

