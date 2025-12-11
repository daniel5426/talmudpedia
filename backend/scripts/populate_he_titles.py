import asyncio
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

def load_book_map(chunks_dir: Path):
    book_map = {}
    for path in chunks_dir.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        def walk(nodes):
            for node in nodes:
                node_type = node.get("type")
                if node_type == "book":
                    title = node.get("title")
                    he_title = node.get("heTitle")
                    if title and he_title:
                        book_map[title] = he_title
                children = node.get("children") or []
                if children:
                    walk(children)
        walk(data if isinstance(data, list) else [])
    return book_map

async def main():
    sys.path.append(os.getcwd())
    sys.path.append(os.path.join(os.getcwd(), "backend"))
    env_path = Path(os.getcwd()) / "backend" / ".env"
    load_dotenv(env_path)
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGO_DB_NAME", "sefaria")
    chunks_dir = Path(os.getcwd()) / "backend" / "library_chunks"
    if not chunks_dir.exists():
        print("library_chunks directory not found")
        return
    book_map = load_book_map(chunks_dir)
    if not book_map:
        print("no book mapping loaded")
        return
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]
    coll = db["texts"]
    total = 0
    updated = 0
    async for doc in coll.find({}, {"title": 1, "heTitle": 1}):
        total += 1
        if doc.get("heTitle"):
            continue
        title = doc.get("title")
        he_title = book_map.get(title)
        if not he_title:
            continue
        res = await coll.update_one({"_id": doc["_id"]}, {"$set": {"heTitle": he_title}})
        if res.modified_count:
            updated += 1
    print(f"processed {total} docs, updated {updated}")
    client.close()

if __name__ == "__main__":
    asyncio.run(main())

