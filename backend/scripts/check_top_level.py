import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import quote_plus

async def check_ids():
    user = "daniel"
    password = "Hjsjfk74jkffdDF"
    ip = "155.138.219.192"
    db_name = "sefaria"
    uri = f"mongodb://{quote_plus(user)}:{quote_plus(password)}@{ip}:27017/{db_name}?authSource=admin"
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    collection = db["library_siblings"]
    
    # List top level
    cursor = collection.find({"path": []})
    async for doc in cursor:
        print(f"Top Level ID: {doc['_id']}, Title: {doc['title']}")

    client.close()

if __name__ == "__main__":
    asyncio.run(check_ids())
