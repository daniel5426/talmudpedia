from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import logging
from app.services.gemini_live import GeminiLiveSession
import json
import asyncio
from uuid import UUID
from datetime import datetime
import jwt
from sqlalchemy import select

from app.db.postgres.session import sessionmaker
from app.db.postgres.models.chat import Chat
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
            user_id = payload.get("sub") # user_id is a UUID string
        except Exception:
            user_id = None
    
    # Create new chat if not provided
    if not chat_id or chat_id == "null" or chat_id == "undefined":
        async with sessionmaker() as db:
            new_chat = Chat(
                title="Voice Conversation",
                user_id=UUID(user_id) if user_id else None
            )
            db.add(new_chat)
            await db.commit()
            await db.refresh(new_chat)
            chat_id = str(new_chat.id)
        logger.info(f"Created new voice chat: {chat_id}")
    else:
        if user_id:
            async with sessionmaker() as db:
                try:
                    chat_uuid = UUID(chat_id)
                    stmt = select(Chat).where(Chat.id == chat_uuid)
                    res = await db.execute(stmt)
                    existing = res.scalar_one_or_none()
                    if existing:
                        if existing.user_id and existing.user_id != UUID(user_id):
                            await websocket.close(code=1008, reason="forbidden")
                            return
                        if not existing.user_id:
                            existing.user_id = UUID(user_id)
                            await db.commit()
                except ValueError:
                    await websocket.close(code=1008, reason="invalid chat_id")
                    return
        
    gemini_session = GeminiLiveSession(chat_id=chat_id)
    
    try:
        # Notify frontend of chat_id
        await websocket.send_json({
            "type": "setup_complete",
            "chat_id": chat_id
        })

        # Connect to Gemini
        await gemini_session.connect(frontend_ws=websocket)
        logger.info("Connected to Gemini Bidi Service")
        
        # Start background task to receive from Gemini and send to Frontend
        receive_task = asyncio.create_task(gemini_session.receive_loop(websocket))
        
        # Loop for receiving from Frontend
        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if message.get("type") == "audio":
                    await gemini_session.send_audio(message.get("data"))
                elif message.get("type") == "user_text":
                    t = message.get("text") or message.get("content") or ""
                    await gemini_session.send_user_text(t, turn_complete=True)
                
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
