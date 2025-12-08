import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import re

sys.path.append(os.path.join(os.getcwd(), "backend"))

env_path = os.path.join(os.getcwd(), "backend", ".env")
load_dotenv(env_path)

from app.endpoints.texts import TextService, ReferenceNavigator

async def test_fix():
    mongo_uri = os.getenv("MONGO_URI") or "mongodb://localhost:27017"
    db_name = os.getenv("MONGO_DB_NAME", "sefaria")
    
    from app.db.connection import MongoDatabase
    MongoDatabase.client = AsyncIOMotorClient(mongo_uri)
    MongoDatabase.db_name = db_name
    
    index_title = "Shulchan Arukh, Even HaEzer"
    
    print(f"=== Testing Fix for: {index_title} ===\n")
    
    db = MongoDatabase.get_db()
    doc = await TextService._find_best_document(db, index_title, None)
    
    if not doc:
        print("❌ Document not found!")
        return
    
    print(f"Selected document: {doc.get('versionTitle', 'N/A')} (Priority: {doc.get('priority', 'N/A')})")
    
    chapter_data_raw = doc.get("chapter", [])
    print(f"\nRaw chapter_data type: {type(chapter_data_raw)}")
    
    chapter_data = TextService._normalize_chapter_data(chapter_data_raw)
    print(f"Normalized chapter_data type: {type(chapter_data)}")
    print(f"Normalized chapter_data length: {len(chapter_data)}")
    
    print(f"\nTesting simanim 1-10:")
    for siman_num in range(1, 11):
        ref = f"{index_title} {siman_num}"
        parsed = ReferenceNavigator.parse_ref(ref)
        
        if "chapter" not in parsed:
            print(f"  Siman {siman_num}: FAILED to parse")
            continue
        
        chapter_index = parsed["chapter"] - 1
        
        if chapter_index < 0 or chapter_index >= len(chapter_data):
            print(f"  Siman {siman_num}: Index {chapter_index} out of bounds (max: {len(chapter_data)-1})")
            continue
        
        content = chapter_data[chapter_index]
        
        if isinstance(content, list):
            has_content = len(content) > 0
        else:
            has_content = bool(content)
        
        status = "✓ HAS CONTENT" if has_content else "✗ EMPTY"
        print(f"  Siman {siman_num} (index {chapter_index}): {status}")
    
    print("\n✅ Test completed!")
    
    MongoDatabase.client.close()

if __name__ == "__main__":
    asyncio.run(test_fix())

