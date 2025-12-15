import sys
import os
import json
import asyncio
import re
from pathlib import Path
from typing import List, Dict, Any

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from motor.motor_asyncio import AsyncIOMotorClient

BASE_DIR = Path(__file__).resolve().parents[1]
TREE_FILE = BASE_DIR / "sefaria_tree.json"
CHUNK_DIR = BASE_DIR / "library_chunks"

def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return cleaned or "item"


def load_chunk(slug: str) -> List[Dict[str, Any]]:
    path = CHUNK_DIR / f"{slug}.json"
    if not path.exists():
        return []
    try:
        with open(path, "r") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def load_tree() -> List[Dict[str, Any]]:
    if TREE_FILE.exists():
        with open(TREE_FILE, "r") as f:
            return json.load(f)
    raise FileNotFoundError(f"Tree file not found: {TREE_FILE}")


def walk(nodes: List[Dict[str, Any]], path: List[str], path_he: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for node in nodes:
        node_path = path + [node.get("title", "")]
        node_path_he = path_he + [node.get("heTitle", "")]
        ref = node.get("ref")
        slug = node.get("slug") or slugify(node.get("title") or node.get("ref") or "")
        doc = {
            "title": node.get("title"),
            "heTitle": node.get("heTitle"),
            "ref": ref,
            "slug": slug,
            "type": node.get("type"),
            "path": path.copy(),
            "path_he": path_he.copy(),
            "path_str": " / ".join(node_path),
            "path_he_str": " / ".join(node_path_he),
        }
        if ref:
            doc["_id"] = ref
        out.append(doc)
        children = node.get("children") or []
        if not children and node.get("hasChildren") and node.get("slug"):
            children = load_chunk(node["slug"])
        if children:
            out.extend(walk(children, node_path, node_path_he))
    return out


async def populate_library_nodes():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_uri)
    db = client["sefaria"]
    collection = db["library_nodes"]

    tree = load_tree()
    docs = walk(tree, [], [])
    print(f"Loaded {len(docs)} nodes")

    seen_ids = set()
    seen_slugs = set()
    unique_docs = []
    for doc in docs:
        doc_id = doc.get("_id")
        base_slug = doc.get("slug") or slugify(doc.get("title") or doc.get("ref") or doc.get("path_str") or "")
        base_slug = base_slug or "item"
        slug = base_slug
        counter = 1
        while slug in seen_slugs:
            counter += 1
            slug = f"{base_slug}-{counter}"
        doc["slug"] = slug
        seen_slugs.add(slug)
        if doc_id:
            if doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)
        unique_docs.append(doc)

    print(f"After deduplication: {len(unique_docs)} nodes")

    await collection.drop()
    batch_size = 5000
    total = 0
    for i in range(0, len(unique_docs), batch_size):
        batch = unique_docs[i:i + batch_size]
        await collection.insert_many(batch, ordered=False)
        total += len(batch)
        print(f"Inserted {total}/{len(unique_docs)} ({(total/len(unique_docs))*100:.1f}%)")

    await collection.create_index("ref", sparse=True)
    await collection.create_index("slug", sparse=True, unique=True)
    await collection.create_index("path_str")
    await collection.create_index("path_he_str")

    client.close()
    print("Done")


if __name__ == "__main__":
    asyncio.run(populate_library_nodes())
