import os
import asyncio
import json
import base64
import traceback
import logging
from typing import AsyncGenerator, Dict, Any, List, Optional
from datetime import datetime
from uuid import UUID, uuid4

import websockets
from fastapi import WebSocket
from sqlalchemy import select, func

from app.db.postgres.models.chat import Chat, Message, MessageRole
from app.db.postgres.engine import sessionmaker as async_sessionmaker
from app.services.retrieval_service import RetrievalService
from app.services.voice.base import BaseVoiceSession
from app.services.voice.registry import VoiceProviderRegistry

logger = logging.getLogger(__name__)

# region agent log
_AGENT_DEBUG_LOG_PATH = "/Users/danielbenassaya/Code/personal/talmudpedia/.cursor/debug.log"
_AGENT_DEBUG_SESSION_ID = "debug-session"
_AGENT_DEBUG_RUN_ID = f"run_{uuid4().hex[:8]}"

def _agent_log(hypothesisId: str, location: str, message: str, data: Dict[str, Any]):
    try:
        payload = {
            "sessionId": _AGENT_DEBUG_SESSION_ID,
            "runId": _AGENT_DEBUG_RUN_ID,
            "hypothesisId": hypothesisId,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(asyncio.get_event_loop().time() * 1000),
        }
        with open(_AGENT_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
# endregion

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
HOST = "generativelanguage.googleapis.com"
MODEL = "gemini-2.5-flash-native-audio-preview-12-2025" 
URI = f"wss://{HOST}/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key={GEMINI_API_KEY}"

ENABLE_GEMINI_TOOLS = True
GEMINI_TOOLS = [
    {
        "functionDeclarations": [
            {
                "name": "retrieve_sources",
                "description": "Search Rabbinic texts (Talmud, Halakhah, etc.) for relevant information. Use this whenever the user asks a question that requires knowledge from Jewish texts.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "query": {
                            "type": "STRING",
                            "description": "The search query to find relevant texts.",
                        }
                    },
                    "required": ["query"],
                },
            }
        ]
    }
]

