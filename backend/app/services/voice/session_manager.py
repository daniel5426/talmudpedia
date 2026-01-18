"""
Voice session manager - PostgreSQL implementation.

Manages voice chat sessions, buffering messages and persisting
to PostgreSQL database.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from app.db.postgres.models.chat import Chat, Message, MessageRole
from app.db.postgres.engine import sessionmaker as async_sessionmaker


class VoiceSessionManager:
    """Manages voice session state and persistence to PostgreSQL."""
    
    def __init__(self, db: AsyncSession, user_id: UUID, tenant_id: UUID, chat_id: Optional[UUID] = None):
        self.db = db
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.chat_id = chat_id
        self.buffered_messages: List[Dict[str, Any]] = []

    async def load_chat_history(self) -> List[BaseMessage]:
        """Load chat history as LangChain messages."""
        if not self.chat_id:
            return []

        try:
            query = select(Chat).where(
                Chat.id == self.chat_id,
                Chat.user_id == self.user_id,
                Chat.tenant_id == self.tenant_id
            )
            result = await self.db.execute(query)
            chat = result.scalar_one_or_none()
            
            if not chat:
                return []

            # Load messages
            msg_query = select(Message).where(
                Message.chat_id == self.chat_id
            ).order_by(Message.index)
            msg_result = await self.db.execute(msg_query)
            db_messages = msg_result.scalars().all()
            
            messages: List[BaseMessage] = []
            for msg in db_messages:
                if msg.role == MessageRole.SYSTEM:
                    messages.append(SystemMessage(content=msg.content))
                elif msg.role == MessageRole.USER:
                    messages.append(HumanMessage(content=msg.content))
                elif msg.role == MessageRole.ASSISTANT:
                    messages.append(AIMessage(content=msg.content))

            return messages
        except Exception as e:
            print(f"Error loading chat history: {e}")
            return []

    async def ensure_chat(self) -> UUID:
        """Ensure a chat exists, creating one if necessary."""
        if self.chat_id:
            query = select(Chat).where(
                Chat.id == self.chat_id,
                Chat.user_id == self.user_id,
                Chat.tenant_id == self.tenant_id
            )
            result = await self.db.execute(query)
            existing = result.scalar_one_or_none()
            if existing:
                return self.chat_id

        # Create new chat
        chat = Chat(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            title="Voice Conversation",
        )
        self.db.add(chat)
        await self.db.commit()
        await self.db.refresh(chat)
        self.chat_id = chat.id
        return self.chat_id

    def buffer_message(
        self,
        role: str,
        content: str,
        citations: Optional[List[Dict[str, Any]]] = None,
        reasoning_steps: Optional[List[Dict[str, Any]]] = None
    ):
        """Buffer a message for later saving."""
        message_data = {
            "role": role,
            "content": content,
            "citations": citations or [],
            "reasoning_steps": reasoning_steps or [],
            "created_at": datetime.utcnow()
        }
        self.buffered_messages.append(message_data)

    async def save_buffered_messages(self):
        """Save all buffered messages to database."""
        if not self.buffered_messages:
            return

        await self.ensure_chat()

        # Get current max index
        max_idx_query = select(func.max(Message.index)).where(Message.chat_id == self.chat_id)
        result = await self.db.execute(max_idx_query)
        current_max = result.scalar() or -1

        for i, msg_data in enumerate(self.buffered_messages):
            role_map = {
                "user": MessageRole.USER,
                "assistant": MessageRole.ASSISTANT,
                "system": MessageRole.SYSTEM,
                "tool": MessageRole.TOOL,
            }
            role = role_map.get(msg_data["role"], MessageRole.USER)
            
            # Store citations/reasoning in tool_calls JSONB if present
            tool_calls = None
            if msg_data.get("citations") or msg_data.get("reasoning_steps"):
                tool_calls = {
                    "citations": msg_data.get("citations", []),
                    "reasoning_steps": msg_data.get("reasoning_steps", []),
                }
            
            message = Message(
                chat_id=self.chat_id,
                role=role,
                content=msg_data["content"],
                index=current_max + 1 + i,
                tool_calls=tool_calls,
            )
            self.db.add(message)

        await self.db.commit()
        self.buffered_messages.clear()

    async def finalize_session(self):
        """Finalize session: save messages and update chat title."""
        await self.save_buffered_messages()
        
        if not self.chat_id:
            return
            
        # Update title based on first user message
        query = select(Chat).where(Chat.id == self.chat_id)
        result = await self.db.execute(query)
        chat = result.scalar_one_or_none()
        
        if chat and chat.title == "Voice Conversation":
            # Get first user message
            msg_query = select(Message).where(
                Message.chat_id == self.chat_id,
                Message.role == MessageRole.USER
            ).order_by(Message.index).limit(1)
            msg_result = await self.db.execute(msg_query)
            first_msg = msg_result.scalar_one_or_none()
            
            if first_msg:
                new_title = first_msg.content[:50]
                if len(first_msg.content) > 50:
                    new_title += "..."
                chat.title = new_title
                await self.db.commit()


# Factory function for creating session manager with its own db session
async def create_voice_session_manager(
    user_id: UUID,
    tenant_id: UUID,
    chat_id: Optional[UUID] = None
) -> VoiceSessionManager:
    """Create a VoiceSessionManager with a new database session."""
    db = async_sessionmaker()
    session = await db.__aenter__()
    return VoiceSessionManager(session, user_id, tenant_id, chat_id)
