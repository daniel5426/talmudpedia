import asyncio
import os
import sys
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    sys.path.append(os.getcwd())
    sys.path.append(os.path.join(os.getcwd(), "backend"))
    env_path = os.path.join(os.getcwd(), "backend", ".env")
    load_dotenv(env_path)
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGO_DB_NAME", "sefaria")
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]

    index_total = await db.index.count_documents({})
    index_missing = await db.index.count_documents({"$or": [{"heTitle": {"$exists": False}}, {"heTitle": {"$in": [None, ""]}}]})
    texts_total = await db.texts.count_documents({})
    texts_with_he = await db.texts.count_documents({"heTitle": {"$exists": True}})
    texts_missing = texts_total - texts_with_he

    print(f"DB: {db_name}")
    print(f"index total: {index_total}, missing heTitle: {index_missing}")
    print(f"texts total: {texts_total}, with heTitle: {texts_with_he}, missing: {texts_missing}")

    missing_titles = await db.texts.distinct("title", {"heTitle": {"$exists": False}})
    print(f"titles missing heTitle in texts: {len(missing_titles)}")
    for title in missing_titles[:20]:
        idx = await db.index.find_one({"title": title}, {"heTitle": 1})
        he_title = idx.get("heTitle") if idx else None
        print(f"- {title} | index.heTitle={he_title}")

    sample_with_he = await db.texts.find_one({"heTitle": {"$exists": True}})
    if sample_with_he:
        print("sample text with heTitle:", sample_with_he.get("title"), sample_with_he.get("versionTitle"))

    sample_missing = await db.texts.find_one({"heTitle": {"$exists": False}})
    if sample_missing:
        idx = await db.index.find_one({"title": sample_missing.get("title")}, {"heTitle": 1})
        he_title_idx = idx.get("heTitle") if idx else None
        print("sample text missing heTitle:", sample_missing.get("title"), sample_missing.get("versionTitle"), "index.heTitle", he_title_idx)

    client.close()

if __name__ == "__main__":
    asyncio.run(main())

