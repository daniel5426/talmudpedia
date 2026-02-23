from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, AsyncGenerator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from app.db.postgres.engine import sessionmaker
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import PublishedApp
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_queue_service import PublishedAppCodingQueueService

logger = logging.getLogger(__name__)

_TERMINAL_EVENTS = {"run.completed", "run.failed", "run.cancelled", "run.paused"}
_TERMINAL_RUN_STATUSES = {
    RunStatus.completed.value,
    RunStatus.failed.value,
    RunStatus.cancelled.value,
    RunStatus.paused.value,
}


@dataclass
class _MonitorState:
    run_id: str
    task: asyncio.Task
    subscribers: set[asyncio.Queue] = field(default_factory=set)


class PublishedAppCodingRunMonitor:
    _monitors: dict[str, _MonitorState] = {}
    _monitors_lock = asyncio.Lock()
    _session_factory = sessionmaker

    def __init__(self, db: AsyncSession):
        self.db = db
        bind = self._resolve_session_factory_bind(db)
        if bind is not None:
            self.__class__._session_factory = async_sessionmaker(bind=bind, expire_on_commit=False, class_=AsyncSession)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _resolve_session_factory_bind(db: AsyncSession) -> AsyncEngine | None:
        direct_bind = getattr(db, "bind", None)
        if isinstance(direct_bind, AsyncConnection):
            return direct_bind.engine
        if isinstance(direct_bind, AsyncEngine):
            return direct_bind

        bind = None
        try:
            bind = db.get_bind()
        except Exception:
            bind = None
        if isinstance(bind, AsyncConnection):
            return bind.engine
        if isinstance(bind, AsyncEngine):
            return bind
        return None

    @staticmethod
    def _terminal_event_for_status(status: str) -> str:
        normalized = str(status or "").strip().lower()
        if normalized == RunStatus.completed.value:
            return "run.completed"
        if normalized == RunStatus.cancelled.value:
            return "run.cancelled"
        if normalized == RunStatus.paused.value:
            return "run.paused"
        return "run.failed"

    @staticmethod
    def _envelope(*, event: str, run_id: UUID, app_id: UUID, stage: str, payload: dict[str, Any], diagnostics: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return {
            "event": event,
            "run_id": str(run_id),
            "app_id": str(app_id),
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "payload": payload,
            "diagnostics": diagnostics or [],
        }

    @classmethod
    async def _emit_to_subscribers(cls, *, run_id: UUID, payload: dict[str, Any]) -> None:
        async with cls._monitors_lock:
            state = cls._monitors.get(str(run_id))
            subscribers = list(state.subscribers) if state is not None else []
        for queue in subscribers:
            try:
                queue.put_nowait(payload)
            except Exception:
                pass

    @classmethod
    async def _close_subscribers(cls, *, run_id: UUID) -> None:
        async with cls._monitors_lock:
            state = cls._monitors.get(str(run_id))
            subscribers = list(state.subscribers) if state is not None else []
            if state is not None:
                state.subscribers.clear()
        for queue in subscribers:
            try:
                queue.put_nowait(None)
            except Exception:
                pass

    async def _try_acquire_advisory_lock(self, *, run_id: UUID) -> tuple[bool, int | None]:
        dialect_name = getattr(getattr(self.db.get_bind(), "dialect", None), "name", "")
        if dialect_name != "postgresql":
            return True, None
        key = (run_id.int & ((1 << 63) - 1))
        result = await self.db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": int(key)})
        acquired = bool(result.scalar_one_or_none())
        return acquired, int(key)

    async def _release_advisory_lock(self, *, advisory_key: int | None) -> None:
        if advisory_key is None:
            return
        try:
            await self.db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": int(advisory_key)})
        except Exception:
            logger.exception("CODING_AGENT_MONITOR advisory_unlock_failed key=%s", advisory_key)

    async def ensure_monitor(self, *, app_id: UUID, run_id: UUID) -> _MonitorState | None:
        run = await self.db.get(AgentRun, run_id)
        if run is None:
            return None
        status = run.status.value if hasattr(run.status, "value") else str(run.status)
        if status in _TERMINAL_RUN_STATUSES:
            return None

        run_key = str(run_id)
        async with self.__class__._monitors_lock:
            existing = self.__class__._monitors.get(run_key)
            if existing is not None and not existing.task.done():
                return existing

            task = asyncio.create_task(self.__class__._runner_main(app_id=app_id, run_id=run_id))
            state = _MonitorState(run_id=run_key, task=task)
            self.__class__._monitors[run_key] = state
            logger.info("CODING_AGENT_MONITOR started run_id=%s app_id=%s", run_id, app_id)
            return state

    @classmethod
    async def ensure_monitor_detached(cls, *, app_id: UUID, run_id: UUID) -> None:
        try:
            async with cls._session_factory() as db:
                monitor = cls(db)
                await monitor.ensure_monitor(app_id=app_id, run_id=run_id)
        except Exception:
            logger.exception("CODING_AGENT_MONITOR detached_start_failed run_id=%s app_id=%s", run_id, app_id)

    async def stream_events(self, *, app_id: UUID, run_id: UUID) -> AsyncGenerator[dict[str, Any], None]:
        runtime = PublishedAppCodingAgentRuntimeService(self.db)
        run = await runtime.get_run_for_app(app_id=app_id, run_id=run_id)
        run_status = run.status.value if hasattr(run.status, "value") else str(run.status)

        if run_status in _TERMINAL_RUN_STATUSES:
            payload = runtime.serialize_run(run)
            diagnostics: list[dict[str, Any]] = []
            if run_status == RunStatus.failed.value:
                diagnostics = [{"message": run.error_message or "run failed"}]
            yield self._envelope(
                event=self._terminal_event_for_status(run_status),
                run_id=run.id,
                app_id=UUID(str(app_id)),
                stage="run",
                payload=payload,
                diagnostics=diagnostics,
            )
            return

        state = await self.ensure_monitor(app_id=app_id, run_id=run_id)
        if state is None:
            refreshed = await runtime.get_run_for_app(app_id=app_id, run_id=run_id)
            refreshed_status = refreshed.status.value if hasattr(refreshed.status, "value") else str(refreshed.status)
            payload = runtime.serialize_run(refreshed)
            diagnostics: list[dict[str, Any]] = []
            if refreshed_status == RunStatus.failed.value:
                diagnostics = [{"message": refreshed.error_message or "run failed"}]
            yield self._envelope(
                event=self._terminal_event_for_status(refreshed_status),
                run_id=refreshed.id,
                app_id=UUID(str(app_id)),
                stage="run",
                payload=payload,
                diagnostics=diagnostics,
            )
            return

        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        async with self.__class__._monitors_lock:
            current = self.__class__._monitors.get(str(run_id))
            if current is not None:
                current.subscribers.add(queue)

        try:
            while True:
                payload = await queue.get()
                if payload is None:
                    break
                yield payload
                if str(payload.get("event") or "") in _TERMINAL_EVENTS:
                    break
        finally:
            async with self.__class__._monitors_lock:
                current = self.__class__._monitors.get(str(run_id))
                if current is not None:
                    current.subscribers.discard(queue)

    @classmethod
    async def _runner_main(cls, *, app_id: UUID, run_id: UUID) -> None:
        advisory_key: int | None = None
        try:
            async with cls._session_factory() as db:
                monitor = cls(db)
                lock_acquired, advisory_key = await monitor._try_acquire_advisory_lock(run_id=run_id)
                if not lock_acquired:
                    logger.info("CODING_AGENT_MONITOR advisory_lock_not_acquired run_id=%s app_id=%s", run_id, app_id)
                    return

                runtime = PublishedAppCodingAgentRuntimeService(db)
                queue_service = PublishedAppCodingQueueService(db)

                app = await db.get(PublishedApp, app_id)
                if app is None:
                    return
                run = await runtime.get_run_for_app(app_id=app_id, run_id=run_id)

                terminal_emitted = False
                async for envelope in runtime.stream_run_events(app=app, run=run):
                    payload = {
                        "event": str(envelope.get("event") or ""),
                        "run_id": str(run_id),
                        "app_id": str(app_id),
                        "ts": str(envelope.get("ts") or datetime.now(timezone.utc).isoformat()),
                        "stage": str(envelope.get("stage") or "run"),
                        "payload": dict(envelope.get("payload") or {}),
                        "diagnostics": list(envelope.get("diagnostics") or []),
                    }
                    await cls._emit_to_subscribers(run_id=run_id, payload=payload)
                    if payload["event"] in _TERMINAL_EVENTS:
                        terminal_emitted = True

                refreshed_run = await db.get(AgentRun, run_id)
                if refreshed_run is None:
                    return

                refreshed_status = refreshed_run.status.value if hasattr(refreshed_run.status, "value") else str(refreshed_run.status)
                if refreshed_status not in _TERMINAL_RUN_STATUSES:
                    refreshed_run.status = RunStatus.failed
                    refreshed_run.error_message = "OpenCode stream ended before terminal event"
                    refreshed_run.completed_at = cls._now()
                    await runtime._clear_preview_run_lock(
                        app_id=refreshed_run.published_app_id,
                        actor_id=refreshed_run.initiator_user_id or refreshed_run.user_id,
                        run_id=refreshed_run.id,
                    )
                    await db.commit()
                    refreshed_status = RunStatus.failed.value

                if not terminal_emitted:
                    terminal_payload = runtime.serialize_run(refreshed_run)
                    diagnostics = []
                    if refreshed_status == RunStatus.failed.value:
                        diagnostics = [{"message": refreshed_run.error_message or "run failed"}]
                    await cls._emit_to_subscribers(
                        run_id=run_id,
                        payload=cls._envelope(
                            event=cls._terminal_event_for_status(refreshed_status),
                            run_id=run_id,
                            app_id=app_id,
                            stage="run",
                            payload=terminal_payload,
                            diagnostics=diagnostics,
                        ),
                    )

                if refreshed_status in _TERMINAL_RUN_STATUSES:
                    next_run = await queue_service.dispatch_next_for_terminal_run(terminal_run=refreshed_run)
                    if next_run is not None:
                        asyncio.create_task(
                            cls.ensure_monitor_detached(app_id=app_id, run_id=next_run.id)
                        )
        except Exception as exc:
            logger.exception("CODING_AGENT_MONITOR runner_failed run_id=%s app_id=%s", run_id, app_id)
            try:
                async with cls._session_factory() as db:
                    runtime = PublishedAppCodingAgentRuntimeService(db)
                    failed_run = await db.get(AgentRun, run_id)
                    if failed_run is not None:
                        status = failed_run.status.value if hasattr(failed_run.status, "value") else str(failed_run.status)
                        if status not in _TERMINAL_RUN_STATUSES:
                            failed_run.status = RunStatus.failed
                            failed_run.error_message = str(exc)
                            failed_run.completed_at = cls._now()
                            await runtime._clear_preview_run_lock(
                                app_id=failed_run.published_app_id,
                                actor_id=failed_run.initiator_user_id or failed_run.user_id,
                                run_id=failed_run.id,
                            )
                            await db.commit()
                            payload = runtime.serialize_run(failed_run)
                            await cls._emit_to_subscribers(
                                run_id=run_id,
                                payload=cls._envelope(
                                    event="run.failed",
                                    run_id=run_id,
                                    app_id=app_id,
                                    stage="run",
                                    payload=payload,
                                    diagnostics=[{"message": str(exc)}],
                                ),
                            )
            except Exception:
                logger.exception("CODING_AGENT_MONITOR fail_closed_terminalize_failed run_id=%s", run_id)
        finally:
            try:
                async with cls._session_factory() as db:
                    monitor = cls(db)
                    await monitor._release_advisory_lock(advisory_key=advisory_key)
            except Exception:
                pass

            await cls._close_subscribers(run_id=run_id)
            async with cls._monitors_lock:
                cls._monitors.pop(str(run_id), None)
                logger.info("CODING_AGENT_MONITOR stopped run_id=%s app_id=%s", run_id, app_id)
