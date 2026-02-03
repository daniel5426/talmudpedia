import asyncio
import os
import sys
from dotenv import load_dotenv

# Load env vars
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.db.postgres.engine import sessionmaker as AsyncSessionLocal
from app.services.registry_seeding import seed_global_models

async def run_seed():
    async with AsyncSessionLocal() as db:
        await seed_global_models(db)

if __name__ == "__main__":
    asyncio.run(run_seed())
