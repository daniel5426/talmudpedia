import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import quote_plus

async def check_db():
    user = "daniel"
    password = "daniel"
    ip = "155.138.219.192"
    db_name = "sefaria"

    uri = f"mongodb://{quote_plus(user)}:{quote_plus(password)}@{ip}:27017/{db_name}?authSource=admin"
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    collection = db["library_siblings"]
    
    print("Checking connection...")
    count = await collection.count_documents({})
    print(f"Total documents in library_siblings: {count}")
    
    doc = await collection.find_one({"children": {"$exists": True}})
    if doc:
        print("Found a document with 'children' field:")
        print(f"ID: {doc.get('_id')}")
        print(f"Ref: {doc.get('ref')}")
        print(f"Children count: {len(doc.get('children', []))}")
    else:
        print("No documents found with 'children' field.")
        
    doc_any = await collection.find_one({})
    if doc_any:
        print("\nSample document structure:")
        # Print keys to see what's there
        print(f"Keys: {list(doc_any.keys())}")
        print(f"ID: {doc_any.get('_id')}")
        print(f"Ref: {doc_any.get('ref')}")

    client.close()

if __name__ == "__main__":
    asyncio.run(check_db())
