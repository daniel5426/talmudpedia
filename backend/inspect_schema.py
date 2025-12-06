import asyncio
import sys
import os
from unittest.mock import MagicMock

# Add backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

# MOCK PROBLEM MODULES
sys.modules["app.agent"] = MagicMock()
sys.modules["app.agent.factory"] = MagicMock()
sys.modules["app.endpoints.agent"] = MagicMock()

from app.db.connection import MongoDatabase

def print_node_recursive(node, indent=0):
    space = "  " * indent
    print(f"{space}Key: {node.get('key')}, Type: {node.get('nodeType')}, Depth: {node.get('depth')}")
    if "nodes" in node:
        for child in node["nodes"]:
            print_node_recursive(child, indent + 1)

async def main():
    await MongoDatabase.connect()
    db = MongoDatabase.get_db()
    
    index = await db.index.find_one({'title': 'Sefer Mitzvot Gadol'})
    if index and "schema" in index:
        print("Schema Structure:")
        print_node_recursive(index["schema"])
    else:
        print("SMG Index not found")

if __name__ == "__main__":
    asyncio.run(main())
