"""
EventEmitter - Fire-and-forget event emission abstraction.

This provides a clean interface for node executors to emit events
without knowing about queues, visibility, or downstream consumers.
All methods are non-blocking and swallow errors.
"""
import asyncio
import logging
from typing import Any, Optional

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
    
    def __init__(
        self,
        queue: asyncio.Queue,
        run_id: str,
        mode: str = "debug",
        orchestration_surface: str = "option_a_graphspec_v2",
    ):
        self._queue = queue
        self._run_id = run_id
        self._mode = mode
        self._orchestration_surface = orchestration_surface

    def emit_token(self, content: str, node_id: str, span_id: Optional[str] = None) -> None:
        """Emit a token (streaming content) event."""
        self._emit(ExecutionEvent(
            event="token",
            data={"content": content},
            run_id=self._run_id,
            span_id=span_id,
            name=node_id,
            visibility=EventVisibility.CLIENT_SAFE,
            metadata=self._metadata()
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
            metadata=self._metadata()
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
            metadata=self._metadata()
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
            metadata=self._metadata()
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
            metadata=self._metadata()
        ))

    def emit_retrieval(self, results: Any, node_id: Optional[str] = None) -> None:
        """Emit a retrieval artifact event."""
        self._emit(ExecutionEvent(
            event="retrieval",
            data={"results": results},
            run_id=self._run_id,
            span_id=node_id,
            visibility=EventVisibility.INTERNAL,
            metadata=self._metadata()
        ))
    
    def emit_error(self, error: str, node_id: Optional[str] = None) -> None:
        """Emit an error event."""
        self._emit(ExecutionEvent(
            event="error",
            data={"error": error},
            run_id=self._run_id,
            span_id=node_id,
            visibility=EventVisibility.CLIENT_SAFE,
            metadata=self._metadata()
        ))

    def emit_orchestration_spawn_decision(
        self,
        *,
        node_id: str,
        target_agent_id: Optional[str],
        target_agent_slug: Optional[str],
        spawned_run_ids: list[str],
        idempotent: bool,
    ) -> None:
        self._emit(ExecutionEvent(
            event="orchestration.spawn_decision",
            data={
                "target_agent_id": target_agent_id,
                "target_agent_slug": target_agent_slug,
                "spawned_run_ids": list(spawned_run_ids),
                "idempotent": bool(idempotent),
            },
            run_id=self._run_id,
            span_id=node_id,
            visibility=EventVisibility.INTERNAL,
            metadata=self._metadata({"category": "orchestration"}),
        ))

    def emit_orchestration_child_lifecycle(
        self,
        *,
        node_id: str,
        child_run_id: str,
        lifecycle_status: str,
        orchestration_group_id: Optional[str] = None,
    ) -> None:
        self._emit(ExecutionEvent(
            event="orchestration.child_lifecycle",
            data={
                "child_run_id": child_run_id,
                "status": lifecycle_status,
                "orchestration_group_id": orchestration_group_id,
            },
            run_id=self._run_id,
            span_id=node_id,
            visibility=EventVisibility.INTERNAL,
            metadata=self._metadata({"category": "orchestration"}),
        ))

    def emit_orchestration_join_decision(
        self,
        *,
        node_id: str,
        group_id: str,
        mode: str,
        status: str,
        complete: bool,
        success_count: int,
        failure_count: int,
        running_count: int,
    ) -> None:
        self._emit(ExecutionEvent(
            event="orchestration.join_decision",
            data={
                "group_id": group_id,
                "mode": mode,
                "status": status,
                "complete": bool(complete),
                "success_count": int(success_count),
                "failure_count": int(failure_count),
                "running_count": int(running_count),
            },
            run_id=self._run_id,
            span_id=node_id,
            visibility=EventVisibility.INTERNAL,
            metadata=self._metadata({"category": "orchestration"}),
        ))

    def emit_orchestration_policy_deny(
        self,
        *,
        node_id: str,
        action: str,
        reason: str,
    ) -> None:
        self._emit(ExecutionEvent(
            event="orchestration.policy_deny",
            data={"action": action, "reason": reason},
            run_id=self._run_id,
            span_id=node_id,
            visibility=EventVisibility.CLIENT_SAFE,
            metadata=self._metadata({"category": "orchestration"}),
        ))

    def emit_orchestration_cancellation_propagation(
        self,
        *,
        node_id: str,
        reason: Optional[str],
        cancelled_run_ids: list[str],
        include_root: Optional[bool] = None,
    ) -> None:
        payload = {
            "reason": reason,
            "cancelled_run_ids": list(cancelled_run_ids),
            "count": len(cancelled_run_ids),
        }
        if include_root is not None:
            payload["include_root"] = bool(include_root)
        self._emit(ExecutionEvent(
            event="orchestration.cancellation_propagation",
            data=payload,
            run_id=self._run_id,
            span_id=node_id,
            visibility=EventVisibility.INTERNAL,
            metadata=self._metadata({"category": "orchestration"}),
        ))

    def _metadata(self, extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        metadata = {
            "mode": self._mode,
            "surface": self._orchestration_surface,
        }
        if isinstance(extra, dict):
            metadata.update(extra)
        return metadata

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
