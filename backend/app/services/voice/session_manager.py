from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from app.db.connection import MongoDatabase
from app.db.models.chat import Chat, Message, Citation


class VoiceSessionManager:
    def __init__(self, user_id: str, chat_id: Optional[str] = None):
        self.user_id = user_id
        self.chat_id = chat_id
        self.buffered_messages: List[Dict[str, Any]] = []
        self.db = MongoDatabase.get_db()

    async def load_chat_history(self) -> List[BaseMessage]:
        if not self.chat_id:
            return []

        try:
            chat_doc = await self.db.chats.find_one({"_id": ObjectId(self.chat_id), "user_id": self.user_id})
            if not chat_doc:
                return []

            chat = Chat(**chat_doc)
            messages: List[BaseMessage] = []

            for msg in chat.messages:
                if msg.role == "system":
                    messages.append(SystemMessage(content=msg.content))
                elif msg.role == "user":
                    messages.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    messages.append(AIMessage(content=msg.content))

            return messages
        except Exception as e:
            print(f"Error loading chat history: {e}")
            return []

    async def ensure_chat(self) -> str:
        if self.chat_id:
            existing = await self.db.chats.find_one({"_id": ObjectId(self.chat_id), "user_id": self.user_id})
            if existing:
                return self.chat_id

        chat = Chat(
            title="Voice Conversation",
            user_id=self.user_id
        )
        result = await self.db.chats.insert_one(chat.model_dump(by_alias=True, exclude={"id"}))
        self.chat_id = str(result.inserted_id)
        return self.chat_id

    def buffer_message(self, role: str, content: str, citations: Optional[List[Dict[str, Any]]] = None, reasoning_steps: Optional[List[Dict[str, Any]]] = None):
        message_data = {
            "role": role,
            "content": content,
            "citations": citations or [],
            "reasoning_steps": reasoning_steps or [],
            "created_at": datetime.utcnow()
        }
        self.buffered_messages.append(message_data)

    async def save_buffered_messages(self):
        if not self.buffered_messages:
            return

        await self.ensure_chat()

        messages_to_save = []
        for msg_data in self.buffered_messages:
            citations = [Citation(**c) if isinstance(c, dict) else c for c in msg_data.get("citations", [])]
            
            message = Message(
                role=msg_data["role"],
                content=msg_data["content"],
                citations=citations if citations else None,
                reasoning_steps=msg_data.get("reasoning_steps"),
                created_at=msg_data.get("created_at", datetime.utcnow())
            )
            messages_to_save.append(message.model_dump())

        if messages_to_save:
            await self.db.chats.update_one(
                {"_id": ObjectId(self.chat_id)},
                {
                    "$push": {"messages": {"$each": messages_to_save}},
                    "$set": {"updated_at": datetime.utcnow()}
                }
            )

        self.buffered_messages.clear()

    async def finalize_session(self):
        await self.save_buffered_messages()
        
        if self.chat_id:
            chat_doc = await self.db.chats.find_one({"_id": ObjectId(self.chat_id)})
            if chat_doc:
                chat = Chat(**chat_doc)
                if chat.title == "Voice Conversation" and chat.messages:
                    first_user_message = next((m for m in chat.messages if m.role == "user"), None)
                    if first_user_message:
                        new_title = first_user_message.content[:50] + ("..." if len(first_user_message.content) > 50 else "")
                        await self.db.chats.update_one(
                            {"_id": ObjectId(self.chat_id)},
                            {"$set": {"title": new_title}}
                        )
