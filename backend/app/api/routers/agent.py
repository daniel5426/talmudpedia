import json
import time
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage

from app.agent import AgentConfig, AgentFactory
from uuid import UUID
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres.session import get_db
from app.db.postgres.models.chat import Chat, Message, MessageRole
from app.db.postgres.models.identity import User, Tenant
from app.api.routers.auth import oauth2_scheme, get_current_user

# Initialize the agent
chat_agent = AgentFactory.create_agent(AgentConfig())

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    chatId: Optional[UUID] = None
    files: Optional[List[Dict[str, Any]]] = None


class ThinkingDurationFormatter:
    @staticmethod
    def format_duration(duration_ms: Optional[int]) -> Optional[str]:
        if not duration_ms or duration_ms <= 0:
            return None
        seconds = duration_ms / 1000
        if seconds < 60:
            value = f"{seconds:.1f}" if seconds < 10 else str(round(seconds))
            if value.endswith(".0"):
                value = value[:-2]
            return f"{value} שניות"
        minutes = int(seconds // 60)
        minute_unit = "דקה" if minutes == 1 else "דקות"
        remaining_seconds = round(seconds % 60)
        if remaining_seconds == 0:
            return f"{minutes} {minute_unit}"
        return f"{minutes} {minute_unit} {remaining_seconds} שניות"

    @classmethod
    def build_label(cls, duration_ms: Optional[int]) -> Optional[str]:
        formatted = cls.format_duration(duration_ms)
        if not formatted:
            return None
        return f"חשב במשך {formatted}"


CACHED_TENANT_ID: Optional[UUID] = None

async def get_tenant_id(db: AsyncSession) -> UUID:
    """Helper to get a tenant ID with simple caching."""
    global CACHED_TENANT_ID
    if CACHED_TENANT_ID:
        return CACHED_TENANT_ID
        
    result = await db.execute(select(Tenant).limit(1))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=500, detail="No tenant configured")
    
    CACHED_TENANT_ID = tenant.id
    return CACHED_TENANT_ID


