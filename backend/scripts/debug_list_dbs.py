import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import quote_plus

async def list_dbs():
    user = "daniel"
    password = "daniel"
    ip = "155.138.219.192"

    uri = f"mongodb://{quote_plus(user)}:{quote_plus(password)}@{ip}:27017/?authSource=admin"
    client = AsyncIOMotorClient(uri)
    
    print("Listing databases...")
    dbs = await client.list_database_names()
    print(f"Databases: {dbs}")
    
    for db_name in dbs:
        db = client[db_name]
        collections = await db.list_collection_names()
        print(f"  DB: {db_name}, Collections: {collections}")
        if "library_siblings" in collections:
            count = await db["library_siblings"].count_documents({})
            print(f"    -> library_siblings count: {count}")

    client.close()

if __name__ == "__main__":
    asyncio.run(list_dbs())
