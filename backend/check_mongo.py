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
    
    print("Checking 'texts' collection...")
    doc = await db.texts.find_one()
    if doc:
        print("Found document:")
        print(doc)
    else:
        print("Collection 'texts' is empty.")
        
    await MongoDatabase.close()

if __name__ == "__main__":
    asyncio.run(check())
