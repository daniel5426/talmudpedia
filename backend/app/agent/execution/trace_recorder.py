from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.execution.types import ExecutionEvent
from app.db.postgres.models.agents import AgentTrace

logger = logging.getLogger(__name__)

_DEFAULT_TRACE_FILE = "/tmp/talmudpedia-agent-execution-events.jsonl"
_FILE_WRITE_LOCK = threading.Lock()


def execution_trace_file_logging_enabled() -> bool:
    raw = os.getenv("AGENT_EXECUTION_EVENT_LOG_ENABLED", "1")
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def execution_trace_file_path() -> str:
    raw = os.getenv("AGENT_EXECUTION_EVENT_LOG_FILE", _DEFAULT_TRACE_FILE)
    path = str(raw or "").strip()
    return path or _DEFAULT_TRACE_FILE


class ExecutionTraceRecorder:
    def __init__(self, serializer: Callable[[Any], Any]):
        self._serializer = serializer
        self._pending_queue: asyncio.Queue[tuple[UUID, dict[str, Any]] | None] = asyncio.Queue()
        self._worker_task: asyncio.Task[Any] | None = None

    def _ensure_worker(self) -> None:
        if self._worker_task is not None and not self._worker_task.done():
            return
        self._worker_task = asyncio.create_task(self._drain_pending_queue(), name="trace-recorder-persist")

    def schedule_persist(self, run_id: UUID, event: ExecutionEvent | dict[str, Any], *, sequence: int) -> None:
        payload = self._normalize_event(run_id, event, sequence=sequence)
        self._mirror_to_file(payload)
        self._ensure_worker()
        self._pending_queue.put_nowait((run_id, payload))

    async def drain(self) -> None:
        if self._worker_task is None:
            return
        await self._pending_queue.join()
        await self._pending_queue.put(None)
        worker = self._worker_task
        self._worker_task = None
        if worker is not None:
            await asyncio.gather(worker, return_exceptions=True)

    async def _drain_pending_queue(self) -> None:
        while True:
            item = await self._pending_queue.get()
            try:
                if item is None:
                    return
                run_id, payload = item
                await self._persist_safe(run_id, payload)
            finally:
                self._pending_queue.task_done()

    async def _persist_safe(self, run_id: UUID, payload: dict[str, Any]) -> None:
        from app.db.postgres.engine import sessionmaker as get_session

        try:
            async with get_session() as session:
                await self.save_event(run_id, session, payload)
                await session.commit()
        except Exception as exc:
            logger.error("Trace persistence failed [Run %s]: %s", run_id, exc)

    async def save_event(self, run_id: UUID, db: AsyncSession, event: ExecutionEvent | dict[str, Any]) -> AgentTrace:
        payload = self._normalize_event(run_id, event)
        timestamp = self._parse_timestamp(payload.get("ts"))
        metadata = dict(payload.get("metadata") or {})
        metadata.update(
            {
                "sequence": int(payload.get("sequence") or 0),
                "visibility": payload.get("visibility"),
                "tags": list(payload.get("tags") or []),
                "event_data": payload.get("data"),
                "logged_at": payload.get("ts"),
                "source_run_id": payload.get("source_run_id"),
                "parent_ids": list(payload.get("parent_ids") or []),
            }
        )

        trace = AgentTrace(
            id=uuid4(),
            run_id=run_id,
            span_id=str(payload.get("span_id") or f"event-{payload.get('sequence') or uuid4().hex}"),
            parent_span_id=payload.get("parent_span_id"),
            name=str(payload.get("name") or payload.get("event") or "event"),
            span_type=str(payload.get("event") or "event"),
            inputs=payload.get("inputs"),
            outputs=payload.get("outputs"),
            start_time=timestamp,
            end_time=timestamp,
            metadata_=metadata,
        )
        db.add(trace)
        return trace

    async def list_events(
        self,
        db: AsyncSession,
        run_id: UUID,
        *,
        after_sequence: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        result = await db.execute(
            select(AgentTrace).where(AgentTrace.run_id == run_id)
        )
        traces = list(result.scalars().all())
        traces.sort(
            key=lambda trace: (
                int((trace.metadata_ or {}).get("sequence") or 0),
                trace.start_time or datetime.min.replace(tzinfo=timezone.utc),
            )
        )

        events: list[dict[str, Any]] = []
        for trace in traces:
            metadata = dict(trace.metadata_ or {})
            sequence = int(metadata.get("sequence") or 0)
            if after_sequence is not None and sequence <= int(after_sequence):
                continue
            events.append(
                {
                    "id": str(trace.id),
                    "run_id": str(run_id),
                    "sequence": sequence,
                    "timestamp": trace.start_time.isoformat() if trace.start_time else None,
                    "event": trace.span_type,
                    "name": trace.name,
                    "span_id": trace.span_id,
                    "parent_span_id": trace.parent_span_id,
                    "visibility": metadata.get("visibility"),
                    "tags": list(metadata.get("tags") or []),
                    "data": metadata.get("event_data"),
                    "inputs": trace.inputs,
                    "outputs": trace.outputs,
                    "metadata": {
                        key: value
                        for key, value in metadata.items()
                        if key not in {"sequence", "visibility", "tags", "event_data", "logged_at", "source_run_id", "parent_ids"}
                    },
                }
            )
            if limit is not None and len(events) >= max(0, int(limit)):
                break
        return events

    def _normalize_event(
        self,
        run_id: UUID,
        event: ExecutionEvent | dict[str, Any],
        *,
        sequence: int | None = None,
    ) -> dict[str, Any]:
        raw = event.model_dump() if isinstance(event, ExecutionEvent) else dict(event or {})
        if {"ts", "event", "data", "source_run_id", "inputs", "outputs"}.issubset(raw.keys()):
            payload = dict(raw)
            if sequence is not None:
                payload["sequence"] = int(sequence)
            return payload
        payload_data = self._serializer(raw.get("data"))
        original_span_id = raw.get("span_id")
        original_run_id = raw.get("run_id")
        parent_ids = list(raw.get("parent_ids") or [])
        event_name = str(raw.get("event") or "event")
        seq = int(sequence if sequence is not None else raw.get("sequence") or 0)
        payload = {
            "ts": raw.get("ts") or datetime.now(timezone.utc).isoformat(),
            "sequence": seq,
            "event": event_name,
            "name": raw.get("name") or event_name,
            "span_id": str(original_span_id) if original_span_id not in (None, "") else f"{event_name}:{seq or uuid4().hex}",
            "parent_span_id": str(parent_ids[-1]) if parent_ids else None,
            "source_run_id": str(original_run_id) if original_run_id not in (None, "") else str(run_id),
            "visibility": raw.get("visibility"),
            "tags": list(raw.get("tags") or []),
            "metadata": self._serializer(raw.get("metadata") or {}),
            "data": payload_data,
            "inputs": payload_data if event_name.endswith("_start") else None,
            "outputs": None if event_name.endswith("_start") else payload_data,
            "parent_ids": parent_ids,
        }
        return payload

    def _mirror_to_file(self, payload: dict[str, Any]) -> None:
        if not execution_trace_file_logging_enabled():
            return
        try:
            rendered = json.dumps(payload, sort_keys=True, default=str)
        except Exception:
            rendered = str(payload)
        try:
            with _FILE_WRITE_LOCK:
                with open(execution_trace_file_path(), "a", encoding="utf-8") as handle:
                    handle.write(rendered + "\n")
        except Exception:
            pass

    @staticmethod
    def _parse_timestamp(raw: Any) -> datetime:
        if isinstance(raw, datetime):
            return raw
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except Exception:
                pass
        return datetime.now(timezone.utc)
