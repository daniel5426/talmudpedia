import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

user = os.getenv("POSTGRES_USER")
password = os.getenv("POSTGRES_PASSWORD")
host = os.getenv("POSTGRES_HOST")
port = os.getenv("POSTGRES_PORT")
db = os.getenv("POSTGRES_DB")

DATABASE_URL = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"

async def check_records():
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        print("Checking users...")
        res = await conn.execute(text("SELECT id, email FROM users ORDER BY created_at DESC LIMIT 5"))
        for row in res:
            print(f"User: {row}")
            
        print("Checking tenants...")
        res = await conn.execute(text("SELECT id, name FROM tenants ORDER BY created_at DESC LIMIT 5"))
        for row in res:
            print(f"Tenant: {row}")
            
        print("Checking memberships...")
        res = await conn.execute(text("SELECT id, user_id, tenant_id FROM org_memberships ORDER BY joined_at DESC LIMIT 5"))
        for row in res:
            print(f"Membership: {row}")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_records())
