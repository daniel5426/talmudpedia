import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

# Load env from backend/.env
env_path = os.path.join(os.getcwd(), "backend", ".env")
load_dotenv(env_path)

async def inspect_db():
    mongo_uri = os.getenv("MONGO_URI") or "mongodb://localhost:27017"
    db_name = os.getenv("MONGO_DB_NAME", "talmudpedia")
    
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]
    
    collections = await db.list_collection_names()
    print(f"Collections in {db_name}: {collections}")
    
    for col_name in collections:
        print(f"\n--- Collection: {col_name} ---")
        count = await db[col_name].count_documents({})
        print(f"Count: {count}")
        
        sample = await db[col_name].find_one({})
        if sample:
            # Print keys and some values, truncating long lists/strings
            print("Sample document keys:", list(sample.keys()))
            if "priority" in sample:
                print(f"FOUND 'priority' field: {sample['priority']}")
            if "versionTitle" in sample:
                print(f"FOUND 'versionTitle': {sample['versionTitle']}")
            if "versions" in sample:
                print(f"FOUND 'versions' field")
            
            # Check for version-like fields
            for key, val in sample.items():
                if isinstance(val, dict) and "priority" in val:
                     print(f"Found 'priority' in nested key '{key}'")

if __name__ == "__main__":
    asyncio.run(inspect_db())
