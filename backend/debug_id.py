import asyncio
import httpx
from app.db.connection import MongoDatabase
from app.db.models.chat import Chat

async def debug_api():
    # We can't easily run the full FastAPI app here without uvicorn, 
    # but we can test the model serialization directly.
    
    await MongoDatabase.connect()
    db = MongoDatabase.get_db()
    
    # Fetch one chat directly from DB
    doc = await db.chats.find_one()
    if doc:
        print("Raw Mongo Doc:", doc)
        chat_obj = Chat(**doc)
        print("Pydantic Object:", chat_obj)
        print("Serialized (model_dump):", chat_obj.model_dump())
        print("Serialized (model_dump_json):", chat_obj.model_dump_json())
        print("Serialized (by_alias=True):", chat_obj.model_dump(by_alias=True))
    else:
        print("No chats found in DB.")
        
    await MongoDatabase.close()

if __name__ == "__main__":
    asyncio.run(debug_api())
