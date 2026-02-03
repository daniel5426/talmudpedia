from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import logging
import json
import asyncio
from uuid import UUID
import jwt
from sqlalchemy import select

from app.db.postgres.session import sessionmaker
from app.db.postgres.models.chat import Chat
from app.db.postgres.models.identity import OrgMembership, Tenant
from app.core.security import SECRET_KEY, ALGORITHM
from app.services.voice import get_voice_session

router = APIRouter()
logger = logging.getLogger(__name__)

async def resolve_auth_context(db, user_id: str):
    """Resolve tenant_id for a user."""
    if not user_id:
        # Fallback for dev: first tenant
        res = await db.execute(select(Tenant).limit(1))
        t = res.scalar_one_or_none()
        return t.id if t else None
    
    user_uuid = UUID(user_id)
    # Get first membership
    stmt = select(OrgMembership).where(OrgMembership.user_id == user_uuid).limit(1)
    res = await db.execute(stmt)
    membership = res.scalar_one_or_none()
    if membership:
        return membership.tenant_id
        
    # Fallback to first tenant
    res = await db.execute(select(Tenant).limit(1))
    t = res.scalar_one_or_none()
    return t.id if t else None

@router.websocket("/session")
async def websocket_voice_session(websocket: WebSocket):
    """
    WebSocket endpoint for Voice Session.
    Supports multiple providers via registry.
    """
    await websocket.accept()
    
    chat_id = websocket.query_params.get("chat_id")
    token = websocket.query_params.get("token")
    provider = websocket.query_params.get("provider", "gemini") # Default to gemini
    
    user_id = None
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
        except Exception:
            user_id = None
    
    tenant_id = None
    async with sessionmaker() as db:
        tenant_id = await resolve_auth_context(db, user_id)
        
        # Create new chat if not provided
        if not chat_id or chat_id == "null" or chat_id == "undefined":
            new_chat = Chat(
                title="Voice Conversation",
                user_id=UUID(user_id) if user_id else None,
                tenant_id=tenant_id
            )
            db.add(new_chat)
            await db.commit()
            await db.refresh(new_chat)
            chat_id = str(new_chat.id)
            logger.info(f"Created new voice chat: {chat_id} for tenant: {tenant_id}")
        else:
            # Validate chat access
            try:
                chat_uuid = UUID(chat_id)
                stmt = select(Chat).where(Chat.id == chat_uuid)
                res = await db.execute(stmt)
                existing = res.scalar_one_or_none()
                if existing:
                    if existing.user_id and user_id and existing.user_id != UUID(user_id):
                        await websocket.close(code=1008, reason="forbidden")
                        return
                    # Ensure tenant_id is set if it was missing (for migration)
                    if not existing.tenant_id and tenant_id:
                        existing.tenant_id = tenant_id
                        await db.commit()
                else:
                    await websocket.close(code=1008, reason="invalid chat_id")
                    return
            except ValueError:
                await websocket.close(code=1008, reason="invalid chat_id")
                return

    # Initialize Voice Session via Registry
    try:
        voice_session = get_voice_session(
            provider, 
            chat_id=chat_id, 
            tenant_id=tenant_id, 
            user_id=UUID(user_id) if user_id else None
        )
    except Exception as e:
        logger.error(f"Failed to initialize voice provider {provider}: {e}")
        await websocket.close(code=1011, reason=f"Provider {provider} not found")
        return

    try:
        # Notify frontend of setup
        await websocket.send_json({
            "type": "setup_complete",
            "chat_id": chat_id,
            "provider": provider
        })

        # Connect to provider
        await voice_session.connect(frontend_ws=websocket)
        logger.info(f"Connected to voice provider: {provider}")
        
        # Start background task to receive from provider and send to Frontend
        receive_task = asyncio.create_task(voice_session.receive_loop(websocket))
        
        # Loop for receiving from Frontend
        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if message.get("type") == "audio":
                    await voice_session.send_audio(message.get("data"))
                elif message.get("type") == "user_text":
                    t = message.get("text") or message.get("content") or ""
                    await voice_session.send_user_text(t, turn_complete=True)
                
        except WebSocketDisconnect:
            logger.info("Frontend WebSocket disconnected")
        except Exception as e:
            logger.error(f"Error in frontend receive loop: {e}")
            
        # Cleanup
        receive_task.cancel()
        
    except Exception as e:
        logger.error(f"Voice Session failed: {e}")
        reason = str(e)[:120] if e else "session failed"
        try:
            await websocket.close(code=1011, reason=reason)
        except Exception:
            pass
    finally:
        await voice_session.close()
