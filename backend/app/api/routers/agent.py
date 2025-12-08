import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
import traceback  # checking if this is needed, yes used in except block

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from app.agent import AgentConfig, AgentFactory
from app.db.connection import MongoDatabase
from app.db.models.chat import Chat, Message
from app.db.models.user import User
from app.api.routers.auth import get_current_user

# Initialize the agent
chat_agent = AgentFactory.create_agent(AgentConfig())

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    chatId: Optional[str] = None
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


@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    """Streams chat completions along with reasoning artifacts."""
    chat_id = request.chatId

    user_message = request.message
    files = request.files or []
    db = MongoDatabase.get_db()
    
    if chat_id:
        # Verify chat ownership
        existing_chat = await db.chats.find_one({"_id": ObjectId(chat_id), "user_id": str(current_user.id)})
        if not existing_chat:
            raise HTTPException(status_code=404, detail="Chat not found or access denied")
    else:
        chat = Chat(
            title=user_message[:30] + "...",
            user_id=str(current_user.id)
        )
        result = await db.chats.insert_one(chat.model_dump(by_alias=True, exclude={"id"}))
        chat_id = str(result.inserted_id)
        
    message = Message(
        role="user", 
        content=user_message,
        attachments=[{"name": f["name"], "type": f["type"], "content": f["content"]} for f in files] if files else None
    )
    await db.chats.update_one(
        {"_id": ObjectId(chat_id)},
        {
            "$push": {"messages": message.model_dump()},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    chat_data = await db.chats.find_one({"_id": ObjectId(chat_id)})
    history_messages: List[Any] = []
    reasoning_items_accumulated: List[Any] = []
    if chat_data:
        chat_obj = Chat(**chat_data)
        for msg in chat_obj.messages:
            if msg.role == "user":
                content = msg.content
                if msg.attachments:
                    # Check if we have images for multimodal
                    has_images = any(att.type.startswith("image/") for att in msg.attachments)
                    
                    if has_images:
                        # Multimodal format for GPT-4o
                        content_parts = [{"type": "text", "text": content}]
                        for att in msg.attachments:
                            if att.type.startswith("image/"):
                                content_parts.append({
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{att.type};base64,{att.content}"}
                                })
                            else:
                                # For non-image files (text/pdf), we append to text content for now
                                # or add as text block if supported.
                                # Appending to text is safer for general compatibility
                                try:
                                    import base64
                                    decoded = base64.b64decode(att.content).decode('utf-8')
                                    content_parts.append({
                                        "type": "text", 
                                        "text": f"\n\n[Attachment: {att.name}]\n{decoded}"
                                    })
                                except Exception:
                                    pass
                        history_messages.append(HumanMessage(content=content_parts))
                    else:
                        # Text-only attachments
                        full_content = content
                        for att in msg.attachments:
                            try:
                                import base64
                                decoded = base64.b64decode(att.content).decode('utf-8')
                                full_content += f"\n\n[Attachment: {att.name}]\n{decoded}"
                            except Exception:
                                pass
                        history_messages.append(HumanMessage(content=full_content))
                else:
                    history_messages.append(HumanMessage(content=content))
            elif msg.role == "assistant":
                history_messages.append(AIMessage(content=msg.content))
                if msg.reasoning_items:
                    reasoning_items_accumulated.extend(msg.reasoning_items)

    async def event_generator():
        full_response = ""
        collected_citations: List[Dict[str, Any]] = []
        collected_reasoning: List[Dict[str, Any]] = []
        final_reasoning_items: List[Dict[str, Any]] = []
        thinking_timer_start = time.perf_counter()
        thinking_duration_ms: Optional[int] = None
        
        # Track if we are currently in a tool call to avoid streaming tool inputs as text
        in_tool_call = False

        try:
            # Initial "Analysis" step (kept for UI consistency, though agent is dynamic now)
            init_reasoning = {"step": "Analysis", "status": "active", "message": "Processing request..."}
            collected_reasoning.append(init_reasoning)
            yield json.dumps({"type": "reasoning", "data": init_reasoning}) + "\n"
            
            inputs = {
                "messages": history_messages,
                "reasoning_items": reasoning_items_accumulated,
                "files": files
            }
            
            async for event in chat_agent.astream_events(inputs, version="v2"):
                kind = event["event"]
                name = event.get("name")
                data = event.get("data", {})
                
                # 1. Handle Custom Events (Reasoning & Retrieval)
                if kind == "on_custom_event":
                    if name == "reasoning_step":
                        step_data = data
                        step_label = step_data.get("step")
                        
                        # Update or append reasoning step
                        existing_index = next(
                            (i for i, s in enumerate(collected_reasoning) if s.get("step") == step_label),
                            None
                        )
                        if existing_index is not None:
                            collected_reasoning[existing_index] = {
                                **collected_reasoning[existing_index],
                                **step_data
                            }
                        else:
                            collected_reasoning.append(step_data)
                        yield json.dumps({"type": "reasoning", "data": step_data}) + "\n"
                    
                    elif name == "retrieval_start":
                        # Handle retrieval start - emit pending status
                        query = data.get("query", "")
                        
                        # Mark Analysis as complete if it's still active
                        for i, step in enumerate(collected_reasoning):
                            if step["step"] == "Analysis" and step["status"] == "active":
                                step["status"] = "complete"
                                step["message"] = ""
                                collected_reasoning[i] = step
                                yield json.dumps({"type": "reasoning", "data": step}) + "\n"
                        
                        # Count how many retrieval steps we already have to create unique names
                        retrieval_count = sum(1 for s in collected_reasoning if s.get("step", "").startswith("Retrieval"))
                        step_name = f"Retrieval {retrieval_count + 1}" if retrieval_count > 0 else "Retrieval"
                        
                        # Emit pending retrieval step with raw data
                        retrieval_pending = {
                            "step": step_name,
                            "status": "pending",
                            "message": "",
                            "query": query
                        }
                        collected_reasoning.append(retrieval_pending)
                        yield json.dumps({"type": "reasoning", "data": retrieval_pending}) + "\n"
                        
                    elif name == "retrieval_complete":
                        # Handle citations from retrieval tool
                        docs = data.get("docs", [])
                        query = data.get("query", "")
                        
                        if docs:
                            # Find the pending retrieval step and update it to complete
                            for i, step in enumerate(collected_reasoning):
                                if step.get("status") == "pending" and step.get("step", "").startswith("Retrieval"):
                                    step_name = step["step"]
                                    
                                    # Emit citations
                                    step_citations = []
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
                                        step_citations.append(citation)
                                        collected_citations.append(citation)
                                        yield json.dumps({"type": "citation", "data": citation}) + "\n"
                                    
                                    # Update the step to complete with raw data
                                    step["status"] = "complete"
                                    step["message"] = ""
                                    step["query"] = query
                                    step["sources"] = docs
                                    step["citations"] = step_citations
                                    collected_reasoning[i] = step
                                    yield json.dumps({"type": "reasoning", "data": step}) + "\n"
                                    break

                    elif name == "output_delta":
                        # Legacy support if any component still emits this
                        delta_text = data.get("delta", "")
                        full_response += delta_text
                        yield json.dumps({"type": "token", "content": delta_text}) + "\n"
                        
                    elif name == "error":
                        yield json.dumps({"type": "error", "data": data}) + "\n"

                # 2. Handle Standard LangChain Streaming (Tokens)
                elif kind == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    if chunk:
                        # Check if this chunk is a tool call (don't stream tool call args as text)
                        if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                            in_tool_call = True
                            continue
                        
                        # If we are back to content and it's not empty
                        if chunk.content:
                            in_tool_call = False
                            
                            # Calculate thinking time on first token
                            if thinking_duration_ms is None:
                                thinking_duration_ms = int((time.perf_counter() - thinking_timer_start) * 1000)
                                label = ThinkingDurationFormatter.build_label(thinking_duration_ms)
                                if label:
                                    duration_step = {"step": label, "status": "complete", "message": ""}
                                    collected_reasoning.append(duration_step)
                                    yield json.dumps({"type": "reasoning", "data": duration_step}) + "\n"
                                    
                                # Also mark Analysis complete if not already
                                for i, step in enumerate(collected_reasoning):
                                    if step["step"] == "Analysis" and step["status"] == "active":
                                        step["status"] = "complete"
                                        step["message"] = ""
                                        collected_reasoning[i] = step
                                        yield json.dumps({"type": "reasoning", "data": step}) + "\n"

                            full_response += chunk.content
                            yield json.dumps({"type": "token", "content": chunk.content}) + "\n"

                # 3. Handle Tool Start (for UI feedback)
                elif kind == "on_tool_start":
                    # We could emit a "Thinking..." or "Using tool..." event here
                    pass

        except Exception as e:
            error_msg = f"Agent streaming failed: {type(e).__name__}: {str(e)}"
            print(f"[MAIN ERROR] {error_msg}")
            import traceback
            traceback.print_exc()
            yield json.dumps({
                "type": "error",
                "data": {"message": error_msg}
            }) + "\n"
        finally:
            if full_response:
                asst_message = Message(
                    role="assistant",
                    content=full_response,
                    citations=collected_citations,
                    reasoning_steps=collected_reasoning,
                    reasoning_items=final_reasoning_items,
                    thinking_duration_ms=thinking_duration_ms
                )
                await db.chats.update_one(
                    {"_id": ObjectId(chat_id)},
                    {
                        "$push": {"messages": asst_message.model_dump()},
                        "$set": {"updated_at": datetime.utcnow()}
                    }
                )
                
                # Update user token usage
                # Simple estimation: 1 token ~= 4 characters
                total_chars = len(user_message) + len(full_response)
                estimated_tokens = total_chars // 4
                await db.users.update_one(
                    {"_id": current_user.id},
                    {"$inc": {"token_usage": estimated_tokens}}
                )

    return StreamingResponse(event_generator(), media_type="application/x-ndjson", headers={"X-Chat-ID": chat_id})