class GeminiVoiceSession(BaseVoiceSession):
    """
    Gemini-specific implementation of a voice session.
    Adapted from gemini_live.py to fit the provider-agnostic architecture.
    """
    
    def __init__(self, chat_id: Optional[str] = None, tenant_id: Optional[UUID] = None, user_id: Optional[UUID] = None, knowledge_store_id: Optional[UUID] = None):
        super().__init__(chat_id=chat_id, tenant_id=tenant_id, user_id=user_id)
        self.ws = None
        self.knowledge_store_id = knowledge_store_id
        self.current_ai_text = ""
        self.current_user_text = ""
        self._last_input_transcription = ""
        self._last_output_transcription = ""
        self._last_saved_user_text = ""
        self._send_lock = asyncio.Lock()
        self._tool_tasks: set[asyncio.Task] = set()
        self._pending_citations: List[Dict[str, Any]] = []
        self._pending_reasoning_steps: List[Dict[str, Any]] = []
        self.is_connected = False

    async def connect(self, frontend_ws: WebSocket):
        self.frontend_ws = frontend_ws
        try:
            self.ws = await websockets.connect(URI)
            self.is_connected = True
            
            # Fetch history for context
            history_turns = await self._get_history_context()
            history_text = self._format_history_for_system_instruction(history_turns)
            
            setup_msg = {
                "setup": {
                    "model": f"models/{MODEL}",
                    "tools": GEMINI_TOOLS if ENABLE_GEMINI_TOOLS else [],
                    "input_audio_transcription": {},
                    "output_audio_transcription": {},
                    "generation_config": {
                        "response_modalities": ["AUDIO"],
                        "speech_config": {
                            "voice_config": {
                                "prebuilt_voice_config": {
                                    "voice_name": "Puck"
                                }
                            }
                        },
                    },
                    "system_instruction": {
                        "parts": [
                            {
                                "text": "Answer with the actual spoken response only. Do not include reasoning, analysis, or meta commentary. Be concise."
                            }
                        ]
                    }
                }
            }
            if history_text:
                setup_msg["setup"]["system_instruction"]["parts"][0]["text"] += f"\n\nConversation so far:\n{history_text}"

            await self._ws_send_json(setup_msg, "setup")
            
            raw_init_resp = await self.ws.recv()
            initial_resp = json.loads(raw_init_resp)
            
            if "error" in initial_resp:
                raise Exception(f"Gemini Setup Failed: {initial_resp['error']}")
            
            await self._handle_gemini_message(initial_resp)
            
        except Exception as e:
            logger.error(f"Failed to connect to Gemini: {e}")
            raise

    async def send_audio(self, audio_chunk_base64: str):
        if not self.is_connected: return
        msg = {
            "realtime_input": {
                "media_chunks": [{"data": audio_chunk_base64, "mime_type": "audio/pcm;rate=16000"}]
            },
        }
        await self._ws_send_json(msg, "audio")

    async def send_user_text(self, text: str, turn_complete: bool = True):
        if not self.is_connected: return
        t = (text or "").strip()
        if not t: return
        await self._save_message("user", t)
        await self._ws_send_json({
            "client_content": {
                "turns": [{"role": "user", "parts": [{"text": t}]}],
                "turn_complete": bool(turn_complete)
            }
        }, "user_text")

    async def receive_loop(self, frontend_ws: WebSocket):
        try:
            self.frontend_ws = frontend_ws
            async for raw_msg in self.ws:
                msg = json.loads(raw_msg)
                await self._handle_gemini_message(msg)
        except Exception as e:
            logger.error(f"Error in receive loop: {e}")

    async def close(self):
        ai = (self.current_ai_text or "").strip()
        if ai:
            await self._save_message("assistant", ai, citations=self._pending_citations or None, reasoning_steps=self._pending_reasoning_steps or None)
        usr = (self.current_user_text or "").strip()
        if usr and usr != self._last_saved_user_text:
            await self._save_message("user", usr)
        if self.ws:
            await self.ws.close()

    # Private helpers adapted from gemini_live.py
    async def _ws_send_json(self, payload: Dict[str, Any], label: str):
        if not self.ws: return
        async with self._send_lock:
            await self.ws.send(json.dumps(payload))

    async def _handle_gemini_message(self, msg: Dict[str, Any]):
        if "error" in msg:
            logger.error(f"Gemini Error: {msg}")

        # Handle tool calls
        tool_call = msg.get("toolCall") or msg.get("tool_call")
        if not tool_call:
            server_content = msg.get("serverContent")
            if server_content:
                tool_call = server_content.get("toolCall") or server_content.get("tool_call")
        
        if tool_call and ENABLE_GEMINI_TOOLS:
            await self._handle_tool_call(tool_call)

        # Handle audio
        audio_data = msg.get("data")
        if audio_data and self.frontend_ws:
            await self.frontend_ws.send_json({"type": "audio", "data": audio_data})

        # Handle transcriptions and model turns (Simplified for brevity but maintaining logic)
        server_content = msg.get("serverContent")
        if server_content:
            # Transcription handling... (same as gemini_live.py)
            input_transcription = server_content.get("inputTranscription") or server_content.get("input_transcription")
            if input_transcription:
                self.current_user_text = self._merge_partial_text(self.current_user_text, input_transcription.get("text", ""))
            
            output_transcription = server_content.get("outputTranscription") or server_content.get("output_transcription")
            if output_transcription:
                await self._flush_user_message()
                t = output_transcription.get("text", "")
                self.current_ai_text = self._merge_partial_text(self.current_ai_text, t)
                if self.frontend_ws:
                    await self.frontend_ws.send_json({"type": "live_text", "role": "assistant", "content": self.current_ai_text, "is_final": False})

            # Model turn...
            model_turn = server_content.get("modelTurn")
            if model_turn:
                await self._flush_user_message()
                for part in model_turn.get("parts", []):
                    if "inlineData" in part:
                        audio = part["inlineData"].get("data")
                        if audio and self.frontend_ws:
                            await self.frontend_ws.send_json({"type": "audio", "data": audio})
                    if "text" in part:
                        self.current_ai_text += part["text"]

            if server_content.get("turnComplete") or server_content.get("turn_complete"):
                if self.current_ai_text:
                    await self._save_message("assistant", self.current_ai_text, citations=self._pending_citations or None, reasoning_steps=self._pending_reasoning_steps or None)
                    if self.frontend_ws:
                        await self.frontend_ws.send_json({"type": "live_text", "role": "assistant", "content": self.current_ai_text, "is_final": True})
                    self.current_ai_text = ""
                    self._last_output_transcription = ""
                    self._pending_citations = []
                    self._pending_reasoning_steps = []

    async def _handle_tool_call(self, tool_call):
        function_calls = tool_call.get("functionCalls") or tool_call.get("function_calls") or []
        for call in function_calls:
            task = asyncio.create_task(self._run_tool_call(call))
            self._tool_tasks.add(task)
            task.add_done_callback(self._tool_tasks.discard)

    async def _run_tool_call(self, call):
        name = call.get("name")
        args = call.get("args") or {}
        call_id = call.get("id")
        
        if name != "retrieve_sources": return

        query = args.get("query", "").strip()
        if self.frontend_ws:
            await self.frontend_ws.send_json({"type": "live_tool", "tool": "retrieve_sources", "status": "pending", "query": query})

        # USE RETRIEVAL SERVICE
        async with async_sessionmaker() as db:
            retrieval_service = RetrievalService(db)
            citations = []
            result_text = ""
            try:
                # Resolve store_id if not provided
                store_id = self.knowledge_store_id
                if not store_id:
                     from app.db.postgres.models import KnowledgeStore
                     stmt = select(KnowledgeStore).where(KnowledgeStore.tenant_id == self.tenant_id).limit(1)
                     res = await db.execute(stmt)
                     ks = res.scalar_one_or_none()
                     if ks: store_id = ks.id
                
                if store_id:
                    results = await retrieval_service.query(store_id, query, top_k=3)
                    for r in results:
                        citations.append({"title": r.metadata.get("ref", "Source"), "description": r.text, "ref": r.metadata.get("ref")})
                    result_text = "\n\n".join([f"{c['title']}: {c['description']}" for c in citations])
                else:
                    result_text = "No knowledge store configured for retrieval."
            except Exception as e:
                logger.error(f"Retrieval error: {e}")
                result_text = f"Error retrieving: {e}"

        if citations:
            self._pending_citations = citations
            self._pending_reasoning_steps = [{"step": "Retrieval", "status": "complete", "citations": citations, "query": query}]

        if self.frontend_ws:
            await self.frontend_ws.send_json({"type": "live_tool", "tool": "retrieve_sources", "status": "complete", "query": query, "citations": citations})

        resp_msg = {
            "toolResponse": {
                "functionResponses": [{"id": call_id, "name": name, "response": {"output": result_text}}]
            }
        }
        await self._ws_send_json(resp_msg, f"toolResponse:{name}")

    async def _save_message(self, role: str, content: str, citations=None, reasoning_steps=None):
        if not self.chat_id or not content: return
        try:
            async with async_sessionmaker() as db:
                chat_uuid = UUID(self.chat_id)
                max_idx_query = select(func.max(Message.index)).where(Message.chat_id == chat_uuid)
                result = await db.execute(max_idx_query)
                current_max = result.scalar() or -1
                
                role_map = {"user": MessageRole.USER, "assistant": MessageRole.ASSISTANT}
                msg_role = role_map.get(role, MessageRole.USER)
                
                tool_calls = {}
                if citations: tool_calls["citations"] = citations
                if reasoning_steps: tool_calls["reasoning_steps"] = reasoning_steps

                message = Message(chat_id=chat_uuid, role=msg_role, content=content, index=current_max + 1, tool_calls=tool_calls or None)
                db.add(message)
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to save message: {e}")

    async def _get_history_context(self) -> List[Dict[str, Any]]:
        if not self.chat_id: return []
        try:
            async with async_sessionmaker() as db:
                chat_uuid = UUID(self.chat_id)
                msg_query = select(Message).where(Message.chat_id == chat_uuid).order_by(Message.index.desc()).limit(10)
                msg_result = await db.execute(msg_query)
                messages = list(msg_result.scalars().all())
                messages.reverse()
                turns = []
                for msg in messages:
                    role = "user" if msg.role == MessageRole.USER else "model"
                    turns.append({"role": role, "parts": [{"text": msg.content}]})
                if turns and turns[-1]["role"] == "user": turns.pop()
                return turns
        except Exception: return []

    def _format_history_for_system_instruction(self, turns: List[Dict[str, Any]]) -> str:
        out = []
        for t in turns:
            who = "User" if t["role"] == "user" else "Assistant"
            text = " ".join([p.get("text", "") for p in t["parts"]])
            out.append(f"{who}: {text}")
        return "\n".join(out)

    def _merge_partial_text(self, current: str, incoming: str) -> str:
        if not incoming: return current
        if not current: return incoming
        if incoming.startswith(current): return incoming
        return f"{current} {incoming}"

    async def _flush_user_message(self):
        if self.current_user_text and self.current_user_text != self._last_saved_user_text:
            await self._save_message("user", self.current_user_text)
            self._last_saved_user_text = self.current_user_text
            if self.frontend_ws:
                await self.frontend_ws.send_json({"type": "live_text", "role": "user", "content": self.current_user_text, "is_final": True})
            self.current_user_text = ""

# Register the provider
VoiceProviderRegistry.register("gemini", GeminiVoiceSession)
