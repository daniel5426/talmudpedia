import asyncio
from logging.config import fileConfig
import sys
import os
from dotenv import load_dotenv

# Add the backend directory to sys.path so we can import 'app'
base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_path)

# Load .env file
load_dotenv(os.path.join(base_path, ".env"))

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.db.postgres.base import Base  # Import your Base
from app.db.postgres.models import * # Import all models to register them
from app.db.postgres.engine import DATABASE_URL

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
print(f"DEBUG: target_metadata.tables = {list(target_metadata.tables.keys())}")

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section)
    # Force use of psycopg (v3) instead of asyncpg for migrations
    url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    if "postgresql+psycopg://" not in url:
             if "postgres://" in url:
                 url = url.replace("postgres://", "postgresql+psycopg://")
             elif "postgresql://" in url:
                 url = url.replace("postgresql://", "postgresql+psycopg://")

    configuration["sqlalchemy.url"] = url
    
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"prepare_threshold": None},
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
