import asyncio
import os
import sys
from typing import List
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from tqdm import tqdm

# Add current directory and backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

# Load env from backend/.env
env_path = os.path.join(os.getcwd(), "backend", ".env")
load_dotenv(env_path)

from ingestion.sefaria_client import SefariaClient

async def ingest_structure():
    print("🚀 Starting Sefaria Structure Ingestion...")
    
    # 1. Setup DB
    mongo_uri = os.getenv("MONGO_URI") or "mongodb://localhost:27017"
    db_name = os.getenv("MONGO_DB_NAME", "talmudpedia")
    
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]
    
    # Collections
    index_coll = db["index"]
    
    # 2. Setup Sefaria Client
    sefaria = SefariaClient()
    
    # 3. Fetch All Titles
    print("Fetching all titles from Sefaria...")
    titles = sefaria.get_all_titles()
    print(f"Found {len(titles)} titles.")
    
    if not titles:
        print("❌ No titles found. Aborting.")
        return

    # 4. Ingest Loop
    # We will fetch Index and Shape for each title
    # To speed up, we could use asyncio.gather, but let's be polite to Sefaria API
    # and use a semaphore or just sequential with small delay if needed.
    # Sefaria API is usually fast.
    
    semaphore = asyncio.Semaphore(5) # Allow 5 concurrent requests
    
    async def process_title(title: str, pbar):
        async with semaphore:
            try:
                # Check if already exists (optional, for resume)
                # existing = await index_coll.find_one({"title": title})
                # if existing:
                #     pbar.update(1)
                #     return

                # Fetch Index Metadata
                # We run sync SefariaClient methods in a thread executor to keep asyncio loop running
                loop = asyncio.get_event_loop()
                
                index_data = await loop.run_in_executor(None, sefaria.get_index, title)
                if not index_data:
                    pbar.write(f"⚠️  Failed to fetch index for {title}")
                    pbar.update(1)
                    return

                # Fetch Shape
                shape_data = await loop.run_in_executor(None, sefaria.get_shape, title)
                
                # Merge Shape into Index Data for storage
                # We store it as 'shape' field
                index_data["shape"] = shape_data
                
                # Upsert into DB
                await index_coll.replace_one(
                    {"title": title},
                    index_data,
                    upsert=True
                )
                
            except Exception as e:
                pbar.write(f"❌ Error processing {title}: {e}")
            finally:
                pbar.update(1)

    # Run in batches
    tasks = []
    print("Starting ingestion loop...")
    with tqdm(total=len(titles)) as pbar:
        for title in titles:
            tasks.append(process_title(title, pbar))
        
        await asyncio.gather(*tasks)

    print("\n✅ Ingestion Complete.")
    
    # Verify counts
    count = await index_coll.count_documents({})
    print(f"Total Documents in 'index' collection: {count}")

if __name__ == "__main__":
    asyncio.run(ingest_structure())
