import asyncio
import os
from app.db.connection import MongoDatabase
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path("backend/.env"))

async def test_lookup():
    await MongoDatabase.connect()
    db = MongoDatabase.get_db()
    
    # Test with a known reference format
    test_refs = ["Genesis 1:1", "Genesis 1", "Berakhot 2a", "Pirkei Avot"]
    
    for ref in test_refs:
        print(f"\n=== Testing ref: '{ref}' ===")
        
        # Try exact match
        doc = await db.texts.find_one({"title": ref})
        if doc:
            print(f"✓ Found exact match")
            print(f"  Title: {doc.get('title')}")
            print(f"  Version: {doc.get('versionTitle')}")
            print(f"  Chapter type: {type(doc.get('chapter'))}")
        else:
            print(f"✗ No exact match")
            
            # Try case-insensitive
            doc = await db.texts.find_one({"title": {"$regex": f"^{ref}$", "$options": "i"}})
            if doc:
                print(f"✓ Found case-insensitive match")
                print(f"  Title: {doc.get('title')}")
            else:
                print(f"✗ No case-insensitive match either")
    
    await MongoDatabase.close()

if __name__ == "__main__":
    asyncio.run(test_lookup())
