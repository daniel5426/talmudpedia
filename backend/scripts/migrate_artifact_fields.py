
import os
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL not found in environment")
    exit(1)

# Convert postgresql:// to postgresql+psycopg:// for async compatibility if needed
# Actually main.py seems to be using it as is or with some prefix.
# The log says: DEBUG: Creating Async Engine with Psycopg (v3)

if DATABASE_URL.startswith("postgresql://"):
    ASYNC_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")
else:
    ASYNC_URL = DATABASE_URL

async def migrate():
    engine = create_async_engine(ASYNC_URL)
    
    async with engine.begin() as conn:
        print("Checking for missing columns in custom_operators...")
        
        # Check if scope exists
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='custom_operators' AND column_name='scope'"))
        if not result.fetchone():
            print("Adding 'scope' column...")
            await conn.execute(text("ALTER TABLE custom_operators ADD COLUMN scope VARCHAR NOT NULL DEFAULT 'rag'"))
        
        # Check if reads exists
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='custom_operators' AND column_name='reads'"))
        if not result.fetchone():
            print("Adding 'reads' column...")
            await conn.execute(text("ALTER TABLE custom_operators ADD COLUMN reads JSONB NOT NULL DEFAULT '[]'"))
            
        # Check if writes exists
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='custom_operators' AND column_name='writes'"))
        if not result.fetchone():
            print("Adding 'writes' column...")
            await conn.execute(text("ALTER TABLE custom_operators ADD COLUMN writes JSONB NOT NULL DEFAULT '[]'"))
            
        print("Migration complete!")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate())
