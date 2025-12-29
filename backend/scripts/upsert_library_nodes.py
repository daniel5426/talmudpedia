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
    keys = ["title", "heTitle", "ref", "slug", "type", "hasChildren"]
    res = {k: node.get(k) for k in keys if k in node}
    if node.get("children"):
        res["hasChildren"] = True
    return res


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


def get_upsert_ops(
    nodes: List[Dict[str, Any]],
    path: List[str],
    path_he: List[str],
    parent_info: Optional[Dict[str, Any]],
    parent_siblings: List[Dict[str, Any]],
) -> List[UpdateOne]:
    ops = []
    
    for node in nodes:
        children = load_chunk_if_needed(node)
        doc_id = node.get("ref") or node.get("slug") or node.get("title")
        if not doc_id:
            continue

        record = {
            "title": node.get("title"),
            "heTitle": node.get("heTitle"),
            "type": node.get("type"),
            "path": path.copy(),
            "path_he": path_he.copy(),
            "he_ref": node.get("he_ref") or node.get("heRef"),
            "hasChildren": node.get("hasChildren") or len(children) > 0,
            "parent": slim_node(parent_info) if parent_info else None,
            "siblings": [slim_node(n) for n in parent_siblings],
            "children": [slim_node(c) for c in children],
        }
        
        if node.get("ref"):
            record["ref"] = node["ref"]
        if node.get("slug"):
            record["slug"] = node["slug"]
        
        ops.append(UpdateOne(
            {"_id": doc_id},
            {"$set": record},
            upsert=True
        ))
        
        if children:
            new_path = path + [node.get("title", "")]
            new_path_he = path_he + [node.get("heTitle", "")]
            child_ops = get_upsert_ops(
                children,
                new_path,
                new_path_he,
                node,
                children,
            )
            ops.extend(child_ops)
    
    return ops


async def upsert_library_nodes():
    user = "daniel"
    password = "Hjsjfk74jkffdDF"
    ip = "155.138.219.192"
    db_name = "sefaria"

    uri = f"mongodb://{quote_plus(user)}:{quote_plus(password)}@{ip}:27017/{db_name}?authSource=admin"
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    collection = db["library_siblings"]
    
    print("Loading tree...")
    tree = load_tree()
    
    print("Traversing tree to generate upsert operations...")
    ops = get_upsert_ops(tree, [], [], None, tree)
    
    print(f"Generated {len(ops)} upsert operations")
    
    print("Cleaning up indices...")
    try:
        await collection.drop_index("ref_1")
    except Exception:
        pass
    try:
        await collection.drop_index("slug_1")
    except Exception:
        pass

    if ops:
        batch_size = 2000
        total_processed = 0
        
        for i in range(0, len(ops), batch_size):
            batch = ops[i:i + batch_size]
            await collection.bulk_write(batch, ordered=False)
            total_processed += len(batch)
            print(f"  Processed {total_processed}/{len(ops)} records ({(total_processed/len(ops)*100):.1f}%)")
    
    print("Creating index on ref...")
    await collection.create_index("ref", sparse=True)
    print("Creating index on slug...")
    await collection.create_index("slug", sparse=True)
    print("Creating index on path...")
    await collection.create_index("path")
    
    print(f"Successfully upserted {len(ops)} records")
    
    client.close()


if __name__ == "__main__":
    asyncio.run(upsert_library_nodes())
