import asyncio
import os
import sys
import json
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

load_dotenv("backend/.env")

class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if hasattr(o, '__dict__'):
            return o.__dict__
        if str(o).startswith("ObjectId"):
            return str(o)
        return str(o)

async def research():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_uri)
    db = client["talmudpedia"]
    index_col = db["index"]
    
    # Compare Leviticus documents
    print("=== Searching for Leviticus ===")
    lev_docs = []
    async for doc in index_col.find({"title": "Leviticus"}):
        lev_docs.append(doc)
    
    print(f"Found {len(lev_docs)} Leviticus documents")
    
    for i, doc in enumerate(lev_docs):
        print(f"\n--- Leviticus Document {i+1} ---")
        print(f"ID: {doc['_id']}")
        print(f"Has schema: {'schema' in doc}")
        print(f"Has shape: {'shape' in doc}")
        
        if 'schema' in doc and isinstance(doc['schema'], dict):
            print(f"Schema titles: {[t.get('text') for t in doc['schema'].get('titles', [])]}")
            
    # Check statistics
    both = await index_col.count_documents({"schema": {"$exists": True}, "shape": {"$exists": True}})
    only_schema = await index_col.count_documents({"schema": {"$exists": True}, "shape": {"$exists": False}})
    only_shape = await index_col.count_documents({"schema": {"$exists": False}, "shape": {"$exists": True}})
    neither = await index_col.count_documents({"schema": {"$exists": False}, "shape": {"$exists": False}})
    
    print("\n=== Statistics ===")
    print(f"Both schema and shape: {both}")
    print(f"Only schema: {only_schema}")
    print(f"Only shape: {only_shape}")
    print(f"Neither: {neither}")

    # Sample a Talmud text
    print("\n=== Berakhot (Talmud) ===")
    ber = await index_col.find_one({"title": "Berakhot"})
    if ber:
        print(f"Has schema: {'schema' in ber}")
        print(f"Has shape: {'shape' in ber}")
        if 'schema' in ber and isinstance(ber['schema'], dict):
            print(f"Schema node type: {ber['schema'].get('nodeType')}")
            print(f"Schema has nodes: {'nodes' in ber['schema']}")
            
    # Sample Shulchan Arukh
    print("\n=== Shulchan Arukh, Orach Chayim ===")
    sa = await index_col.find_one({"title": "Shulchan Arukh, Orach Chayim"})
    if sa:
        print(f"Has schema: {'schema' in sa}")
        print(f"Has shape: {'shape' in sa}")
        if 'schema' in sa and isinstance(sa['schema'], dict):
            print(f"Schema node type: {sa['schema'].get('nodeType')}")
            print(f"Schema has nodes: {'nodes' in sa['schema']}")

    client.close()

if __name__ == "__main__":
    asyncio.run(research())
