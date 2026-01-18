import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Import models to register them
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.db.postgres.base import Base
from app.db.postgres.models import *

async def create_tables():
    from app.db.postgres.engine import DATABASE_URL
    # Force use of psycopg for synchronous-like behavior in create_all if needed, 
    # but we'll stick to async engine since it's already configured.
    engine = create_async_engine(DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    
    print(f"Connecting to database...")
    async with engine.begin() as conn:
        print("Creating tables if they don't exist...")
        # We'll use run_sync to execute Base.metadata.create_all
        await conn.run_sync(Base.metadata.create_all)
        print("Tables created successfully (or already existed).")
    
    await engine.dispose()

if __name__ == "__main__":
    import traceback
    try:
        asyncio.run(create_tables())
    except Exception:
        traceback.print_exc()
