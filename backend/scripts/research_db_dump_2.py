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
    
    print("\n--- Leviticus ---")
    lev = await index_col.find_one({"title": "Leviticus"})
    if lev:
        if "_id" in lev: del lev["_id"]
        print(json.dumps(lev, indent=2, cls=JSONEncoder))
    else:
        print("Leviticus not found")

    print("\n--- Esther ---")
    esther = await index_col.find_one({"title": "Esther"})
    if esther:
        if "_id" in esther: del esther["_id"]
        print(json.dumps(esther, indent=2, cls=JSONEncoder))
    else:
        print("Esther not found")

    # Count docs with schema
    schema_count = await index_col.count_documents({"schema": {"$exists": True}})
    print(f"\nDocuments with 'schema' field: {schema_count}")
    
    # Count docs with shape
    shape_count = await index_col.count_documents({"shape": {"$exists": True}})
    print(f"Documents with 'shape' field: {shape_count}")

    client.close()

if __name__ == "__main__":
    asyncio.run(research())