@router.post("/chat")
async def chat_endpoint(
    request_body: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    t_enter = time.perf_counter()
    print(f"[TIMER] chat_endpoint entered: {t_enter}")
    """Streams chat completions along with reasoning artifacts using Postgres."""
    chat_id = request_body.chatId
    user_message = request_body.message
    files = request_body.files or []

    # --- DB SETUP ---
    t_heavy_start = time.perf_counter()
    
    # Fetch Tenant (Tenant is cached)
    tenant_id = await get_tenant_id(db)

    history_messages: List[Any] = []
    msg_count = 0
    chat = None
    
    if chat_id:
        # chatId is already a UUID due to Pydantic conversion
        # OPTIMIZATION: Fetch Chat and Messages in ONE round-trip using selectinload
        result = await db.execute(
            select(Chat)
            .options(selectinload(Chat.messages))
            .where(Chat.id == chat_id, Chat.user_id == current_user.id)
        )
        chat = result.scalar_one_or_none()
        
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        # Chat.messages is already populated due to selectinload
        msg_count = len(chat.messages)
        for msg in chat.messages:
            if msg.role == MessageRole.USER:
                history_messages.append(HumanMessage(content=msg.content))
            elif msg.role == MessageRole.ASSISTANT:
                history_messages.append(AIMessage(content=msg.content))
    else:
        # New chat
        chat = Chat(
            title=user_message[:30] + "...",
            user_id=current_user.id,
            tenant_id=tenant_id
        )
        db.add(chat)
        await db.flush()
        chat_id = str(chat.id)
        msg_count = 0

    # Save user message and commit (One final round trip)
    user_msg_db = Message(
        chat_id=chat.id,
        role=MessageRole.USER,
        content=user_message,
        index=msg_count,
    )
    db.add(user_msg_db)
    chat.updated_at = datetime.now(timezone.utc)
    await db.commit()
    
    # Add the NEW user message to history so the AI sees it
    history_messages.append(HumanMessage(content=user_message))
    
    print(f"[TIMER] Total Heavy Setup (Optimized): {time.perf_counter()-t_heavy_start:.4f}s")
    # --- END AUTH AND DB SETUP ---
    
    async def event_generator():
        t_gen_start = time.perf_counter()
        full_response = ""
        collected_citations: List[Dict[str, Any]] = []
        collected_reasoning: List[Dict[str, Any]] = []
        thinking_timer_start = time.perf_counter()
        thinking_duration_ms: Optional[int] = None
        in_tool_call = False

        try:
            # 1. Yield initial signal IMMEDIATELY
            init_reasoning = {"step": "Analysis", "status": "active", "message": "Evaluating request..."}
            collected_reasoning.append(init_reasoning)
            yield json.dumps({"type": "reasoning", "data": init_reasoning}) + "\n"
            
            # Logic moved above
            
            
            inputs = {
                "messages": history_messages,
                "reasoning_items": [],
                "files": files
            }
            
            t_agent_start = time.perf_counter()
            first_event_received = False
            async for event in chat_agent.astream_events(inputs, version="v2"):
                if not first_event_received:
                    print(f"[TIMER] Time to first agent event: {time.perf_counter()-t_agent_start:.4f}s")
                    first_event_received = True
                kind = event["event"]
                name = event.get("name")
                data = event.get("data", {})
                
                if kind == "on_custom_event":
                    if name == "reasoning_step":
                        step_data = data
                        step_label = step_data.get("step")
                        
                        existing_index = next(
                            (i for i, s in enumerate(collected_reasoning) if s.get("step") == step_label),
                            None
                        )
                        if existing_index is not None:
                            collected_reasoning[existing_index] = {**collected_reasoning[existing_index], **step_data}
                        else:
                            collected_reasoning.append(step_data)
                        yield json.dumps({"type": "reasoning", "data": step_data}) + "\n"
                    
                    elif name == "retrieval_start":
                        query = data.get("query", "")
                        for i, step in enumerate(collected_reasoning):
                            if step["step"] == "Analysis" and step["status"] == "active":
                                step["status"] = "complete"
                                step["message"] = ""
                                collected_reasoning[i] = step
                                yield json.dumps({"type": "reasoning", "data": step}) + "\n"
                        
                        retrieval_count = sum(1 for s in collected_reasoning if s.get("step", "").startswith("Retrieval"))
                        step_name = f"Retrieval {retrieval_count + 1}" if retrieval_count > 0 else "Retrieval"
                        retrieval_pending = {"step": step_name, "status": "pending", "message": "", "query": query}
                        collected_reasoning.append(retrieval_pending)
                        yield json.dumps({"type": "reasoning", "data": retrieval_pending}) + "\n"
                        
                    elif name == "retrieval_complete":
                        docs = data.get("docs", [])
                        query = data.get("query", "")
                        if docs:
                            for i, step in enumerate(collected_reasoning):
                                if step.get("status") == "pending" and step.get("step", "").startswith("Retrieval"):
                                    step_citations = []
                                    for doc in docs:
                                        meta = doc.get("metadata", {})
                                        citation = {
                                            "title": meta.get("ref", "Unknown"),
                                            "url": meta.get("shape_path", [None])[0],
                                            "ref": meta.get("ref", ""),
                                            "description": meta.get("text", "")[:100] + "..."
                                        }
                                        step_citations.append(citation)
                                        collected_citations.append(citation)
                                        yield json.dumps({"type": "citation", "data": citation}) + "\n"
                                    
                                    step["status"] = "complete"
                                    step["message"] = ""
                                    step["query"] = query
                                    step["citations"] = step_citations
                                    collected_reasoning[i] = step
                                    yield json.dumps({"type": "reasoning", "data": step}) + "\n"
                                    break

                    elif name == "output_delta":
                        delta_text = data.get("delta", "")
                        full_response += delta_text
                        yield json.dumps({"type": "token", "content": delta_text}) + "\n"

                elif kind == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    if chunk:
                        if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                            in_tool_call = True
                            continue
                        if chunk.content:
                            in_tool_call = False
                            if thinking_duration_ms is None:
                                thinking_duration_ms = int((time.perf_counter() - thinking_timer_start) * 1000)
                                label = ThinkingDurationFormatter.build_label(thinking_duration_ms)
                                if label:
                                    duration_step = {"step": label, "status": "complete", "message": ""}
                                    collected_reasoning.append(duration_step)
                                    yield json.dumps({"type": "reasoning", "data": duration_step}) + "\n"
                                for i, step in enumerate(collected_reasoning):
                                    if step["step"] == "Analysis" and step["status"] == "active":
                                        step["status"] = "complete"; step["message"] = ""
                                        collected_reasoning[i] = step
                                        yield json.dumps({"type": "reasoning", "data": step}) + "\n"
                            content = str(chunk.content) if chunk.content else ""
                            full_response += content
                            yield json.dumps({"type": "token", "content": content}) + "\n"

        except Exception as e:
            error_msg = f"Agent streaming failed: {type(e).__name__}: {str(e)}"
            print(f"[MAIN ERROR] {error_msg}")
            yield json.dumps({"type": "error", "data": {"message": error_msg}}) + "\n"
        finally:
            if full_response:
                # Save assistant message
                # We need a new session since the outer one might be closed or at a different state
                # but in event_generator we should be careful. 
                # Actually, the db session is function scoped and should stay open until the request ends.
                asst_msg_db = Message(
                    chat_id=chat.id,
                    role=MessageRole.ASSISTANT,
                    content=full_response,
                    index=msg_count + 1,
                    tool_calls={"reasoning": collected_reasoning, "citations": collected_citations}
                )
                db.add(asst_msg_db)
                
                # Update user token usage
                total_chars = len(user_message) + len(full_response)
                estimated_tokens = total_chars // 4
                await db.execute(
                    update(User).where(User.id == current_user.id).values(
                        token_usage=User.token_usage + estimated_tokens
                    )
                )
                await db.commit()

    headers = {"X-Chat-ID": str(chat_id or "")}
    print(f"[TIMER] chat_endpoint returning StreamingResponse: {time.perf_counter()-t_enter:.4f}s")
    return StreamingResponse(event_generator(), media_type="application/x-ndjson", headers=headers)

