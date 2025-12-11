import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from motor.motor_asyncio import AsyncIOMotorClient
from app.services.text.navigator import ReferenceNavigator

async def check():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_uri)
    db = client["sefaria"]
    
    print("=== Checking index collection ===")
    index_doc = await db.index.find_one({"title": "Rashbam on Bava Batra"})
    if index_doc:
        print(f"  Found index: {index_doc.get('title')}")
        print(f"  heTitle: {index_doc.get('heTitle')}")
        schema = index_doc.get('schema', {})
        print(f"  schema keys: {list(schema.keys()) if schema else 'None'}")
        print(f"  schema nodeType: {schema.get('nodeType')}")
        print(f"  schema has nodes: {bool(schema.get('nodes'))}")
    else:
        print("  Index not found")
    
    print("\n=== Checking texts collection ===")
    texts = await db.texts.find({
        "title": {"$regex": "Rashbam.*Bava.*Batra", "$options": "i"}
    }).to_list(length=10)
    
    print(f"  Found {len(texts)} documents matching pattern")
    for t in texts:
        print(f"    title: {t.get('title')}")
        print(f"    language: {t.get('language')}")
        print(f"    versionTitle: {t.get('versionTitle')}")
        print(f"    sectionRef: {t.get('sectionRef')}")
        chapter = t.get('chapter', [])
        if isinstance(chapter, list):
            print(f"    chapter array length: {len(chapter)}")
        elif isinstance(chapter, dict):
            print(f"    chapter dict keys: {list(chapter.keys())[:5]}")
        print()
    
    print("\n=== Testing ref parsing ===")
    test_ref = "Rashbam on Bava Batra 29a"
    parsed = ReferenceNavigator.parse_ref(test_ref)
    print(f"  Ref: {test_ref}")
    print(f"  Parsed: {parsed}")
    print(f"  index_title: {parsed.get('index')}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(check())

