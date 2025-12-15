import sys
import os
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from motor.motor_asyncio import AsyncIOMotorClient

BASE_DIR = Path(__file__).resolve().parents[1]
TREE_FILE = BASE_DIR / "sefaria_tree.json"


def load_tree() -> List[Dict[str, Any]]:
    if TREE_FILE.exists():
        with open(TREE_FILE, "r") as f:
            return json.load(f)
    raise FileNotFoundError(f"Tree file not found: {TREE_FILE}")


def slim_node(node: Dict[str, Any]) -> Dict[str, Any]:
    keys = ["title", "heTitle", "ref", "slug", "type"]
    return {k: node.get(k) for k in keys if k in node}


def load_chunk_if_needed(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    if node.get("hasChildren") and not node.get("children") and node.get("slug"):
        slug = node["slug"]
        chunk_file = BASE_DIR / "library_chunks" / f"{slug}.json"
        if chunk_file.exists():
            with open(chunk_file, "r") as f:
                children = json.load(f)
                node["children"] = children
                return children
    return node.get("children") or []


def traverse_tree(
    nodes: List[Dict[str, Any]],
    path: List[str],
    path_he: List[str],
    parent_info: Optional[Dict[str, Any]],
    parent_siblings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    records = []
    
    for node in nodes:
        ref = node.get("ref")
        if ref:
            record = {
                "_id": ref,
                "ref": ref,
                "title": node.get("title"),
                "heTitle": node.get("heTitle"),
                "type": node.get("type"),
                "slug": node.get("slug"),
                "path": path.copy(),
                "path_he": path_he.copy(),
                "he_ref": node.get("he_ref") or node.get("heRef"),
                "parent": slim_node(parent_info) if parent_info else None,
                "siblings": [slim_node(n) for n in parent_siblings],
            }
            records.append(record)
        
        children = load_chunk_if_needed(node)
        if children:
            new_path = path + [node.get("title", "")]
            new_path_he = path_he + [node.get("heTitle", "")]
            child_records = traverse_tree(
                children,
                new_path,
                new_path_he,
                node,
                children,
            )
            records.extend(child_records)
    
    return records


async def populate_siblings_collection():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_uri)
    db = client["sefaria"]
    collection = db["library_siblings"]
    
    print("Loading tree...")
    tree = load_tree()
    
    print("Traversing tree to build sibling records...")
    records = traverse_tree(tree, [], [], None, tree)
    
    print(f"Generated {len(records)} records")
    
    print("Dropping existing collection...")
    await collection.drop()
    
    print("Inserting records in batches...")
    if records:
        batch_size = 5000
        total_inserted = 0
        
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            await collection.insert_many(batch, ordered=False)
            total_inserted += len(batch)
            print(f"  Inserted {total_inserted}/{len(records)} records ({(total_inserted/len(records)*100):.1f}%)")
    
    print("Creating index on ref...")
    await collection.create_index("ref", unique=True)
    
    print(f"Successfully populated {len(records)} records")
    
    client.close()


if __name__ == "__main__":
    asyncio.run(populate_siblings_collection())
