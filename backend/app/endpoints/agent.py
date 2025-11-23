import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from agent import agent as chat_agent
from app.db.connection import MongoDatabase
from app.db.models.chat import Chat, Message


class ChatRequest(BaseModel):
    message: str
    chatId: Optional[str] = None


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


class AgentEndpoints:
    router = APIRouter(tags=["agent"])

    @staticmethod
    @router.post("/chat")
    async def chat_endpoint(request: ChatRequest):
        """Streams chat completions along with reasoning artifacts."""
        chat_id = request.chatId
        user_message = request.message
        db = MongoDatabase.get_db()
        if not chat_id:
            chat = Chat(title=user_message[:30] + "...")
            result = await db.chats.insert_one(chat.model_dump(by_alias=True, exclude={"id"}))
            chat_id = str(result.inserted_id)
        message = Message(role="user", content=user_message)
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
                    history_messages.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    history_messages.append(AIMessage(content=msg.content))
                    if msg.reasoning_items:
                        reasoning_items_accumulated.extend(msg.reasoning_items)

        async def event_generator():
            full_response = ""
            collected_citations: List[Dict[str, Any]] = []
            collected_reasoning: List[Dict[str, Any]] = []
            final_reasoning_items: List[Dict[str, Any]] = []
            pending_retrieval_update: Optional[Dict[str, Any]] = None
            retrieval_update_pending = False
            retrieval_update_sent = False
            thinking_timer_start = time.perf_counter()
            thinking_duration_ms: Optional[int] = None

            def consume_pending_retrieval_update():
                nonlocal pending_retrieval_update, retrieval_update_pending, retrieval_update_sent, collected_reasoning
                if retrieval_update_pending and not retrieval_update_sent and pending_retrieval_update:
                    retrieval_update_sent = True
                    retrieval_update_pending = False
                    collected_reasoning.append(pending_retrieval_update)
                    update_data = pending_retrieval_update
                    pending_retrieval_update = None
                    return update_data
                return None

            try:
                init_reasoning = {"step": "Analysis", "status": "active", "message": ""}
                collected_reasoning.append(init_reasoning)
                yield json.dumps({"type": "reasoning", "data": init_reasoning}) + "\n"
                inputs = {
                    "messages": history_messages,
                    "reasoning_items": reasoning_items_accumulated
                }
                async for event in chat_agent.astream_events(inputs, version="v2"):
                    pending_update = consume_pending_retrieval_update()
                    if pending_update:
                        yield json.dumps({"type": "reasoning", "data": pending_update}) + "\n"
                    kind = event["event"]
                    if kind == "on_custom_event" and event.get("name") == "reasoning_step":
                        step_data = event.get("data", {})
                        step_label = step_data.get("step")
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
                    elif kind == "on_custom_event" and event.get("name") == "output_delta":
                        delta_data = event.get("data", {})
                        delta_text = delta_data.get("delta", "")
                        full_response += delta_text
                        if thinking_duration_ms is None:
                            thinking_duration_ms = int((time.perf_counter() - thinking_timer_start) * 1000)
                            label = ThinkingDurationFormatter.build_label(thinking_duration_ms)
                            if label:
                                duration_step = {"step": label, "status": "complete", "message": ""}
                                collected_reasoning.append(duration_step)
                                yield json.dumps({"type": "reasoning", "data": duration_step}) + "\n"
                        yield json.dumps({"type": "token", "content": delta_text}) + "\n"
                    elif kind == "on_custom_event" and event.get("name") == "error":
                        error_data = event.get("data", {})
                        yield json.dumps({"type": "error", "data": error_data}) + "\n"
                    elif kind == "on_custom_event" and event.get("name") == "warning":
                        warning_data = event.get("data", {})
                        print(f"[CUSTOM EVENT] Warning: {warning_data.get('message')}")
                    elif kind == "on_chain_end" and event["name"] == "retrieve":
                        data = event["data"].get("output")
                        if data and "retrieved_docs" in data:
                            analysis_complete = {"step": "Analysis", "status": "complete", "message": ""}
                            collected_reasoning.append(analysis_complete)
                            yield json.dumps({"type": "reasoning", "data": analysis_complete}) + "\n"
                            retrieval_active = {"step": "Retrieval", "status": "active", "message": "Searching Rabbinic texts..."}
                            collected_reasoning.append(retrieval_active)
                            yield json.dumps({"type": "reasoning", "data": retrieval_active}) + "\n"
                            docs = data["retrieved_docs"]
                            for doc in docs:
                                meta = doc.get("metadata", {})
                                citation = {
                                    "title": meta.get("ref", "Unknown Source"),
                                    "url": f"https://talmudpedia.com/{meta.get('ref', '').replace(' ', '-')}",
                                    "description": meta.get("text", "")[:100] + "..."
                                }
                                collected_citations.append(citation)
                                yield json.dumps({"type": "citation", "data": citation}) + "\n"
                            pending_retrieval_update = {
                                "step": "Retrieval",
                                "status": "complete",
                                "message": "",
                                "citations": collected_citations
                            }
                            retrieval_update_pending = True
                    elif kind == "on_chain_end" and event["name"] == "generate":
                        data = event["data"].get("output")
                        if data:
                            final_reasoning_items = data.get("reasoning_items", [])
                pending_update = consume_pending_retrieval_update()
                if pending_update:
                    yield json.dumps({"type": "reasoning", "data": pending_update}) + "\n"
            except Exception as e:
                error_msg = f"Agent streaming failed: {type(e).__name__}: {str(e)}"
                print(f"[MAIN ERROR] {error_msg}")
                import traceback
                traceback.print_exc()
                yield json.dumps({
                    "type": "error",
                    "data": {"message": error_msg}
                }) + "\n"
                pending_update = consume_pending_retrieval_update()
                if pending_update:
                    yield json.dumps({"type": "reasoning", "data": pending_update}) + "\n"
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

        return StreamingResponse(event_generator(), media_type="application/x-ndjson", headers={"X-Chat-ID": chat_id})

