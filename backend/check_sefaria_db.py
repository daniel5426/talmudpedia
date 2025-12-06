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

async def check_sefaria_db():
    mongo_uri = os.getenv("MONGO_URI") or "mongodb://localhost:27017"
    
    client = AsyncIOMotorClient(mongo_uri)
    db = client["sefaria"]  # Check the sefaria database
    
    print("=== COLLECTIONS IN sefaria DATABASE ===")
    collections = await db.list_collection_names()
    for coll in collections:
        count = await db[coll].count_documents({})
        print(f"\n{coll}: {count} documents")
        
        if count > 0:
            sample = await db[coll].find_one({})
            print(f"  Sample keys: {list(sample.keys())}")
            
            # Check for priority field
            if 'priority' in sample:
                print(f"  ✓ HAS 'priority' field: {sample['priority']}")
            if 'versionTitle' in sample:
                print(f"  ✓ HAS 'versionTitle': {sample.get('versionTitle', 'N/A')}")
            if 'title' in sample:
                print(f"  Sample title: {sample['title']}")
                
    # Specifically check for texts collection
    print("\n=== CHECKING 'texts' COLLECTION ===")
    texts_count = await db.texts.count_documents({})
    print(f"Total texts: {texts_count}")
    
    if texts_count > 0:
        # Check Genesis versions
        genesis_versions = await db.texts.find({"title": "Genesis"}).to_list(length=10)
        print(f"\nGenesis versions: {len(genesis_versions)}")
        for v in genesis_versions:
            print(f"  - {v.get('language')}: {v.get('versionTitle')} (priority: {v.get('priority', 'N/A')})")

if __name__ == "__main__":
    asyncio.run(check_sefaria_db())
