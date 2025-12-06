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
    
    print("\n--- Leviticus Schema ---")
    lev = await index_col.find_one({"title": "Leviticus"}, {"schema": 1})
    if lev:
        print(json.dumps(lev, indent=2, cls=JSONEncoder))
        
        # Check titles in schema
        schema = lev.get("schema", {})
        titles = schema.get("titles", [])
        print("\nTitles in Schema:")
        for t in titles:
            print(t)
            
        # Check section names
        print(f"\nSection Names: {schema.get('sectionNames')}")
        print(f"Depth: {schema.get('depth')}")
    
    print("\n--- Berakhot Schema (Talmud) ---")
    ber = await index_col.find_one({"title": "Berakhot"}, {"schema": 1})
    if ber:
        # Just print structure summary
        schema = ber.get("schema", {})
        print(f"Node Type: {schema.get('nodeType')}")
        print(f"Depth: {schema.get('depth')}")
        print(f"Section Names: {schema.get('sectionNames')}")
        print(f"Titles: {schema.get('titles')}")

    client.close()

if __name__ == "__main__":
    asyncio.run(research())
