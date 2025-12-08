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

async def deep_inspect():
    mongo_uri = os.getenv("MONGO_URI") or "mongodb://localhost:27017"
    db_name = os.getenv("MONGO_DB_NAME", "talmudpedia")
    
    client = AsyncIOMotorClient(mongo_uri)
    
    # List all databases
    print("=== ALL DATABASES ===")
    dbs = await client.list_database_names()
    for db in dbs:
        print(f"  - {db}")
    
    db = client[db_name]
    
    # List all collections with counts
    print(f"\n=== COLLECTIONS IN {db_name} ===")
    collections = await db.list_collection_names()
    for coll in collections:
        count = await db[coll].count_documents({})
        print(f"  - {coll}: {count} documents")
        
        # Sample document from each non-empty collection
        if count > 0:
            sample = await db[coll].find_one({})
            print(f"    Sample keys: {list(sample.keys())[:10]}")
            
            # Check if it has title field
            if 'title' in sample:
                print(f"    Sample title: {sample['title']}")
                # Check all unique titles to find books
                if count < 1000:  # Only if reasonable size
                    distinct_titles = await db[coll].distinct('title')
                    print(f"    Unique titles count: {len(distinct_titles)}")
                    if len(distinct_titles) < 20:
                        print(f"    Titles: {distinct_titles[:10]}")

if __name__ == "__main__":
    asyncio.run(deep_inspect())
