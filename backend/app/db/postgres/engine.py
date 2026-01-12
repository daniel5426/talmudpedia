import os
import urllib.parse
from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine, async_sessionmaker, AsyncEngine

# Postgres (Supabase) configuration from environment variables
user = os.getenv("POSTGRES_USER", "postgres")
password = os.getenv("POSTGRES_PASSWORD", "")
host = os.getenv("POSTGRES_HOST", "localhost")
port = os.getenv("POSTGRES_PORT", "5432")
db = os.getenv("POSTGRES_DB", "postgres")

# Quote password for URL characters (like &, $, #)
quoted_password = urllib.parse.quote_plus(password)

# Construct the Async Database URL
# We use the asyncpg driver which is compatible with SQLAlchemy's async support
DATABASE_URL = f"postgresql+asyncpg://{user}:{quoted_password}@{host}:{port}/{db}"

def create_async_engine() -> AsyncEngine:
    """
    Creates and returns a new SQLAlchemy AsyncEngine instance.
    """
    return _create_async_engine(
        DATABASE_URL,
        echo=False,  # Set to True for SQL logging
        pool_pre_ping=True,  # Check connection health before using
        pool_size=20,
        max_overflow=10,
    )

# Create a global engine instance
engine = create_async_engine()

# Create a session factory
# This is used in app/db/postgres/session.py as:
# async with sessionmaker() as session:
sessionmaker = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)
