from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException

from app.db.connection import MongoDatabase
from app.db.models.chat import Chat


class ChatEndpoints:
    router = APIRouter(prefix="/chats", tags=["chats"])

    @staticmethod
    @router.get("", response_model_by_alias=False)
    async def get_chats(limit: int = 20, cursor: Optional[str] = None):
        """Returns chats ordered by last update with optional cursor paging."""
        db = MongoDatabase.get_db()
        query: Dict[str, Any] = {}
        if cursor:
            try:
                cursor_time = datetime.fromisoformat(cursor)
                query["updated_at"] = {"$lt": cursor_time}
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid cursor value")
        db_cursor = db.chats.find(query).sort("updated_at", -1).limit(limit)
        chats = []
        last_timestamp: Optional[datetime] = None
        async for doc in db_cursor:
            chat = Chat(**doc)
            chat_dict = chat.model_dump(by_alias=False)
            chat_dict["id"] = str(chat.id)
            chats.append(chat_dict)
            last_timestamp = chat.updated_at
        next_cursor = last_timestamp.isoformat() if last_timestamp and len(chats) == limit else None
        return {"items": chats, "nextCursor": next_cursor}

    @staticmethod
    @router.get("/{chat_id}", response_model_by_alias=False)
    async def get_chat_history(chat_id: str):
        """Returns the full message history for a chat."""
        db = MongoDatabase.get_db()
        try:
            doc = await db.chats.find_one({"_id": ObjectId(chat_id)})
            if doc:
                chat = Chat(**doc)
                chat_dict = chat.model_dump(by_alias=False)
                chat_dict["id"] = str(chat.id)
                return chat_dict
        except Exception:
            pass
        raise HTTPException(status_code=404, detail="Chat not found")

    @staticmethod
    @router.delete("/{chat_id}")
    async def delete_chat(chat_id: str):
        """Deletes a chat thread by identifier."""
        db = MongoDatabase.get_db()
        result = await db.chats.delete_one({"_id": ObjectId(chat_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Chat not found")
        return {"status": "deleted"}

