import asyncio
import os
import sys

# Add the current directory to sys.path so we can import app modules
sys.path.append(os.getcwd())

from app.db.connection import MongoDatabase

async def main():
    await MongoDatabase.connect()
    db = MongoDatabase.get_db()
    # Try to find the document
    doc = await db.texts.find_one({"title": "Sha'ar HaHakdamot"})
    if not doc:
        print("Document not found with exact title.")
        doc = await db.texts.find_one({"title": {"$regex": "^Sha'ar HaHakdamot$", "$options": "i"}})
    
    if not doc:
        print("Document not found.")
        return

    chapter_data = doc.get("chapter")
    print(f"Type of chapter_data: {type(chapter_data)}")
    if isinstance(chapter_data, dict):
        print(f"Keys: {list(chapter_data.keys())}")
    elif isinstance(chapter_data, list):
        print(f"Length: {len(chapter_data)}")
        if len(chapter_data) > 0:
             print(f"First element type: {type(chapter_data[0])}")

if __name__ == "__main__":
    asyncio.run(main())
