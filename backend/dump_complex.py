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
    
    # Find a complex document with nodes
    print("=== Complex Document with Nodes ===")
    complex_doc = await index_col.find_one({"schema.nodes": {"$exists": True}})
    if complex_doc:
        print(f"Title: {complex_doc.get('title')}")
        if "_id" in complex_doc: del complex_doc["_id"]
        print(json.dumps(complex_doc, indent=2, cls=JSONEncoder))

    client.close()

if __name__ == "__main__":
    asyncio.run(research())
