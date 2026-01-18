"""
Gemini Live Voice Session - PostgreSQL implementation.

Handles real-time voice interactions with Gemini, persisting
chat messages to PostgreSQL.
"""
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

from dotenv import load_dotenv
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.components.retrieval.vector import VectorRetriever
from app.db.postgres.models.chat import Chat, Message, MessageRole
from app.db.postgres.engine import sessionmaker as async_sessionmaker

# Robustly load .env from the backend root directory
backend_root = Path(__file__).resolve().parent.parent.parent
env_path = backend_root / ".env"
load_dotenv(env_path)

# Set up logging
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
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY not found in environment variables!")

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


class GeminiLiveSession:
    """Manages a live voice session with Gemini, using PostgreSQL for persistence."""
    
    def __init__(self, chat_id: Optional[UUID] = None, tenant_id: Optional[UUID] = None, user_id: Optional[UUID] = None):
        self.ws = None
        self.retriever = VectorRetriever()
        self.is_connected = False
        self.chat_id = chat_id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.frontend_ws = None
        self.current_ai_text = ""
        self.current_user_text = ""
        self._last_input_transcription = ""
        self._last_output_transcription = ""
        self._last_saved_user_text = ""
        self._send_lock = asyncio.Lock()
        self._tool_tasks: set[asyncio.Task] = set()
        self._pending_citations: List[Dict[str, Any]] = []
        self._pending_reasoning_steps: List[Dict[str, Any]] = []

    async def _get_db_session(self) -> AsyncSession:
        """Get a database session."""
        return await async_sessionmaker().__aenter__()

    async def _flush_user_message(self):
        """Save buffered user message to database."""
        if self.current_user_text and self.current_user_text != self._last_saved_user_text:
            await self._save_message("user", self.current_user_text, is_voice=True)
            self._last_saved_user_text = self.current_user_text
            if self.frontend_ws:
                await self.frontend_ws.send_json({
                    "type": "live_text",
                    "role": "user",
                    "content": self.current_user_text,
                    "is_final": True
                })
            self.current_user_text = ""

    def _format_history_for_system_instruction(self, turns: List[Dict[str, Any]]) -> str:
        """Format chat history for system instruction."""
        out: List[str] = []
        total = 0
        max_total = 6000
        max_piece = 1200
        for t in (turns or []):
            role = t.get("role")
            parts = t.get("parts") or []
            texts: List[str] = []
            for p in parts:
                v = (p or {}).get("text")
                if v is None:
                    continue
                if not isinstance(v, str):
                    v = str(v)
                v = "".join(ch for ch in v if ch in "\n\t\r" or ord(ch) >= 32).strip()
                if not v:
                    continue
                if len(v) > max_piece:
                    v = v[:max_piece]
                texts.append(v)
            if not texts:
                continue
            who = "User" if role == "user" else "Assistant"
            piece = f"{who}: {' '.join(texts)}"
            if total + len(piece) + 1 > max_total:
                break
            out.append(piece)
            total += len(piece) + 1
        return "\n".join(out).strip()

    async def _ws_send_json(self, payload: Dict[str, Any], label: str):
        """Send JSON to Gemini websocket."""
        if not self.ws:
            logger.error("ws_send_json called without ws")
            return
        _agent_log("C", "gemini_live.py:_ws_send_json", "sending", {"label": label, "topKeys": list(payload.keys())})
        started = asyncio.get_running_loop().time()
        async with self._send_lock:
            waited = asyncio.get_running_loop().time() - started
            if waited >= 0.5:
                logger.warning(f"Gemini ws send lock wait {waited:.3f}s label={label}")
            data = json.dumps(payload)
            logger.info(f"Gemini ws send label={label} bytes={len(data)}")
            try:
                await asyncio.wait_for(self.ws.send(data), timeout=6.0)
                _agent_log("C", "gemini_live.py:_ws_send_json", "sent", {"label": label, "bytes": len(data)})
            except asyncio.TimeoutError:
                logger.error(f"Gemini ws send timeout label={label} bytes={len(data)}")
                _agent_log("C", "gemini_live.py:_ws_send_json", "timeout", {"label": label, "bytes": len(data)})
                raise

    def _merge_partial_text(self, current: str, incoming: str) -> str:
        """Merge partial transcription text."""
        inc = (incoming or "").strip()
        if not inc:
            return (current or "").strip()
        cur = (current or "").strip()
        if not cur:
            return inc
        if inc.startswith(cur):
            return inc
        if cur.startswith(inc):
            return cur
        if inc in cur:
            return cur
        if cur in inc:
            return inc
        if cur.endswith(inc):
            return cur
        if inc.endswith(cur):
            return inc
        return f"{cur} {inc}"

    async def connect(self, frontend_ws=None):
        """Establishes connection to Gemini Bidi endpoint."""
        if frontend_ws:
            self.frontend_ws = frontend_ws

        try:
            self.ws = await websockets.connect(URI)
            self.is_connected = True
            
            # Fetch history for context
            history_turns = await self._get_history_context()
            history_text = self._format_history_for_system_instruction(history_turns)
            
            # Send initial setup message
            setup_msg = {
                "setup": {
                    "model": f"models/{MODEL}",
                    "tools": GEMINI_TOOLS if ENABLE_GEMINI_TOOLS else [],
                    "input_audio_transcription": {},
                    "output_audio_transcription": {},
                    "generation_config": {
                        "response_modalities": ["AUDIO"],
                        "thinking_config": {
                            "thinking_budget": 0,
                            "include_thoughts": False
                        },
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
                setup_msg["setup"]["system_instruction"]["parts"][0]["text"] = (
                    setup_msg["setup"]["system_instruction"]["parts"][0]["text"]
                    + "\n\nConversation so far:\n"
                    + history_text
                )

            _agent_log("D", "gemini_live.py:connect", "setup_pre_send", {"toolsEnabled": bool(ENABLE_GEMINI_TOOLS), "toolsCount": len(setup_msg["setup"].get("tools") or [])})
            await self._ws_send_json(setup_msg, "setup")
            
            # Read first response (setup complete or error)
            raw_init_resp = await self.ws.recv()
            initial_resp = json.loads(raw_init_resp)
            logger.info(f"Gemini Init Response: {initial_resp}")
            _agent_log("D", "gemini_live.py:connect", "setup_init_resp", {"topKeys": list(initial_resp.keys()), "hasError": "error" in initial_resp})
            
            # Check for errors in setup
            if "error" in initial_resp:
                logger.error(f"Gemini Setup Error: {initial_resp}")
                raise Exception(f"Gemini Setup Failed: {initial_resp['error']}")
            
            # Process the initial response as it might contain content (like initial audio)
            await self._handle_gemini_message(initial_resp)
            
        except Exception as e:
            logger.error(f"Failed to connect to Gemini: {e}")
            raise

    async def _get_history_context(self) -> List[Dict[str, Any]]:
        """Loads chat history for context from PostgreSQL."""
        if not self.chat_id:
            return []

        try:
            async with async_sessionmaker() as db:
                # Get chat
                query = select(Chat).where(Chat.id == self.chat_id)
                result = await db.execute(query)
                chat = result.scalar_one_or_none()
                
                if not chat:
                    return []

                # Get recent messages
                msg_query = select(Message).where(
                    Message.chat_id == self.chat_id
                ).order_by(Message.index.desc()).limit(10)
                
                msg_result = await db.execute(msg_query)
                messages = list(msg_result.scalars().all())
                messages.reverse()  # Oldest first
                
                turns = []
                for msg in messages:
                    role = "user" if msg.role == MessageRole.USER else "model"
                    if msg.content:
                        turns.append({
                            "role": role,
                            "parts": [{"text": msg.content}]
                        })
                
                # CRITICAL FIX: Ensure history does NOT end with a user turn.
                if turns and turns[-1]["role"] == "user":
                    logger.info("Dropping last user message from history to prevent setup crash.")
                    turns.pop()

                return turns

        except Exception as e:
            logger.error(f"Failed to get history: {e}")
            return []

    async def send_audio(self, audio_chunk_base64: str):
        """Sends audio chunk to Gemini."""
        if not self.is_connected:
            return

        msg = {
            "realtime_input": {
                "media_chunks": [
                    {
                        "data": audio_chunk_base64,
                        "mime_type": "audio/pcm;rate=16000"
                    }
                ]
            },
        }
        await self._ws_send_json(msg, "audio")

    async def send_user_text(self, text: str, turn_complete: bool = True):
        """Send user text message."""
        if not self.is_connected:
            return
        t = (text or "").strip()
        if not t:
            return
        await self._save_message("user", t)
        await self._ws_send_json({
            "client_content": {
                "turns": [
                    {"role": "user", "parts": [{"text": t}]}
                ],
                "turn_complete": bool(turn_complete)
            }
        }, "user_text")

    async def _save_message(
        self,
        role: str,
        content: str,
        citations: Optional[List[Dict[str, Any]]] = None,
        reasoning_steps: Optional[List[Dict[str, Any]]] = None,
        is_voice: bool = False,
    ):
        """Save message to PostgreSQL."""
        if not self.chat_id or not content:
            return
            
        try:
            async with async_sessionmaker() as db:
                # Get current max index
                max_idx_query = select(func.max(Message.index)).where(Message.chat_id == self.chat_id)
                result = await db.execute(max_idx_query)
                current_max = result.scalar() or -1
                
                role_map = {
                    "user": MessageRole.USER,
                    "assistant": MessageRole.ASSISTANT,
                    "system": MessageRole.SYSTEM,
                    "tool": MessageRole.TOOL,
                }
                msg_role = role_map.get(role, MessageRole.USER)
                
                # Store metadata in tool_calls JSONB
                tool_calls = None
                if citations or reasoning_steps or is_voice:
                    tool_calls = {}
                    if citations:
                        tool_calls["citations"] = citations
                    if reasoning_steps:
                        tool_calls["reasoning_steps"] = reasoning_steps
                    if is_voice:
                        tool_calls["is_voice"] = True
                
                message = Message(
                    chat_id=self.chat_id,
                    role=msg_role,
                    content=content,
                    index=current_max + 1,
                    tool_calls=tool_calls,
                )
                db.add(message)
                
                # Update chat updated_at
                chat_query = select(Chat).where(Chat.id == self.chat_id)
                chat_result = await db.execute(chat_query)
                chat = chat_result.scalar_one_or_none()
                if chat:
                    chat.updated_at = datetime.utcnow()
                
                await db.commit()
                logger.info(f"Saved {role} message to DB: {content[:50]}...")
        except Exception as e:
            logger.error(f"Failed to save message: {e}")

    async def _handle_gemini_message(self, msg: Dict[str, Any]):
        """Handle incoming message from Gemini."""
        _agent_log("B", "gemini_live.py:receive_loop", "ws_rx", {"topKeys": list(msg.keys())})
        if "error" in msg:
            logger.error(f"Gemini Error: {msg}")
            _agent_log("B", "gemini_live.py:receive_loop", "ws_error", {"error": msg.get("error")})
        
        tool_call_top = msg.get("tool_call") or msg.get("toolCall")
        if tool_call_top:
            _agent_log("B", "gemini_live.py:receive_loop", "tool_call_detected_top", {"toolCallKeys": list(tool_call_top.keys()), "toolsEnabled": bool(ENABLE_GEMINI_TOOLS)})
            if ENABLE_GEMINI_TOOLS:
                await self._handle_tool_call(tool_call_top)

        tool_cancel = msg.get("toolCallCancellation") or msg.get("tool_call_cancellation")
        if tool_cancel:
            _agent_log("B", "gemini_live.py:receive_loop", "tool_call_cancel", {"topKeys": list(tool_cancel.keys()) if isinstance(tool_cancel, dict) else type(tool_cancel).__name__, "tasks": len(self._tool_tasks)})
            for t in list(self._tool_tasks):
                try:
                    t.cancel()
                except Exception:
                    pass

        audio_data = msg.get("data")
        if audio_data and isinstance(audio_data, str):
            if self.frontend_ws:
                await self.frontend_ws.send_json({
                    "type": "audio",
                    "data": audio_data
                })

        # Check for serverContent
        server_content = msg.get("serverContent")
        if server_content:
            input_transcription = server_content.get("input_transcription") or server_content.get("inputTranscription")
            if input_transcription and isinstance(input_transcription, dict):
                t = input_transcription.get("text") or ""
                if t and t != self._last_input_transcription:
                    self._last_input_transcription = t
                    self.current_user_text = self._merge_partial_text(self.current_user_text, t)

            input_transcriptions = server_content.get("input_transcriptions") or server_content.get("inputTranscriptions")
            if input_transcriptions and isinstance(input_transcriptions, list):
                joined = " ".join([(x or {}).get("text", "") for x in input_transcriptions]).strip()
                if joined and joined != self._last_input_transcription:
                    self._last_input_transcription = joined
                    self.current_user_text = self._merge_partial_text(self.current_user_text, joined)

            output_transcription = server_content.get("output_transcription") or server_content.get("outputTranscription")
            if output_transcription and isinstance(output_transcription, dict):
                await self._flush_user_message()
                t = output_transcription.get("text") or ""
                if t and t != self._last_output_transcription:
                    self._last_output_transcription = t
                    if self.current_ai_text and t.startswith(self.current_ai_text):
                        self.current_ai_text = t
                    else:
                        self.current_ai_text += t
                    
                    if self.frontend_ws:
                        await self.frontend_ws.send_json({
                            "type": "live_text",
                            "role": "assistant",
                            "content": self.current_ai_text,
                            "is_final": False
                        })

            # Model Audio & Text
            model_turn = server_content.get("modelTurn")
            if model_turn:
                await self._flush_user_message()
                parts = model_turn.get("parts", [])
                for part in parts:
                    inline_data = part.get("inlineData")
                    if inline_data:
                        audio_data = inline_data.get("data")
                        if audio_data:
                            if self.frontend_ws:
                                await self.frontend_ws.send_json({
                                    "type": "audio",
                                    "data": audio_data
                                })
                    text_data = part.get("text")
                    if text_data and not self._last_output_transcription:
                        self.current_ai_text += text_data

            # Turn Complete
            if server_content.get("turn_complete") or server_content.get("turnComplete"):
                if self.current_ai_text:
                    await self._save_message(
                        "assistant",
                        self.current_ai_text,
                        citations=self._pending_citations or None,
                        reasoning_steps=self._pending_reasoning_steps or None,
                    )
                    if self.frontend_ws:
                        await self.frontend_ws.send_json({
                            "type": "live_text",
                            "role": "assistant",
                            "content": self.current_ai_text,
                            "is_final": True
                        })
                    self.current_ai_text = ""
                    self._last_output_transcription = ""
                    self._pending_citations = []
                    self._pending_reasoning_steps = []
            
            # Tool Call
            tool_call = msg.get("tool_call") or msg.get("toolCall")
            if not tool_call:
                tool_call = server_content.get("tool_call") or server_content.get("toolCall")
            
            if tool_call:
                logger.info(f"Tool call found keys={list(tool_call.keys())}")
                _agent_log("B", "gemini_live.py:receive_loop", "tool_call_detected", {"toolCallKeys": list(tool_call.keys()), "toolsEnabled": bool(ENABLE_GEMINI_TOOLS)})
                if ENABLE_GEMINI_TOOLS:
                    await self._handle_tool_call(tool_call)

            if "modelTurn" not in server_content and "turnComplete" not in server_content and "toolCall" not in server_content:
                logger.info(f"Potential User Transcript? Keys: {server_content.keys()}")

    async def receive_loop(self, frontend_ws):
        """Loops to receive messages from Gemini and forward audio to frontend."""
        try:
            self.frontend_ws = frontend_ws
            async for raw_msg in self.ws:
                msg = json.loads(raw_msg)
                await self._handle_gemini_message(msg)

        except Exception as e:
            logger.error(f"Error in receive loop: {e}")
            traceback.print_exc()

    async def _handle_tool_call(self, tool_call):
        """Handle tool calls from Gemini."""
        use_camel = "functionCalls" in tool_call
        function_calls = tool_call.get("function_calls") or tool_call.get("functionCalls") or []
        _agent_log("B", "gemini_live.py:_handle_tool_call", "dispatching", {"useCamel": bool(use_camel), "count": len(function_calls), "names": [c.get("name") for c in function_calls]})
        for call in function_calls:
            task = asyncio.create_task(self._run_tool_call(call, use_camel=use_camel))
            self._tool_tasks.add(task)
            task.add_done_callback(self._tool_tasks.discard)

    async def _run_tool_call(self, call: Dict[str, Any], use_camel: bool):
        """Execute a tool call."""
        name = call.get("name")
        args = call.get("args") or {}
        call_id = call.get("id")
        logger.info(f"Tool call received name={name} id={call_id} args_keys={list(args.keys())}")
        _agent_log("B", "gemini_live.py:_run_tool_call", "start", {"name": name, "hasId": bool(call_id), "argsKeys": list(args.keys()), "useCamel": bool(use_camel)})
        
        # Flush user message if pending
        if self.current_user_text and self.current_user_text != self._last_saved_user_text:
            await self._save_message("user", self.current_user_text, is_voice=True)
            self._last_saved_user_text = self.current_user_text
        
        if self.frontend_ws:
            await self.frontend_ws.send_json({
                "type": "live_text",
                "role": "user",
                "content": self.current_user_text,
                "is_final": True
            })
            self.current_user_text = ""

        if name != "retrieve_sources":
            return

        query = (args.get("query") or "").strip()
        logger.info(f"Tool retrieve_sources start id={call_id} query_len={len(query)}")
        _agent_log("A", "gemini_live.py:_run_tool_call", "retrieve_sources_begin", {"id": call_id, "queryLen": len(query)})
        if self.frontend_ws:
            try:
                await self.frontend_ws.send_json({
                    "type": "live_tool",
                    "tool": "retrieve_sources",
                    "status": "pending",
                    "query": query,
                })
            except Exception:
                pass

        started = asyncio.get_running_loop().time()
        result_text = ""
        citations = []
        try:
            docs = await asyncio.wait_for(self.retriever.retrieve(query, limit=3), timeout=12.0)
            doc_texts = []
            for d in (docs or []):
                md = getattr(d, "metadata", {}) or {}
                ref = md.get("ref") or md.get("heRef") or md.get("source_ref") or ""
                content = (getattr(d, "content", "") or "").strip()
                if ref and content:
                    citations.append({
                        "title": ref,
                        "url": "",
                        "description": content,
                        "ref": ref,
                        "sourceRef": ref,
                    })
                if ref:
                    doc_texts.append(f"{ref}: {content}")
                else:
                    doc_texts.append(content)
            result_text = "\n\n".join([t for t in doc_texts if t])
            logger.info(f"Tool retrieve_sources ok id={call_id} docs={len(docs or [])} bytes={len(result_text)} dur={(asyncio.get_running_loop().time()-started):.3f}s")
            _agent_log("A", "gemini_live.py:_run_tool_call", "retrieve_sources_ok", {"id": call_id, "docs": len(docs or []), "bytes": len(result_text), "durMs": int((asyncio.get_running_loop().time()-started) * 1000)})
        except asyncio.TimeoutError:
            logger.error(f"Tool retrieve_sources timeout id={call_id} dur={(asyncio.get_running_loop().time()-started):.3f}s")
            result_text = "Search timed out. Please try again with a shorter query."
            _agent_log("A", "gemini_live.py:_run_tool_call", "retrieve_sources_timeout", {"id": call_id, "durMs": int((asyncio.get_running_loop().time()-started) * 1000)})
        except Exception as e:
            logger.error(f"Tool retrieve_sources error id={call_id} err={e}")
            result_text = f"Error retrieving: {e}"
            _agent_log("A", "gemini_live.py:_run_tool_call", "retrieve_sources_error", {"id": call_id, "errType": type(e).__name__})

        if citations:
            self._pending_citations = citations
            self._pending_reasoning_steps = [
                {
                    "step": "Retrieval",
                    "status": "complete",
                    "message": "",
                    "citations": citations,
                    "query": query,
                    "sources": citations,
                }
            ]

        if self.frontend_ws:
            try:
                await self.frontend_ws.send_json({
                    "type": "live_tool",
                    "tool": "retrieve_sources",
                    "status": "complete",
                    "query": query,
                    "citations": citations,
                })
            except Exception:
                pass

        resp_msg = {
            "toolResponse": {
                "functionResponses": [
                    {
                        "id": call_id,
                        "name": name,
                        "response": {"output": result_text},
                    }
                ]
            },
        }
        label = f"toolResponse:{name}"

        logger.info(f"Tool retrieve_sources sending id={call_id} bytes={len(result_text)} casing={'camel' if use_camel else 'snake'}")
        _agent_log("C", "gemini_live.py:_run_tool_call", "tool_response_pre_send", {"id": call_id, "name": name, "respTopKeys": list(resp_msg.keys()), "innerKeys": list(resp_msg["toolResponse"].keys())})
        await self._ws_send_json(resp_msg, label)

    async def close(self):
        """Close the session and save any pending messages."""
        ai = (self.current_ai_text or "").strip()
        if ai:
            await self._save_message(
                "assistant",
                ai,
                citations=self._pending_citations or None,
                reasoning_steps=self._pending_reasoning_steps or None,
            )
            self.current_ai_text = ""
            self._pending_citations = []
            self._pending_reasoning_steps = []
        usr = (self.current_user_text or "").strip()
        if usr and usr != self._last_saved_user_text:
            await self._save_message("user", usr)
            self._last_saved_user_text = usr
            self.current_user_text = ""
        if self.ws:
            await self.ws.close()
