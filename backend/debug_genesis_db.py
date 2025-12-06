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
    index_col = db["index"]
    
    # Check Genesis documents
    count = 0
    async for doc in index_col.find({"title": "Genesis"}):
        count += 1
        print(f"\n=== Genesis Document {count} ===")
        print(f"Has schema: {'schema' in doc}")
        print(f"Has shape: {'shape' in doc}")
        if 'schema' in doc:
            schema = doc['schema']
            print(f"Schema keys: {schema.keys() if isinstance(schema, dict) else 'Not a dict'}")
            if isinstance(schema, dict):
                print(f"nodeType: {schema.get('nodeType')}")
                print(f"lengths: {schema.get('lengths')}")

    client.close()

if __name__ == "__main__":
    asyncio.run(research())
