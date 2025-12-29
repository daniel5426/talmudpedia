import asyncio
import time
import json
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import quote_plus

async def diagnostic():
    user = "daniel"
    password = "Hjsjfk74jkffdDF"
    ip = "155.138.219.192"
    db_name = "sefaria"
    uri = f"mongodb://{quote_plus(user)}:{quote_plus(password)}@{ip}:27017/{db_name}?authSource=admin"
    
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    collection = db["library_siblings"]
    
    # 1. Check total folders
    start = time.time()
    folder_count = await collection.count_documents({"hasChildren": True})
    print(f"Total Folders: {folder_count} (Count took {time.time() - start:.3f}s)")
    
    # 2. Check the "Heaviest" nodes
    # Let's look for nodes with the most children
    print("\nTop 10 nodes by children count:")
    cursor = collection.aggregate([
        {"$project": {"title": 1, "child_count": {"$size": {"$ifNull": ["$children", []]}}}},
        {"$sort": {"child_count": -1}},
        {"$limit": 10}
    ])
    async for doc in cursor:
        print(f"  - {doc['title']}: {doc['child_count']} children")

    # 3. Simulate a fetch
    target = "halakhah" # Example
    start = time.time()
    doc = await collection.find_one({"_id": target}, {"children": 1})
    db_time = time.time() - start
    
    start = time.time()
    json_data = json.dumps(doc["children"])
    serial_time = time.time() - start
    
    print(f"\nFetch diagnostic for '{target}':")
    print(f"  DB Fetch: {db_time:.3f}s")
    print(f"  Serialization: {serial_time:.3f}s")
    print(f"  Data Size: {len(json_data)/1024:.2f} KB")

    client.close()

if __name__ == "__main__":
    asyncio.run(diagnostic())
