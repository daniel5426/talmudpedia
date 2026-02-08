import logging
from typing import AsyncGenerator, Dict, Any, Union
import json

from .types import ExecutionMode, EventVisibility, ExecutionEvent

logger = logging.getLogger(__name__)

class StreamAdapter:
    """
    Adapts the internal agent execution stream for different consumers (Modes).
    Enforces filtering rules based on EventVisibility.
    """
    
    @staticmethod
    async def filter_stream(
        stream: AsyncGenerator[Union[Dict[str, Any], ExecutionEvent], None],
        mode: ExecutionMode
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Consumes the raw event stream and yields filtered events based on mode.
        """
        async for chunk in stream:
            # Normalize to ExecutionEvent wrapper if standard dict
            if isinstance(chunk, dict):
                # Temporary compatibility: try to infer visibility if not present
                # This handles legacy events or those not yet fully migrated to ExecutionEvent
                visibility = chunk.get("visibility", EventVisibility.INTERNAL)
                event_type = chunk.get("event", "")
                
                # Heuristics for untagged events (Safety net during refactor)
                if mode == ExecutionMode.PRODUCTION:
                    # In PROD, rely strictly on explicit tags or known allow-list
                    if event_type in ("on_chat_model_stream", "run_status"):
                         # Even these should ideally be explicitly tagged CLIENT_SAFE by the engine
                        pass 
                    elif visibility != EventVisibility.CLIENT_SAFE:
                        continue
                
                # If we are here, it's allowed or we are in DEBUG
                yield chunk
                
                # Synthesize Reasoning Events for Chain of Thought UI (for dicts)
                if mode != ExecutionMode.PRODUCTION:
                    evt_type = chunk.get("event")
                    evt_name = chunk.get("name")
                    if evt_type == "on_tool_start":
                        yield {
                            "type": "reasoning",
                            "data": {
                                "step": evt_name or "Tool",
                                "step_id": chunk.get("span_id"),
                                "status": "active",
                                "message": chunk.get("data", {}).get("message") or f"Calling tool {evt_name}...",
                            }
                        }
                    elif evt_type == "on_tool_end":
                        data = chunk.get("data", {})
                        yield {
                            "type": "reasoning",
                            "data": {
                                "step": evt_name or "Tool",
                                "step_id": chunk.get("span_id"),
                                "status": "complete",
                                "message": f"Tool {evt_name} completed",
                                "output": data.get("output") if data else None
                            }
                        }
                continue

            if isinstance(chunk, ExecutionEvent):
                if mode == ExecutionMode.PRODUCTION:
                    if chunk.visibility == EventVisibility.CLIENT_SAFE:
                        yield chunk.model_dump(mode='json')
                else:
                    # DEBUG mode: Yield everything
                    # PLUS: Synthesize "reasoning" events for better UI
                    yield chunk.model_dump(mode='json')
                    
                    # Synthesize Reasoning Events for Chain of Thought UI
                    if chunk.event == "on_tool_start":
                        yield {
                            "type": "reasoning",
                            "data": {
                                "step": chunk.name or "Tool",
                                "step_id": chunk.span_id,
                                "status": "active",
                                "message": chunk.data.get("message") or f"Calling tool {chunk.name}...",
                            }
                        }
                    elif chunk.event == "on_tool_end":
                        yield {
                            "type": "reasoning",
                            "data": {
                                "step": chunk.name or "Tool",
                                "step_id": chunk.span_id,
                                "status": "complete",
                                "message": f"Tool {chunk.name} completed",
                                "output": chunk.data.get("output") if chunk.data else None
                            }
                        }
