import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import quote_plus
import json

async def debug_node(slug):
    user = "daniel"
    password = "Hjsjfk74jkffdDF"
    ip = "155.138.219.192"
    db_name = "sefaria"
    uri = f"mongodb://{quote_plus(user)}:{quote_plus(password)}@{ip}:27017/{db_name}?authSource=admin"
    
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    collection = db["library_siblings"]
    
    # Check all nodes with this slug
    cursor = collection.find({"slug": slug})
    nodes = await cursor.to_list(length=10)
    
    print(f"Found {len(nodes)} nodes with slug '{slug}':")
    for doc in nodes:
        print(f"ID: {doc.get('_id')}")
        print(f"Title: {doc.get('title')}")
        print(f"Has Children: {doc.get('hasChildren')}")
        print(f"Children Count: {len(doc.get('children', []))}")
        if doc.get('children'):
            print(f"First child: {doc['children'][0]}")
        print("-" * 20)
    
    client.close()

if __name__ == "__main__":
    # Genesis is a good test case
    asyncio.run(debug_node("Genesis"))
