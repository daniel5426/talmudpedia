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
    
    print("\n--- Full Document: Genesis ---")
    genesis = await index_col.find_one({"title": "Genesis"})
    if genesis:
        # Remove _id for cleaner printing
        if "_id" in genesis:
            del genesis["_id"]
        print(json.dumps(genesis, indent=2, cls=JSONEncoder))
    else:
        print("Genesis not found")

    client.close()

if __name__ == "__main__":
    asyncio.run(research())
