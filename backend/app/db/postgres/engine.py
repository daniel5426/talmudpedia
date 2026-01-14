import os
import urllib.parse
from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine, async_sessionmaker, AsyncEngine

# Postgres (Supabase) configuration from environment variables
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    # Ensure usage of asyncpg driver
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
    elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "postgres")

    # Quote password for URL characters (like &, $, #)
    quoted_password = urllib.parse.quote_plus(password)
    
    # Construct the Async Database URL
    DATABASE_URL = f"postgresql+asyncpg://{user}:{quoted_password}@{host}:{port}/{db}"

print(f"DEBUG: Initializing DB Engine with URL: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else 'HIDDEN'}")  # Log host/db only

def create_async_engine() -> AsyncEngine:
    """
    Creates and returns a new SQLAlchemy AsyncEngine instance.
    """
    return _create_async_engine(
        DATABASE_URL,
        echo=False,  # Set to True for SQL logging
        pool_pre_ping=True,  # Enable pre-ping to handle closed connections
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
