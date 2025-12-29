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


def slim_node(node: Dict[str, Any], path: List[str] = []) -> Dict[str, Any]:
    if not node:
        return None
    
    # Use ref or slug if available, otherwise construct the path-based ID we use in MongoDB
    node_id = node.get("ref") or node.get("slug") or node.get("title")
    path_str = "/".join(path)
    doc_id = f"{path_str}/{node_id}" if path_str else node_id

    keys = ["title", "heTitle", "ref", "slug", "type", "hasChildren"]
    res = {k: node.get(k) for k in keys if k in node}
    
    # Fallback for slug so the frontend always has an identifier
    if not res.get("slug"):
        res["slug"] = node.get("ref") or doc_id
        
    if node.get("children") or node.get("hasChildren"):
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


def get_records(
    nodes: List[Dict[str, Any]],
    path: List[str] = [],
    path_he: List[str] = [],
    parent_info: Optional[Dict[str, Any]] = None,
    records_dict: Dict[str, Dict[str, Any]] = None
) -> Dict[str, Dict[str, Any]]:
    if records_dict is None:
        records_dict = {}
    
    # Pre-slim siblings for the current level
    slim_siblings = [slim_node(n, path) for n in nodes]
    slim_parent = slim_node(parent_info, path[:-1]) if parent_info else None
    
    for node in nodes:
        children = load_chunk_if_needed(node)
        
        node_id = node.get("ref") or node.get("slug") or node.get("title")
        if not node_id:
            continue
            
        path_str = "/".join(path)
        doc_id = f"{path_str}/{node_id}" if path_str else node_id

        record = {
            "title": node.get("title"),
            "heTitle": node.get("heTitle"),
            "type": node.get("type"),
            "path": path,
            "path_he": path_he,
            "he_ref": node.get("he_ref") or node.get("heRef"),
            "hasChildren": node.get("hasChildren") or len(children) > 0,
            "parent": slim_parent,
            "siblings": slim_siblings,
            "children": [slim_node(c, path + [node.get("title", "")]) for c in children],
        }
        
        if node.get("ref"): record["ref"] = node["ref"]
        if node.get("slug"): record["slug"] = node["slug"]
        
        # Use a dict to automatically handle any duplicates in the source files
        records_dict[doc_id] = record
        
        if children:
            get_records(
                children,
                path + [node.get("title", "")],
                path_he + [node.get("heTitle", "")],
                node,
                records_dict
            )
    
    return records_dict


async def populate_library_nodes():
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
    
    print("Generating unique records in memory...")
    records_dict = get_records(tree)
    records = list(records_dict.items())
    print(f"Generated {len(records)} unique records")
    
    print("Dropping existing collection...")
    await collection.drop()
    
    print("Inserting records in large batches...")
    if records:
        batch_size = 5000
        total = len(records)
        for i in range(0, total, batch_size):
            batch = records[i:i + batch_size]
            ops = [
                UpdateOne({"_id": doc_id}, {"$set": record}, upsert=True)
                for doc_id, record in batch
            ]
            await collection.bulk_write(ops, ordered=False)
            print(f"  Processed {min(i + batch_size, total)}/{total} records ({(min(i + batch_size, total)/total*100):.1f}%)")
    
    print("Creating indices...")
    await asyncio.gather(
        collection.create_index("ref", sparse=True),
        collection.create_index("slug", sparse=True),
        collection.create_index("path")
    )
    
    print(f"Successfully populated {len(records)} records")
    client.close()


if __name__ == "__main__":
    asyncio.run(populate_library_nodes())
