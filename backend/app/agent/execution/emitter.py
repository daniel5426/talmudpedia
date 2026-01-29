"""
EventEmitter - Fire-and-forget event emission abstraction.

This provides a clean interface for node executors to emit events
without knowing about queues, visibility, or downstream consumers.
All methods are non-blocking and swallow errors.
"""
import asyncio
import logging
from typing import Any, Optional
from uuid import UUID

from .types import ExecutionEvent, EventVisibility

logger = logging.getLogger(__name__)


import contextvars

# ContextVar to hold the active emitter for the current async task
# This allows node executors to access the emitter without partial plumbing through LangGraph config
active_emitter = contextvars.ContextVar("active_emitter", default=None)

class EventEmitter:
    """
    Abstraction for emitting execution events from node executors.
    
    Contract:
    - All emit_* methods are non-blocking.
    - All emit_* methods never throw (errors are logged).
    - All emit_* methods never await I/O.
    - All emit_* methods never affect control flow.
    """
    
    def __init__(self, queue: asyncio.Queue, run_id: str, mode: str = "debug"):
        self._queue = queue
        self._run_id = run_id
        self._mode = mode
    
    def emit_token(self, content: str, node_id: str, span_id: Optional[str] = None) -> None:
        """Emit a token (streaming content) event."""
        self._emit(ExecutionEvent(
            event="token",
            data={"content": content},
            run_id=self._run_id,
            span_id=span_id,
            name=node_id,
            visibility=EventVisibility.CLIENT_SAFE,
            metadata={"mode": self._mode}
        ))
    
    def emit_node_start(self, node_id: str, name: str, node_type: str, input_data: Any = None) -> None:
        """Emit a node start event."""
        self._emit(ExecutionEvent(
            event="node_start",
            data={"input": input_data, "type": node_type} if input_data else {"type": node_type},
            run_id=self._run_id,
            span_id=node_id,
            name=name,
            visibility=EventVisibility.INTERNAL,
            metadata={"mode": self._mode}
        ))
    
    def emit_tool_start(self, tool_name: str, input_data: Any = None, node_id: Optional[str] = None) -> None:
        """Emit a tool start event."""
        data = {"input": input_data} if input_data else {}
        # Lift message to top level if present in input (for UI display)
        if isinstance(input_data, dict) and "message" in input_data:
            data["message"] = input_data["message"]

        self._emit(ExecutionEvent(
            event="on_tool_start",
            data=data,
            run_id=self._run_id,
            span_id=node_id,
            name=tool_name,
            visibility=EventVisibility.INTERNAL,
            metadata={"mode": self._mode}
        ))

    def emit_tool_end(self, tool_name: str, output_data: Any = None, node_id: Optional[str] = None) -> None:
        """Emit a tool end event."""
        self._emit(ExecutionEvent(
            event="on_tool_end",
            data={"output": output_data} if output_data else {},
            run_id=self._run_id,
            span_id=node_id,
            name=tool_name,
            visibility=EventVisibility.INTERNAL,
            metadata={"mode": self._mode}
        ))
    
    def emit_node_end(self, node_id: str, name: str, node_type: str, output_data: Any = None) -> None:
        """Emit a node end event."""
        self._emit(ExecutionEvent(
            event="node_end",
            data={"output": output_data, "type": node_type} if output_data else {"type": node_type},
            run_id=self._run_id,
            span_id=node_id,
            name=name,
            visibility=EventVisibility.INTERNAL,
            metadata={"mode": self._mode}
        ))
    
    def emit_error(self, error: str, node_id: Optional[str] = None) -> None:
        """Emit an error event."""
        self._emit(ExecutionEvent(
            event="error",
            data={"error": error},
            run_id=self._run_id,
            span_id=node_id,
            visibility=EventVisibility.CLIENT_SAFE,
            metadata={"mode": self._mode}
        ))
    
    def _emit(self, event: ExecutionEvent) -> None:
        """
        Fire-and-forget event emission.
        Uses put_nowait to avoid blocking. If queue is full, logs warning.
        """
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(f"[EventEmitter] Queue full, dropping event: {event.event}")
        except Exception as e:
            logger.error(f"[EventEmitter] Failed to emit event: {e}")
