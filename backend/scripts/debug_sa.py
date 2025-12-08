import asyncio
import os
import sys
import json
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

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
    
    # Check Shulchan Arukh, Even HaEzer
    print("=== Shulchan Arukh, Even HaEzer ===")
    sa_eh = await index_col.find_one({"title": "Shulchan Arukh, Even HaEzer", "schema": {"$exists": True}})
    if sa_eh:
        if "_id" in sa_eh: del sa_eh["_id"]
        
        # Print just the schema
        schema = sa_eh.get("schema", {})
        print(f"NodeType: {schema.get('nodeType')}")
        print(f"Has nodes: {'nodes' in schema}")
        
        if "nodes" in schema:
            print(f"Number of nodes: {len(schema['nodes'])}")
            for i, node in enumerate(schema['nodes']):
                print(f"\nNode {i}:")
                print(f"  Title: {node.get('title')}")
                print(f"  HeTitle: {node.get('heTitle')}")
                print(f"  NodeType: {node.get('nodeType')}")
                print(f"  Default: {node.get('default', False)}")
                if node.get('nodeType') == 'JaggedArrayNode':
                    print(f"  Lengths: {node.get('lengths')}")
    
    # Compare with Orach Chayim
    print("\n\n=== Shulchan Arukh, Orach Chayim ===")
    sa_oc = await index_col.find_one({"title": "Shulchan Arukh, Orach Chayim", "schema": {"$exists": True}})
    if sa_oc:
        if "_id" in sa_oc: del sa_oc["_id"]
        
        schema = sa_oc.get("schema", {})
        print(f"NodeType: {schema.get('nodeType')}")
        print(f"Has nodes: {'nodes' in schema}")
        print(f"Lengths: {schema.get('lengths')}")
        
        if "nodes" in schema:
            print(f"Number of nodes: {len(schema['nodes'])}")

    client.close()

if __name__ == "__main__":
    asyncio.run(research())
