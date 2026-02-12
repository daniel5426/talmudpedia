import logging
from typing import AsyncGenerator, Dict, Any, Union

from .types import ExecutionMode, EventVisibility, ExecutionEvent

logger = logging.getLogger(__name__)

class StreamAdapter:
    """
    Adapts the internal agent execution stream for different consumers (Modes).
    Enforces filtering rules based on EventVisibility.
    """

    _PRODUCTION_LEGACY_ALLOW = {"on_chat_model_stream", "run_status"}
    _TOOL_LIFECYCLE_EVENTS = {"on_tool_start", "on_tool_end"}

    @classmethod
    def _is_client_safe(cls, visibility: Any) -> bool:
        if isinstance(visibility, EventVisibility):
            return visibility == EventVisibility.CLIENT_SAFE
        if isinstance(visibility, str):
            return visibility.strip().lower() == EventVisibility.CLIENT_SAFE.value
        return False

    @classmethod
    def _reasoning_event(
        cls,
        *,
        event_type: str,
        event_name: str | None,
        step_id: str | None,
        data: Dict[str, Any] | None,
    ) -> Dict[str, Any] | None:
        payload = data or {}
        if event_type == "on_tool_start":
            return {
                "type": "reasoning",
                "data": {
                    "step": event_name or "Tool",
                    "step_id": step_id,
                    "status": "active",
                    "message": payload.get("message") or f"Calling tool {event_name}...",
                },
            }
        if event_type == "on_tool_end":
            return {
                "type": "reasoning",
                "data": {
                    "step": event_name or "Tool",
                    "step_id": step_id,
                    "status": "complete",
                    "message": f"Tool {event_name} completed",
                    "output": payload.get("output"),
                },
            }
        return None
    
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
                is_tool_lifecycle = event_type in StreamAdapter._TOOL_LIFECYCLE_EVENTS
                
                # Heuristics for untagged events (Safety net during refactor)
                if mode == ExecutionMode.PRODUCTION:
                    # PROD includes client-safe events + explicit tool lifecycle + narrow legacy allow-list.
                    if not (
                        StreamAdapter._is_client_safe(visibility)
                        or is_tool_lifecycle
                        or event_type in StreamAdapter._PRODUCTION_LEGACY_ALLOW
                    ):
                        continue
                
                # If we are here, it's allowed or we are in DEBUG
                yield chunk
                
                # Synthesize reasoning for tool lifecycle in both DEBUG and PRODUCTION.
                reasoning = StreamAdapter._reasoning_event(
                    event_type=event_type,
                    event_name=chunk.get("name"),
                    step_id=chunk.get("span_id"),
                    data=chunk.get("data", {}),
                )
                if reasoning:
                    yield reasoning
                continue

            if isinstance(chunk, ExecutionEvent):
                if mode == ExecutionMode.PRODUCTION:
                    is_tool_lifecycle = chunk.event in StreamAdapter._TOOL_LIFECYCLE_EVENTS
                    if chunk.visibility == EventVisibility.CLIENT_SAFE or is_tool_lifecycle:
                        payload = chunk.model_dump(mode="json")
                        yield payload
                        reasoning = StreamAdapter._reasoning_event(
                            event_type=chunk.event,
                            event_name=chunk.name,
                            step_id=chunk.span_id,
                            data=chunk.data,
                        )
                        if reasoning:
                            yield reasoning
                else:
                    # DEBUG mode: Yield everything
                    # PLUS: Synthesize "reasoning" events for better UI
                    yield chunk.model_dump(mode="json")
                    reasoning = StreamAdapter._reasoning_event(
                        event_type=chunk.event,
                        event_name=chunk.name,
                        step_id=chunk.span_id,
                        data=chunk.data,
                    )
                    if reasoning:
                        yield reasoning
