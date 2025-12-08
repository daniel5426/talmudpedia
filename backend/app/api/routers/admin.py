from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from bson import ObjectId
from app.db.models.user import User
from app.db.models.chat import Chat
from app.db.connection import MongoDatabase
from app.api.routers.auth import get_current_user
from pydantic import BaseModel


router = APIRouter()

async def get_admin_user(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None

@router.get("/stats")
async def get_admin_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    admin: User = Depends(get_admin_user)
):
    db = MongoDatabase.get_db()
    
    # 1. Total Active Users (Last 7 Days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    active_users_count = await db.chats.distinct("user_id", {"updated_at": {"$gte": seven_days_ago}})
    total_active_users = len(active_users_count)

    # 2. Total Conversations
    total_chats = await db.chats.count_documents({})

    # 3. Total Messages
    message_count_pipeline = [
        {"$project": {"count": {"$size": "$messages"}}},
        {"$group": {"_id": None, "total": {"$sum": "$count"}}}
    ]
    message_count_result = await db.chats.aggregate(message_count_pipeline).to_list(1)
    total_messages = message_count_result[0]["total"] if message_count_result else 0

    # 4. Avg Messages/Chat
    avg_messages_per_chat = round(total_messages / total_chats, 1) if total_chats > 0 else 0

    # 5. Token Usage (Estimate: 1 token ~= 4 chars)
    # This is a rough estimate based on message content length
    token_usage_pipeline = [
        {"$unwind": "$messages"},
        {"$project": {"length": {"$strLenCP": "$messages.content"}}},
        {"$group": {"_id": None, "total_chars": {"$sum": "$length"}}}
    ]
    token_usage_result = await db.chats.aggregate(token_usage_pipeline).to_list(1)
    total_chars = token_usage_result[0]["total_chars"] if token_usage_result else 0
    estimated_tokens = total_chars // 4

    # 6. Daily Active Users - with date range support
    if start_date and end_date:
        try:
            if 'T' in start_date:
                start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            else:
                start = datetime.strptime(start_date, "%Y-%m-%d")
            if 'T' in end_date:
                end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            else:
                end = datetime.strptime(end_date, "%Y-%m-%d")
                end = end.replace(hour=23, minute=59, second=59)
        except Exception as e:
            end = datetime.utcnow()
            start = end - timedelta(days=180)
    else:
        end = datetime.utcnow()
        start = end - timedelta(days=180)
    
    dau_pipeline = [
        {"$match": {"updated_at": {"$gte": start, "$lte": end}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$updated_at"}},
            "users": {"$addToSet": "$user_id"}
        }},
        {"$project": {
            "date": "$_id",
            "count": {"$size": "$users"},
            "_id": 0
        }},
        {"$sort": {"date": 1}}
    ]
    daily_active_users = await db.chats.aggregate(dau_pipeline).to_list(None)

    # 7. New Users (Last 7 Days)
    new_users_count = await db.users.count_documents({"created_at": {"$gte": seven_days_ago}})

    # 8. Chat Volume Trend - with date range support
    chat_volume_pipeline = [
        {"$match": {"created_at": {"$gte": start, "$lte": end}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "chats": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    daily_chat_stats = []
    async for doc in db.chats.aggregate(chat_volume_pipeline):
        daily_chat_stats.append({
            "date": doc["_id"],
            "chats": doc["chats"]
        })

    # 9. Top Active Users (by message count)
    top_users_pipeline = [
        {"$unwind": "$messages"},
        {"$group": {"_id": "$user_id", "message_count": {"$sum": 1}}},
        {"$sort": {"message_count": -1}},
        {"$limit": 5}
    ]
    top_users_data = await db.chats.aggregate(top_users_pipeline).to_list(None)
    top_users = []
    for user_data in top_users_data:
        if user_data["_id"]:
            user = await db.users.find_one({"_id": ObjectId(user_data["_id"])})
            if user:
                top_users.append({
                    "email": user.get("email"),
                    "count": user_data["message_count"]
                })

    # 10. Recent Chats
    latest_chats_cursor = db.chats.find({}, {"messages": 0}).sort("created_at", -1).limit(5)
    latest_chats = []
    async for doc in latest_chats_cursor:
        chat_data = doc
        chat_data["id"] = str(chat_data["_id"])
        del chat_data["_id"]
        if chat_data.get("user_id"):
            user = await db.users.find_one({"_id": ObjectId(chat_data["user_id"])})
            if user:
                chat_data["user_email"] = user.get("email")
        latest_chats.append(chat_data)
        
    total_users = await db.users.count_documents({})

    return {
        "total_users": total_users,
        "total_active_users": total_active_users,
        "total_chats": total_chats,
        "total_messages": total_messages,
        "avg_messages_per_chat": avg_messages_per_chat,
        "estimated_tokens": estimated_tokens,
        "new_users_last_7_days": new_users_count,
        "daily_active_users": daily_active_users,
        "daily_stats": daily_chat_stats,
        "top_users": top_users,
        "latest_chats": latest_chats
    }

@router.post("/users/bulk-delete")
async def bulk_delete_users(user_ids: List[str], admin: User = Depends(get_admin_user)):
    db = MongoDatabase.get_db()
    try:
        object_ids = [ObjectId(uid) for uid in user_ids]
        result = await db.users.delete_many({"_id": {"$in": object_ids}})
        # Also delete their chats
        await db.chats.delete_many({"user_id": {"$in": user_ids}})
        return {"deleted_count": result.deleted_count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/chats/bulk-delete")
async def bulk_delete_chats(chat_ids: List[str], admin: User = Depends(get_admin_user)):
    db = MongoDatabase.get_db()
    try:
        object_ids = [ObjectId(cid) for cid in chat_ids]
        result = await db.chats.delete_many({"_id": {"$in": object_ids}})
        return {"deleted_count": result.deleted_count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/users")
async def get_users(
    skip: int = 0, 
    limit: int = 20, 
    search: Optional[str] = None,
    admin: User = Depends(get_admin_user)
):
    db = MongoDatabase.get_db()
    query: Dict[str, Any] = {}
    if search:
        query["$or"] = [
            {"email": {"$regex": search, "$options": "i"}},
            {"full_name": {"$regex": search, "$options": "i"}}
        ]
    
    cursor = db.users.find(query).skip(skip).limit(limit)
    users = []
    async for doc in cursor:
        user = User(**doc)
        user_dict = user.model_dump(by_alias=False)
        user_dict["id"] = str(user.id)
        users.append(user_dict)
    
    total = await db.users.count_documents(query)
    
    return {
        "items": users,
        "total": total,
        "page": skip // limit + 1,
        "pages": (total + limit - 1) // limit
    }

@router.get("/chats")
async def get_chats(
    skip: int = 0, 
    limit: int = 20, 
    search: Optional[str] = None,
    admin: User = Depends(get_admin_user)
):
    db = MongoDatabase.get_db()
    query: Dict[str, Any] = {}
    if search:
        query["title"] = {"$regex": search, "$options": "i"}
        
    cursor = db.chats.find(query).sort("updated_at", -1).skip(skip).limit(limit)
    chats = []
    async for doc in cursor:
        chat = Chat(**doc)
        chat_dict = chat.model_dump(by_alias=False)
        chat_dict["id"] = str(chat.id)
        chats.append(chat_dict)
    
    total = await db.chats.count_documents(query)
    
    return {
        "items": chats,
        "total": total,
        "page": skip // limit + 1,
        "pages": (total + limit - 1) // limit
    }

@router.get("/users/{user_id}")
async def get_user_details(user_id: str, admin: User = Depends(get_admin_user)):
    db = MongoDatabase.get_db()
    try:
        user_doc = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user_doc:
            raise HTTPException(status_code=404, detail="User not found")
        user = User(**user_doc)
        user_dict = user.model_dump(by_alias=False)
        user_dict["id"] = str(user.id)
        
        user_chats_count = await db.chats.count_documents({"user_id": user_id})
        
        return {
            "user": user_dict,
            "stats": {
                "chats_count": user_chats_count,
                "tokens_used_this_month": user.token_usage
            }
        }
    except Exception:
        raise HTTPException(status_code=404, detail="User not found")

@router.patch("/users/{user_id}")
async def update_user(
    user_id: str, 
    user_update: UserUpdate,
    admin: User = Depends(get_admin_user)
):
    db = MongoDatabase.get_db()
    try:
        update_data = {k: v for k, v in user_update.model_dump().items() if v is not None}
        if not update_data:
            return {"message": "No changes provided"}
            
        result = await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
            
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/users/{user_id}/chats")
async def get_user_chats(
    user_id: str,
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    admin: User = Depends(get_admin_user)
):
    db = MongoDatabase.get_db()
    query: Dict[str, Any] = {"user_id": user_id}
    if search:
        query["title"] = {"$regex": search, "$options": "i"}
        
    cursor = db.chats.find(query).sort("updated_at", -1).skip(skip).limit(limit)
    chats = []
    async for doc in cursor:
        chat = Chat(**doc)
        chat_dict = chat.model_dump(by_alias=False)
        chat_dict["id"] = str(chat.id)
        chats.append(chat_dict)
    
    total = await db.chats.count_documents(query)
    
    return {
        "items": chats,
        "total": total,
        "page": skip // limit + 1,
        "pages": (total + limit - 1) // limit
    }
