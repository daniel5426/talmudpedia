import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import quote_plus
import json

async def measure_chunk(slug):
    user = "daniel"
    password = "Hjsjfk74jkffdDF"
    ip = "155.138.219.192"
    db_name = "sefaria"
    uri = f"mongodb://{quote_plus(user)}:{quote_plus(password)}@{ip}:27017/{db_name}?authSource=admin"
    
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    collection = db["library_siblings"]
    
    doc = await collection.find_one({"_id": slug}, {"children": 1})
    if doc:
        children = doc.get("children", [])
        print(f"ID: {slug}")
        print(f"Children Count: {len(children)}")
        data_str = json.dumps(children)
        print(f"JSON size: {len(data_str) / 1024:.2f} KB")
    else:
        print(f"Not found: {slug}")
    client.close()

if __name__ == "__main__":
    asyncio.run(measure_chunk("tanakh"))
    print("-" * 20)
    asyncio.run(measure_chunk("halakhah"))
    print("-" * 20)
    asyncio.run(measure_chunk("talmud"))
