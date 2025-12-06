import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

load_dotenv("backend/.env")

async def research():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_uri)
    db = client["talmudpedia"]
    
    print(f"Connected to {mongo_uri}")
    
    # Check collections
    collections = await db.list_collection_names()
    print(f"Collections: {collections}")
    
    # Inspect 'index' collection
    index_col = db["index"]
    count = await index_col.count_documents({})
    print(f"Total documents in 'index': {count}")
    
    # Sample different categories
    categories_to_check = ["Tanakh", "Talmud", "Mishnah", "Halakhah"]
    
    for cat in categories_to_check:
        print(f"\n--- Sampling {cat} ---")
        sample = await index_col.find_one({"categories": cat})
        if sample:
            print(f"Title: {sample.get('title')}")
            print(f"Categories: {sample.get('categories')}")
            print(f"Schema keys: {sample.get('schema', {}).keys()}")
            
            # Check for Hebrew title in schema
            titles = sample.get("schema", {}).get("titles", [])
            print(f"Schema Titles: {titles}")
            
            # Check for section names
            print(f"Section Names: {sample.get('sectionNames')}")
            print(f"He Section Names: {sample.get('heSectionNames')}") # Checking if this exists
            
            # Check schema node structure
            schema = sample.get("schema", {})
            print(f"Schema Node Type: {schema.get('nodeType')}")
            if "nodes" in schema:
                print(f"Has sub-nodes: {len(schema['nodes'])}")
                print(f"First sub-node keys: {schema['nodes'][0].keys()}")
        else:
            print(f"No sample found for {cat}")

    # Check for a complex text (e.g. with multiple depths or complex structure)
    print("\n--- Sampling Complex Text ---")
    # Try to find one with 'nodes' in schema
    complex_sample = await index_col.find_one({"schema.nodes": {"$exists": True}})
    if complex_sample:
        print(f"Title: {complex_sample.get('title')}")
        print(f"Schema keys: {complex_sample.get('schema', {}).keys()}")
        print(f"First node title: {complex_sample['schema']['nodes'][0].get('titles')}")

    client.close()

if __name__ == "__main__":
    asyncio.run(research())
