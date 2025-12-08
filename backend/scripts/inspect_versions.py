import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import json

# Add backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

# Load env from backend/.env
env_path = os.path.join(os.getcwd(), "backend", ".env")
load_dotenv(env_path)

async def inspect_versions():
    mongo_uri = os.getenv("MONGO_URI") or "mongodb://localhost:27017"
    db_name = os.getenv("MONGO_DB_NAME", "talmudpedia")
    
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]
    
    # Check texts collection for version info
    print("=== TEXTS COLLECTION ===")
    texts_count = await db.texts.count_documents({})
    print(f"Total texts: {texts_count}")
    
    # Get a sample text document
    sample_text = await db.texts.find_one({})
    if sample_text:
        print("\nSample text document keys:", list(sample_text.keys()))
        for key in ['title', 'versionTitle', 'versionSource', 'language', 'priority', 'status']:
            if key in sample_text:
                print(f"  {key}: {sample_text[key]}")
        
    # Check for a specific book with multiple versions
    print("\n=== CHECKING GENESIS VERSIONS ===")
    genesis_versions = await db.texts.find({"title": "Genesis"}).to_list(length=None)
    print(f"Found {len(genesis_versions)} versions of Genesis")
    
    for i, version in enumerate(genesis_versions):
        print(f"\nVersion {i+1}:")
        print(f"  versionTitle: {version.get('versionTitle')}")
        print(f"  language: {version.get('language')}")
        print(f"  priority: {version.get('priority', 'NOT FOUND')}")
        print(f"  status: {version.get('status', 'NOT FOUND')}")
        
    # Check for Talmud versions
    print("\n=== CHECKING BERAKHOT VERSIONS ===")
    berakhot_versions = await db.texts.find({"title": "Berakhot"}).to_list(length=None)
    print(f"Found {len(berakhot_versions)} versions of Berakhot")
    
    for i, version in enumerate(berakhot_versions):
        print(f"\nVersion {i+1}:")
        print(f"  versionTitle: {version.get('versionTitle')}")
        print(f"  language: {version.get('language')}")
        print(f"  priority: {version.get('priority', 'NOT FOUND')}")
        print(f"  status: {version.get('status', 'NOT FOUND')}")

if __name__ == "__main__":
    asyncio.run(inspect_versions())
