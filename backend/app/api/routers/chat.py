from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends

from app.db.connection import MongoDatabase
from app.db.models.chat import Chat
from app.db.models.user import User
from app.api.routers.auth import get_current_user

router = APIRouter()

@router.get("", response_model_by_alias=False)
async def get_chats(
    limit: int = 20, 
    cursor: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Returns chats ordered by last update with optional cursor paging."""
    db = MongoDatabase.get_db()
    query: Dict[str, Any] = {"user_id": str(current_user.id)}
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

@router.get("/{chat_id}", response_model_by_alias=False)
async def get_chat_history(
    chat_id: str,
    current_user: User = Depends(get_current_user)
):
    """Returns the full message history for a chat."""
    db = MongoDatabase.get_db()
    try:
        query = {"_id": ObjectId(chat_id)}
        if current_user.role != "admin":
            query["user_id"] = str(current_user.id)
        doc = await db.chats.find_one(query)
        if doc:
            chat = Chat(**doc)
            chat_dict = chat.model_dump(by_alias=False)
            chat_dict["id"] = str(chat.id)
            return chat_dict
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="Chat not found")

@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user)
):
    """Deletes a chat thread by identifier."""
    db = MongoDatabase.get_db()
    result = await db.chats.delete_one({"_id": ObjectId(chat_id), "user_id": str(current_user.id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"status": "deleted"}

@router.patch("/{chat_id}/messages/{message_index}")
async def update_message_feedback(
    chat_id: str,
    message_index: int,
    liked: Optional[bool] = None,
    disliked: Optional[bool] = None,
    current_user: User = Depends(get_current_user)
):
    """Updates the feedback (like/dislike) for a specific message."""
    db = MongoDatabase.get_db()
    try:
        query = {"_id": ObjectId(chat_id)}
        if current_user.role != "admin":
            query["user_id"] = str(current_user.id)
        
        # Build update fields
        update_fields = {}
        if liked is not None:
            update_fields[f"messages.{message_index}.liked"] = liked
        if disliked is not None:
            update_fields[f"messages.{message_index}.disliked"] = disliked
        
        if not update_fields:
            raise HTTPException(status_code=400, detail="No feedback provided")
        
        result = await db.chats.update_one(
            query,
            {"$set": update_fields}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        return {"status": "updated"}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{chat_id}/messages/last-assistant")
async def delete_last_assistant_message(
    chat_id: str,
    current_user: User = Depends(get_current_user)
):
    """Deletes the last assistant message from a chat (for retry functionality)."""
    db = MongoDatabase.get_db()
    try:
        query = {"_id": ObjectId(chat_id)}
        if current_user.role != "admin":
            query["user_id"] = str(current_user.id)
        
        # Get the chat
        chat_doc = await db.chats.find_one(query)
        if not chat_doc:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        chat = Chat(**chat_doc)
        
        # Find the last assistant message
        last_assistant_index = None
        for i in range(len(chat.messages) - 1, -1, -1):
            if chat.messages[i].role == "assistant":
                last_assistant_index = i
                break
        
        if last_assistant_index is None:
            raise HTTPException(status_code=404, detail="No assistant message found")
        
        # Remove the message
        chat.messages.pop(last_assistant_index)
        
        # Update the database
        await db.chats.update_one(
            query,
            {
                "$set": {
                    "messages": [msg.model_dump() for msg in chat.messages],
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        return {"status": "deleted", "message_index": last_assistant_index}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
