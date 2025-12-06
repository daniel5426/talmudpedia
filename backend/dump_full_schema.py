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
    
    # Get Leviticus with schema
    print("=== Leviticus (with schema) ===")
    lev = await index_col.find_one({"title": "Leviticus", "schema": {"$exists": True}})
    if lev:
        if "_id" in lev: del lev["_id"]
        print(json.dumps(lev, indent=2, cls=JSONEncoder))
    
    print("\n\n=== Shulchan Arukh, Orach Chayim (with schema.nodes) ===")
    # Find a document with schema.nodes
    sa_schema = await index_col.find_one({"title": "Shulchan Arukh, Orach Chayim", "schema.nodes": {"$exists": True}})
    if sa_schema:
        if "_id" in sa_schema: del sa_schema["_id"]
        print(json.dumps(sa_schema, indent=2, cls=JSONEncoder))
    else:
        # Check if any SA document has schema
        sa_any = await index_col.find_one({"title": {"$regex": "Shulchan Arukh"}, "schema": {"$exists": True}})
        if sa_any:
            print(f"Found: {sa_any.get('title')}")
            if "_id" in sa_any: del sa_any["_id"]
            print(json.dumps(sa_any, indent=2, cls=JSONEncoder))
        else:
            print("No Shulchan Arukh with schema found")

    client.close()

if __name__ == "__main__":
    asyncio.run(research())
