import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

from dotenv import load_dotenv
load_dotenv("backend/.env")

from app.services.library.tree_builder import TreeBuilder

async def test_expansion():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_uri)
    db = client["talmudpedia"]
    
    # Get Genesis
    genesis_idx = await db["index"].find_one({"title": "Genesis"})
    
    # Get Berakhot
    berakhot_idx = await db["index"].find_one({"title": "Berakhot"})
    
    builder = TreeBuilder()
    
    # Test Genesis expansion
    genesis_node = {
        "id": "Genesis",
        "title": "Genesis",
        "type": "book",
        "categories": ["Tanakh", "Torah"],
        "ref": "Genesis",
        "children": []
    }
    
    print("Testing Genesis expansion...")
    builder.expand_children(genesis_node, genesis_idx or {})
    print(f"Genesis children count: {len(genesis_node['children'])}")
    if genesis_node['children']:
        print(f"First 3: {[c['title'] for c in genesis_node['children'][:3]]}")
    
    # Test Berakhot expansion
    berakhot_node = {
        "id": "Berakhot",
        "title": "Berakhot",
        "type": "book",
        "categories": ["Talmud", "Bavli", "Seder Zeraim"],
        "ref": "Berakhot",
        "children": []
    }
    
    print("\nTesting Berakhot expansion...")
    builder.expand_children(berakhot_node, berakhot_idx or {})
    print(f"Berakhot children count: {len(berakhot_node['children'])}")
    if berakhot_node['children']:
        print(f"First 3: {[c['title'] for c in berakhot_node['children'][:3]]}")

if __name__ == "__main__":
    asyncio.run(test_expansion())
