import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import quote_plus

async def debug_ref(ref):
    user = "daniel"
    password = "Hjsjfk74jkffdDF"
    ip = "155.138.219.192"
    db_name = "sefaria"
    uri = f"mongodb://{quote_plus(user)}:{quote_plus(password)}@{ip}:27017/{db_name}?authSource=admin"
    
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    collection = db["library_siblings"]
    
    doc = await collection.find_one({"ref": ref})
    
    if doc:
        print(f"Found node with ref '{ref}':")
        print(f"ID: {doc.get('_id')}")
        print(f"Title: {doc.get('title')}")
        print(f"Slug: {doc.get('slug')}")
        print(f"Has Children: {doc.get('hasChildren')}")
        print(f"Children Count: {len(doc.get('children', []))}")
    else:
        print(f"No node found with ref '{ref}'")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(debug_ref("Genesis"))
