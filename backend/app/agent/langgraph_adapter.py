from __future__ import annotations

import asyncio
import re
import sys
from typing import Any, AsyncIterable, List, Optional, TYPE_CHECKING
from livekit.agents import llm
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from app.agent.core.base import BaseAgent

if TYPE_CHECKING:
    from app.services.voice import VoiceSessionManager

class LangGraphAdapter(llm.LLM):
    def __init__(
        self,
        *,
        agent: BaseAgent,
        session_manager: Optional["VoiceSessionManager"] = None,
        filler_message: str = "רק רגע, אני בודק במקורות...",
    ) -> None:
        super().__init__()
        self.agent = agent
        self.session_manager = session_manager
        self.filler_message = filler_message

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        fnc_ctx: Optional[llm.FunctionContext] = None,
        temperature: Optional[float] = None,
        n: Optional[int] = None,
        parallel_tool_calls: Optional[bool] = None,
        tools: Optional[Any] = None,
        tool_choice: Optional[Any] = None,
        conn_options: Optional[Any] = None,
        **_: Any,
    ) -> "LangGraphLLMStream":
        return LangGraphLLMStream(
            agent=self.agent,
            chat_ctx=chat_ctx,
            filler_message=self.filler_message,
            llm=self,
            session_manager=self.session_manager,
            tools=tools or [],
            conn_options=conn_options,
        )

class LangGraphLLMStream(llm.LLMStream):
    def __init__(
        self,
        *,
        agent: BaseAgent,
        chat_ctx: llm.ChatContext,
        filler_message: str,
        llm: llm.LLM,
        session_manager: Optional["VoiceSessionManager"],
        tools: list[Any],
        conn_options: Any,
    ) -> None:
        super().__init__(llm=llm, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self.agent = agent
        self.filler_message = filler_message
        self.session_manager = session_manager
        self.current_response = ""
        self.current_citations = []
        self.current_reasoning = []
        self._buffer = ""

    def _to_langchain_messages(self, chat_ctx: llm.ChatContext) -> List[BaseMessage]:
        messages: List[BaseMessage] = []
        for msg in chat_ctx.items:
            role = msg.role
            if role == "system":
                messages.append(SystemMessage(content="".join(msg.content)))
            elif role == "user":
                messages.append(HumanMessage(content="".join(msg.content)))
            elif role == "assistant":
                messages.append(AIMessage(content="".join(msg.content)))
        return messages

    async def _run(self) -> None:
        messages = self._to_langchain_messages(self.chat_ctx)
        
        last_user_message = None
        for msg in reversed(self.chat_ctx.items):
            if msg.role == "user":
                last_user_message = "".join(msg.content)
                break
        
        self.current_response = ""
        self.current_citations = []
        self.current_reasoning = []
        self._buffer = ""
        self._stream_print_started = False
        print("LLM start", last_user_message)

        def normalize_content(content: Any) -> str:
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        parts.append(item.get("text", ""))
                    else:
                        text = getattr(item, "text", None)
                        if text:
                            parts.append(text)
                return "".join(parts)
            return str(content)

        def clean_for_tts(text: str) -> str:
            t = text.replace("**", "").replace("*", "").replace("_", "")
            t = t.replace("`", "")
            t = re.sub(r"\s+\n", "\n", t)
            t = re.sub(r"\n{3,}", "\n\n", t)
            t = t.replace("•", "- ").replace("\u2022", "- ")
            return t

        async def flush_buffer(force: bool = False):
            text = self._buffer
            if not text.strip():
                return
            if not force and len(text) < 20:
                return
            chunk_text = text.strip()
            import uuid
            chunk_id = str(uuid.uuid4())
            chunk = llm.ChatChunk(
                id=chunk_id,
                request_id=chunk_id,
                delta=llm.ChoiceDelta(role="assistant", content=chunk_text)
            )
            self._event_ch.send_nowait(chunk)
            self._buffer = ""
        
        try:
            async for event in self.agent.astream_events(
                inputs={"messages": messages},
                version="v2"
            ):
                kind = event.get("event")
                name = event.get("name")
                data = event.get("data", {})
                
                if kind == "on_tool_start":
                    import uuid
                    chunk_id = str(uuid.uuid4())
                    
                    chunk = llm.ChatChunk(
                        id=chunk_id,
                        request_id=chunk_id,
                        delta=llm.ChoiceDelta(role="assistant", content=self.filler_message)
                    )
                    self._event_ch.send_nowait(chunk)
                
                elif kind == "on_custom_event":
                    if name == "retrieval_complete":
                        docs = data.get("docs", [])
                        for doc in docs:
                            meta = doc.get("metadata", {})
                            shape_path = meta.get("shape_path", [])
                            citation = {
                                "title": meta.get("ref", "Unknown Source"),
                                "url": shape_path[0] if shape_path else None,
                                "sourceRef": shape_path[1] if shape_path else None,
                                "ref": meta.get("ref", ""),
                                "description": meta.get("text", "")[:100] + "..."
                            }
                            self.current_citations.append(citation)
                    
                    elif name == "reasoning_step":
                        self.current_reasoning.append(data)
                    
                elif kind == "on_chat_model_stream":
                    chunk_content = event["data"]["chunk"].content
                    if chunk_content:
                        content_str = normalize_content(chunk_content)
                        if content_str:
                            cleaned = clean_for_tts(content_str)
                            if not self._stream_print_started:
                                print("LLM stream:", end=" ", flush=True)
                                self._stream_print_started = True
                            sys.stdout.write(cleaned)
                            sys.stdout.flush()
                            self.current_response += cleaned
                        self._buffer += cleaned
                        await flush_buffer()
                    finish_reason = getattr(event["data"]["chunk"], "finish_reason", None)
                    if finish_reason == "stop":
                        await flush_buffer(force=True)
        finally:
            await flush_buffer(force=True)
        
        if self.session_manager and last_user_message:
            self.session_manager.buffer_message("user", last_user_message)
        
        if self.session_manager and self.current_response:
            print(f"[DEBUG DB] Saving to database: {repr(self.current_response)}")
            self.session_manager.buffer_message(
                "assistant",
                self.current_response,
                citations=self.current_citations if self.current_citations else None,
                reasoning_steps=self.current_reasoning if self.current_reasoning else None
            )
            await self.session_manager.save_buffered_messages()
        if self._stream_print_started:
            print()
        print("LLM done", self.current_response)

    def __aiter__(self) -> AsyncIterable[llm.ChatChunk]:
        return self._event_ch

