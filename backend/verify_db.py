import asyncio
import os
from app.db.connection import MongoDatabase
from app.db.models.sefaria import Index, Text, Link
from app.db.models.chat import Chat

async def verify():
    print("Connecting to database...")
    await MongoDatabase.connect()
    db = MongoDatabase.get_db()
    
    print("Testing Chat model...")
    chat = Chat(title="Test Chat")
    res = await db.chats.insert_one(chat.model_dump(by_alias=True, exclude={"id"}))
    print(f"Inserted Chat ID: {res.inserted_id}")
    
    print("Testing Sefaria models...")
    index = Index(title="Test Index", categories=["Test"], schema={"node": "test"})
    res_idx = await db.index.insert_one(index.model_dump(by_alias=True, exclude={"id"}))
    print(f"Inserted Index ID: {res_idx.inserted_id}")
    
    text = Text(title="Test Index", versionTitle="Test Version", language="en", chapter=["Test content"])
    res_txt = await db.texts.insert_one(text.model_dump(by_alias=True, exclude={"id"}))
    print(f"Inserted Text ID: {res_txt.inserted_id}")
    
    link = Link(refs=["Test Index 1", "Test Index 2"], type="commentary")
    res_lnk = await db.links.insert_one(link.model_dump(by_alias=True, exclude={"id"}))
    print(f"Inserted Link ID: {res_lnk.inserted_id}")
    
    print("Cleaning up...")
    await db.chats.delete_one({"_id": res.inserted_id})
    await db.index.delete_one({"_id": res_idx.inserted_id})
    await db.texts.delete_one({"_id": res_txt.inserted_id})
    await db.links.delete_one({"_id": res_lnk.inserted_id})
    
    await MongoDatabase.close()
    print("Verification complete.")

if __name__ == "__main__":
    asyncio.run(verify())
