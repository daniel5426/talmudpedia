import asyncio
import os
from app.db.connection import MongoDatabase
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path("backend/.env"))

async def explore_structure():
    await MongoDatabase.connect()
    db = MongoDatabase.get_db()
    
    # Get a sample text to understand structure
    doc = await db.texts.find_one({"title": "Genesis"})
    
    if doc:
        print(f"Title: {doc.get('title')}")
        print(f"Version: {doc.get('versionTitle')}")
        print(f"Language: {doc.get('language')}")
        print(f"\nChapter structure:")
        chapter = doc.get('chapter', [])
        print(f"  Type: {type(chapter)}")
        print(f"  Length (chapters): {len(chapter)}")
        
        if len(chapter) > 0:
            print(f"\n  Chapter 1 type: {type(chapter[0])}")
            if isinstance(chapter[0], list):
                print(f"  Chapter 1 length (verses): {len(chapter[0])}")
                if len(chapter[0]) > 0:
                    print(f"\n  Genesis 1:1 = {chapter[0][0][:200]}...")
            else:
                print(f"  Chapter 1 content: {str(chapter[0])[:200]}...")
    else:
        print("Genesis not found")
    
    # Check Talmud structure
    print("\n\n=== Talmud Structure ===")
    talmud_doc = await db.texts.find_one({"title": {"$regex": "^Berakhot", "$options": "i"}})
    if talmud_doc:
        print(f"Title: {talmud_doc.get('title')}")
        print(f"Version: {talmud_doc.get('versionTitle')}")
        chapter = talmud_doc.get('chapter', [])
        print(f"Chapter structure type: {type(chapter)}")
        print(f"Length: {len(chapter)}")
        if len(chapter) > 0:
            print(f"First element type: {type(chapter[0])}")
            print(f"Sample: {str(chapter[0])[:200]}...")
    
    await MongoDatabase.close()

if __name__ == "__main__":
    asyncio.run(explore_structure())
