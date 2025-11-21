import asyncio
from app.db.connection import MongoDatabase
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path("backend/.env"))

async def check_talmud():
    await MongoDatabase.connect()
    db = MongoDatabase.get_db()
    
    # Find Taanit
    doc = await db.texts.find_one({"title": {"$regex": "^Taanit", "$options": "i"}})
    
    if doc:
        print(f"Title: {doc.get('title')}")
        print(f"Version: {doc.get('versionTitle')}")
        print(f"Language: {doc.get('language')}")
        
        chapter = doc.get('chapter', [])
        print(f"\nChapter structure:")
        print(f"  Type: {type(chapter)}")
        print(f"  Length: {len(chapter)}")
        
        if len(chapter) > 0:
            print(f"\n  First element type: {type(chapter[0])}")
            if isinstance(chapter[0], list):
                print(f"  First element length: {len(chapter[0])}")
                if len(chapter[0]) > 0:
                    print(f"  Sample: {str(chapter[0][0])[:200]}...")
            else:
                print(f"  Sample: {str(chapter[0])[:200]}...")
        
        # Check what index 11 (12a in 1-indexed) looks like
        if len(chapter) > 11:
            print(f"\n  Index 11 (12a) type: {type(chapter[11])}")
            if isinstance(chapter[11], list):
                print(f"  Index 11 length: {len(chapter[11])}")
    else:
        print("Taanit not found")
    
    await MongoDatabase.close()

if __name__ == "__main__":
    asyncio.run(check_talmud())
