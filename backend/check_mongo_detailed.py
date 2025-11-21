import asyncio
import os
from app.db.connection import MongoDatabase
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path("backend/.env"))

async def check():
    print("Connecting to database...")
    await MongoDatabase.connect()
    db = MongoDatabase.get_db()
    
    print("\n=== Checking 'texts' collection ===")
    count = await db.texts.count_documents({})
    print(f"Total documents: {count}")
    
    if count > 0:
        print("\nSample document:")
        doc = await db.texts.find_one()
        print(f"Title: {doc.get('title')}")
        print(f"Version Title: {doc.get('versionTitle')}")
        print(f"Language: {doc.get('language')}")
        print(f"Chapter structure: {type(doc.get('chapter'))}")
        if doc.get('chapter'):
            print(f"First chapter sample: {str(doc.get('chapter')[0])[:200]}...")
    
    print("\n=== Checking 'index' collection ===")
    index_count = await db.index.count_documents({})
    print(f"Total index documents: {index_count}")
    
    if index_count > 0:
        index_doc = await db.index.find_one()
        print(f"Sample index title: {index_doc.get('title')}")
        
    await MongoDatabase.close()

if __name__ == "__main__":
    asyncio.run(check())
