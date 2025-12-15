from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import logging
from app.services.gemini_live import GeminiLiveSession
import json
import asyncio
from app.db.connection import MongoDatabase
from app.db.models.chat import Chat
from datetime import datetime
from bson import ObjectId
import jwt
from app.core.security import SECRET_KEY, ALGORITHM

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/session")
async def websocket_voice_session(websocket: WebSocket):
    """
    WebSocket endpoint for Gemini Live Voice Session.
    Client <-> Backend <-> Gemini
    """
    await websocket.accept()
    logger.info(f"New Voice Session WebSocket connected chat_id={websocket.query_params.get('chat_id')}")
    
    chat_id = websocket.query_params.get("chat_id")
    token = websocket.query_params.get("token")
    user_id = None
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
        except Exception:
            user_id = None
    
    # Create new chat if not provided
    if not chat_id or chat_id == "null" or chat_id == "undefined":
        db = MongoDatabase.get_db()
        new_chat = Chat(
            title="Voice Conversation",
            messages=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            user_id=str(user_id) if user_id else None
        )
        result = await db.chats.insert_one(new_chat.model_dump(by_alias=True, exclude=["id"]))
        chat_id = str(result.inserted_id)
        logger.info(f"Created new voice chat: {chat_id}")
    else:
        if user_id:
            db = MongoDatabase.get_db()
            existing = await db.chats.find_one({"_id": ObjectId(chat_id)})
            if existing:
                existing_user_id = existing.get("user_id")
                if existing_user_id and existing_user_id != str(user_id):
                    await websocket.close(code=1008, reason="forbidden")
                    return
                if not existing_user_id:
                    await db.chats.update_one({"_id": ObjectId(chat_id)}, {"$set": {"user_id": str(user_id)}})
        
    gemini_session = GeminiLiveSession(chat_id=chat_id)
    
    try:
        # Notify frontend of chat_id
        await websocket.send_json({
            "type": "setup_complete",
            "chat_id": chat_id
        })

        # Connect to Gemini
        await gemini_session.connect()
        logger.info("Connected to Gemini Bidi Service")
        
        # Start background task to receive from Gemini and send to Frontend
        receive_task = asyncio.create_task(gemini_session.receive_loop(websocket))
        
        # Loop for receiving from Frontend
        try:
            while True:
                # Expecting JSON with {type: "audio", data: "base64..."} or other controls
                # Or raw bytes if we decide to optimize
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if message.get("type") == "audio":
                    a = message.get("data") or ""
                    logger.debug(f"Voice WS RX audio bytes={len(a)}")
                    await gemini_session.send_audio(message.get("data"))
                elif message.get("type") == "user_text":
                    t = message.get("text") or message.get("content") or ""
                    logger.info(f"Voice WS RX user_text len={len((t or '').strip())}")
                    await gemini_session.send_user_text(t, turn_complete=True)
                
                # Handle other types if needed (e.g. interrupt)
                
        except WebSocketDisconnect:
            logger.info("Frontend WebSocket disconnected")
        except Exception as e:
            logger.error(f"Error in frontend receive loop: {e}")
            
        # Cleanup
        receive_task.cancel()
        
    except Exception as e:
        logger.error(f"Session failed: {e}")
        reason = str(e) if e is not None else "session failed"
        if len(reason) > 120:
            reason = reason[:120]
        try:
            await websocket.close(code=1011, reason=reason)
        except Exception:
            pass
    finally:
        await gemini_session.close()
