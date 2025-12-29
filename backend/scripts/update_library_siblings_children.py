import sys
import os
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from pymongo import UpdateOne
from urllib.parse import quote_plus

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


def get_updates(
    nodes: List[Dict[str, Any]],
) -> List[UpdateOne]:
    updates = []
    
    for node in nodes:
        ref = node.get("ref")
        children = load_chunk_if_needed(node)
        
        if ref:
            slim_children = [slim_node(c) for c in children]
            updates.append(UpdateOne(
                {"_id": ref},
                {"$set": {"children": slim_children}}
            ))
        
        if children:
            child_updates = get_updates(children)
            updates.extend(child_updates)
    
    return updates


async def update_library_siblings():
    uri = f"mongodb://daniel:Hjsjfk74jkffdDF@155.138.219.192:27017/sefaria?authSource=admin"

    client = AsyncIOMotorClient(uri)
    db = client["sefaria"]
    collection = db["library_siblings"]
    
    print("Loading tree...")
    tree = load_tree()
    
    print("Traversing tree to generate children updates...")
    updates = get_updates(tree)
    
    print(f"Generated {len(updates)} updates")
    
    if updates:
        batch_size = 5000
        total_updated = 0
        
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]
            result = await collection.bulk_write(batch, ordered=False)
            total_updated += result.modified_count
            print(f"  Processed {min(i + batch_size, len(updates))}/{len(updates)} updates. Modified: {total_updated}")
    
    print(f"Successfully updated {total_updated} records with children lists.")
    
    client.close()


if __name__ == "__main__":
    asyncio.run(update_library_siblings())
