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
SEARCH_FILE = BASE_DIR / "library_chunks" / "search_index.json"


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return cleaned or "item"


def load_search_index() -> List[Dict[str, Any]]:
    if not SEARCH_FILE.exists():
        raise FileNotFoundError(f"Missing {SEARCH_FILE}")
    with open(SEARCH_FILE, "r") as f:
        raw = json.load(f)
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    cleaned: List[Dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, str):
            try:
                entry = json.loads(entry)
            except Exception:
                continue
        if not isinstance(entry, dict):
            continue
        title = entry.get("title") or ""
        he_title = entry.get("heTitle") or ""
        ref = entry.get("ref") or ""
        he_ref = entry.get("heRef") or ""
        slug = entry.get("slug") or slugify(title or ref or he_title or he_ref)
        path = entry.get("path") or []
        path_he = entry.get("path_he") or []
        path_str = " / ".join(path)
        path_he_str = " / ".join(path_he)
        cleaned.append({
            "title": title,
            "heTitle": he_title,
            "ref": ref,
            "heRef": he_ref,
            "slug": slug,
            "path": path,
            "path_he": path_he,
            "path_str": path_str,
            "path_he_str": path_he_str,
            "type": entry.get("type"),
            "score": entry.get("score"),
            "version": SEARCH_FILE.stat().st_mtime,
        })
    return cleaned


async def populate_search_collection():
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_uri)
    db = client["sefaria"]
    collection = db["library_search"]

    entries = load_search_index()
    print(f"Loaded {len(entries)} search rows")

    await collection.drop()
    if entries:
        batch_size = 5000
        total = 0
        for i in range(0, len(entries), batch_size):
            batch = entries[i:i + batch_size]
            await collection.insert_many(batch, ordered=False)
            total += len(batch)
            print(f"Inserted {total}/{len(entries)} ({(total/len(entries))*100:.1f}%)")

    await collection.create_index("ref", sparse=True)
    await collection.create_index("slug", sparse=True)
    await collection.create_index([("title", "text"), ("heTitle", "text"), ("ref", "text"), ("heRef", "text"), ("path_str", "text"), ("path_he_str", "text")])

    latest_version = SEARCH_FILE.stat().st_mtime
    await collection.replace_one({"_id": "__meta__"}, {"_id": "__meta__", "version": latest_version}, upsert=True)

    client.close()
    print("Done")


if __name__ == "__main__":
    asyncio.run(populate_search_collection())
