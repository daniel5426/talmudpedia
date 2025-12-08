import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from collections import Counter

# Add backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

from dotenv import load_dotenv
load_dotenv("backend/.env")

async def check_duplicates():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_uri)
    db = client["talmudpedia"]
    collection = db["index"]
    
    print("Fetching all titles...")
    cursor = collection.find({}, {"title": 1})
    titles = []
    async for doc in cursor:
        title = doc.get("title")
        if not title:
            print(f"⚠️  Document missing title: {doc.keys()}")
            continue
        titles.append(title)
        
    print(f"Total documents: {len(titles)}")
    
    counts = Counter(titles)
    duplicates = {t: c for t, c in counts.items() if c > 1}
    
    if duplicates:
        print(f"❌ Found {len(duplicates)} duplicates!")
        for t, c in list(duplicates.items())[:10]:
            print(f"   - {t}: {c}")
    else:
        print("✅ No duplicates found in DB.")

if __name__ == "__main__":
    asyncio.run(check_duplicates())
