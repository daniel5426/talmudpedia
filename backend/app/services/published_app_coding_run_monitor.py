from __future__ import annotations

import asyncio
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import time
from typing import Any, AsyncGenerator
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from app.db.postgres.engine import sessionmaker
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import PublishedApp
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_queue_service import PublishedAppCodingQueueService
from app.services.published_app_coding_run_monitor_config import (
    monitor_inactivity_timeout_seconds,
    monitor_max_runtime_seconds,
    monitor_poll_interval_seconds,
    monitor_status_probe_interval_seconds,
    monitor_trace,
)

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
    event_backlog: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=6000))


class PublishedAppCodingRunMonitor:
    _monitors: dict[str, _MonitorState] = {}
    _monitors_lock = asyncio.Lock()
    _session_factory = sessionmaker
    _trace = staticmethod(monitor_trace)
    _monitor_inactivity_timeout_seconds = staticmethod(monitor_inactivity_timeout_seconds)
    _monitor_poll_interval_seconds = staticmethod(monitor_poll_interval_seconds)
    _monitor_max_runtime_seconds = staticmethod(monitor_max_runtime_seconds)
    _monitor_status_probe_interval_seconds = staticmethod(monitor_status_probe_interval_seconds)

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
        run_key = str(run_id)
        async with cls._monitors_lock:
            state = cls._monitors.get(run_key)
            if state is not None:
                # Keep an in-memory backlog so late stream subscribers can replay
                # already-emitted events without DB replay semantics.
                state.event_backlog.append(dict(payload))
            subscribers = list(state.subscribers) if state is not None else []
        event_name = str(payload.get("event") or "").strip()
        if event_name and event_name != "assistant.delta":
            cls._trace(
                "monitor.emit",
                run_id=run_key,
                run_event=event_name,
                subscriber_count=len(subscribers),
            )
            if event_name in _TERMINAL_EVENTS:
                run_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
                cls._trace(
                    "monitor.terminal_payload",
                    run_id=run_key,
                    run_event=event_name,
                    status=run_payload.get("status"),
                    result_revision_id=run_payload.get("result_revision_id"),
                    checkpoint_revision_id=run_payload.get("checkpoint_revision_id"),
                    error=run_payload.get("error"),
                )
        for queue in subscribers:
            try:
                queue.put_nowait(dict(payload))
            except Exception as exc:
                cls._trace(
                    "monitor.emit_queue_put_failed",
                    run_id=str(run_id),
                    run_event=event_name,
                    error=str(exc),
                )

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
            self.__class__._trace("monitor.started", run_id=str(run_id), app_id=str(app_id))
            return state

    @classmethod
    async def ensure_monitor_detached(cls, *, app_id: UUID, run_id: UUID) -> None:
        try:
            async with cls._session_factory() as db:
                monitor = cls(db)
                await monitor.ensure_monitor(app_id=app_id, run_id=run_id)
        except Exception:
            logger.exception("CODING_AGENT_MONITOR detached_start_failed run_id=%s app_id=%s", run_id, app_id)

    @classmethod
    async def _finalize_completed_run_detached(cls, *, app_id: UUID, run_id: UUID) -> None:
        try:
            async with cls._session_factory() as db:
                runtime = PublishedAppCodingAgentRuntimeService(db)
                cls._trace(
                    "monitor.post_complete_finalize_begin",
                    run_id=str(run_id),
                    app_id=str(app_id),
                )
                revision_id, checkpoint_id = await runtime.finalize_completed_run_postprocessing(run_id=run_id)
                cls._trace(
                    "monitor.post_complete_finalize_done",
                    run_id=str(run_id),
                    app_id=str(app_id),
                    revision_id=revision_id,
                    checkpoint_id=checkpoint_id,
                )
        except Exception as exc:
            logger.exception(
                "CODING_AGENT_MONITOR post_complete_finalize_failed run_id=%s app_id=%s",
                run_id,
                app_id,
            )
            cls._trace(
                "monitor.post_complete_finalize_failed",
                run_id=str(run_id),
                app_id=str(app_id),
                error=str(exc),
                error_type=exc.__class__.__name__,
            )

    async def stream_events(self, *, app_id: UUID, run_id: UUID) -> AsyncGenerator[dict[str, Any], None]:
        runtime = PublishedAppCodingAgentRuntimeService(self.db)
        run = await runtime.get_run_for_app(app_id=app_id, run_id=run_id)

        async def _load_run_fresh() -> AgentRun | None:
            dialect_name = str(getattr(getattr(self.db.get_bind(), "dialect", None), "name", "") or "").strip().lower()
            if dialect_name == "sqlite":
                result = await self.db.execute(
                    select(AgentRun)
                    .where(AgentRun.id == run_id)
                    .execution_options(populate_existing=True)
                )
                refreshed = result.scalar_one_or_none()
                if refreshed is None:
                    return None
                refreshed_app_id = str(getattr(refreshed, "published_app_id", "") or "")
                if refreshed_app_id != str(app_id):
                    return None
                return refreshed

            try:
                async with self.__class__._session_factory() as probe_db:
                    result = await probe_db.execute(
                        select(AgentRun)
                        .where(AgentRun.id == run_id)
                        .execution_options(populate_existing=True)
                    )
                    refreshed = result.scalar_one_or_none()
                    if refreshed is None:
                        return None
                    refreshed_app_id = str(getattr(refreshed, "published_app_id", "") or "")
                    if refreshed_app_id != str(app_id):
                        return None
                    return refreshed
            except Exception:
                result = await self.db.execute(
                    select(AgentRun)
                    .where(AgentRun.id == run_id)
                    .execution_options(populate_existing=True)
                )
                refreshed = result.scalar_one_or_none()
                if refreshed is None:
                    return None
                refreshed_app_id = str(getattr(refreshed, "published_app_id", "") or "")
                if refreshed_app_id != str(app_id):
                    return None
                return refreshed

        run = await _load_run_fresh() or run
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

        # Keep subscriber queue unbounded so assistant deltas are never dropped
        # under transient plan/tool event bursts.
        queue: asyncio.Queue = asyncio.Queue()
        attached = False
        backlog_snapshot: list[dict[str, Any]] = []
        async with self.__class__._monitors_lock:
            current = self.__class__._monitors.get(str(run_id))
            if current is not None:
                current.subscribers.add(queue)
                backlog_snapshot = [dict(item) for item in current.event_backlog]
                attached = True
                self.__class__._trace(
                    "monitor.subscriber_attached",
                    run_id=str(run_id),
                    app_id=str(app_id),
                    subscriber_count=len(current.subscribers),
                    backlog_size=len(backlog_snapshot),
                )

        if not attached:
            self.__class__._trace(
                "monitor.subscriber_attach_miss",
                run_id=str(run_id),
                app_id=str(app_id),
            )

        try:
            for payload in backlog_snapshot:
                yield payload
                if str(payload.get("event") or "") in _TERMINAL_EVENTS:
                    return
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    refreshed = await _load_run_fresh()
                    if refreshed is None:
                        break
                    refreshed_status = refreshed.status.value if hasattr(refreshed.status, "value") else str(refreshed.status)
                    if refreshed_status in _TERMINAL_RUN_STATUSES:
                        diagnostics: list[dict[str, Any]] = []
                        if refreshed_status == RunStatus.failed.value:
                            diagnostics = [{"message": refreshed.error_message or "run failed"}]
                        yield self._envelope(
                            event=self._terminal_event_for_status(refreshed_status),
                            run_id=refreshed.id,
                            app_id=UUID(str(app_id)),
                            stage="run",
                            payload=runtime.serialize_run(refreshed),
                            diagnostics=diagnostics,
                        )
                        break
                    continue
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
                    self.__class__._trace(
                        "monitor.subscriber_detached",
                        run_id=str(run_id),
                        app_id=str(app_id),
                        subscriber_count=len(current.subscribers),
                    )

    @classmethod
    async def _runner_main(cls, *, app_id: UUID, run_id: UUID) -> None:
        advisory_key: int | None = None
        try:
            async with cls._session_factory() as db:
                monitor = cls(db)
                lock_acquired, advisory_key = await monitor._try_acquire_advisory_lock(run_id=run_id)
                if not lock_acquired:
                    logger.info("CODING_AGENT_MONITOR advisory_lock_not_acquired run_id=%s app_id=%s", run_id, app_id)
                    cls._trace("monitor.lock_not_acquired", run_id=str(run_id), app_id=str(app_id))
                    runtime = PublishedAppCodingAgentRuntimeService(db)
                    follower_timeout_raw = (os.getenv("APPS_CODING_AGENT_MONITOR_FOLLOWER_TIMEOUT_SECONDS") or "").strip()
                    try:
                        follower_timeout_seconds = float(follower_timeout_raw) if follower_timeout_raw else 300.0
                    except Exception:
                        follower_timeout_seconds = 300.0
                    follower_timeout_seconds = max(10.0, follower_timeout_seconds)
                    follower_poll_seconds = cls._monitor_poll_interval_seconds(
                        inactivity_timeout_seconds=follower_timeout_seconds
                    )
                    follower_deadline = time.monotonic() + follower_timeout_seconds
                    while time.monotonic() < follower_deadline:
                        result = await db.execute(
                            select(AgentRun)
                            .where(AgentRun.id == run_id)
                            .execution_options(populate_existing=True)
                        )
                        follower_run = result.scalar_one_or_none()
                        if follower_run is None:
                            break
                        follower_status = (
                            follower_run.status.value
                            if hasattr(follower_run.status, "value")
                            else str(follower_run.status)
                        )
                        if follower_status in _TERMINAL_RUN_STATUSES:
                            cls._trace(
                                "monitor.follower_terminal_observed",
                                run_id=str(run_id),
                                app_id=str(app_id),
                                status=follower_status,
                            )
                            diagnostics: list[dict[str, Any]] = []
                            if follower_status == RunStatus.failed.value:
                                diagnostics = [{"message": follower_run.error_message or "run failed"}]
                            await cls._emit_to_subscribers(
                                run_id=run_id,
                                payload=cls._envelope(
                                    event=cls._terminal_event_for_status(follower_status),
                                    run_id=run_id,
                                    app_id=app_id,
                                    stage="run",
                                    payload=runtime.serialize_run(follower_run),
                                    diagnostics=diagnostics,
                                ),
                            )
                            break
                        await asyncio.sleep(follower_poll_seconds)
                    cls._trace(
                        "monitor.follower_exit",
                        run_id=str(run_id),
                        app_id=str(app_id),
                    )
                    return

                runtime = PublishedAppCodingAgentRuntimeService(db)
                cls._trace("monitor.lock_acquired", run_id=str(run_id), app_id=str(app_id))
                dialect_name = getattr(getattr(db.get_bind(), "dialect", None), "name", "")
                use_external_probe = str(dialect_name or "").strip().lower() != "sqlite"

                app = await db.get(PublishedApp, app_id)
                if app is None:
                    return
                run = await runtime.get_run_for_app(app_id=app_id, run_id=run_id)

                terminal_emitted = False
                inactivity_timeout_seconds = cls._monitor_inactivity_timeout_seconds()
                poll_interval_seconds = cls._monitor_poll_interval_seconds(
                    inactivity_timeout_seconds=inactivity_timeout_seconds
                )
                status_probe_interval_seconds = cls._monitor_status_probe_interval_seconds()
                last_event_at = time.monotonic()
                run_event_stream = runtime.stream_run_events(app=app, run=run)
                run_event_iterator = run_event_stream.__aiter__()
                pending_next: asyncio.Task | None = None
                monitor_started_at = time.monotonic()
                max_runtime_seconds = cls._monitor_max_runtime_seconds()
                last_progress_at = monitor_started_at
                last_status_probe_at = 0.0
                last_plan_summary = ""

                async def _load_run_fresh() -> AgentRun | None:
                    if use_external_probe:
                        async with cls._session_factory() as probe_db:
                            result = await probe_db.execute(
                                select(AgentRun)
                                .where(AgentRun.id == run_id)
                                .execution_options(populate_existing=True)
                            )
                            return result.scalar_one_or_none()
                    result = await db.execute(
                        select(AgentRun)
                        .where(AgentRun.id == run_id)
                        .execution_options(populate_existing=True)
                    )
                    return result.scalar_one_or_none()

                async def _read_run_status() -> str | None:
                    if use_external_probe:
                        async with cls._session_factory() as probe_db:
                            result = await probe_db.execute(select(AgentRun.status).where(AgentRun.id == run_id))
                            refreshed_status = result.scalar_one_or_none()
                            if refreshed_status is None:
                                return None
                            return (
                                refreshed_status.value
                                if hasattr(refreshed_status, "value")
                                else str(refreshed_status)
                            )
                    result = await db.execute(select(AgentRun.status).where(AgentRun.id == run_id))
                    refreshed_status = result.scalar_one_or_none()
                    if refreshed_status is None:
                        return None
                    return (
                        refreshed_status.value
                        if hasattr(refreshed_status, "value")
                        else str(refreshed_status)
                    )

                async def _terminalize_stalled_run(*, message: str, log_reason: str) -> bool:
                    if use_external_probe:
                        async with cls._session_factory() as timeout_db:
                            timeout_run = await timeout_db.get(AgentRun, run_id)
                            if timeout_run is None:
                                return False
                            timeout_status = (
                                timeout_run.status.value
                                if hasattr(timeout_run.status, "value")
                                else str(timeout_run.status)
                            )
                            if timeout_status in _TERMINAL_RUN_STATUSES:
                                return False
                            timeout_run.status = RunStatus.failed
                            timeout_run.error_message = message
                            timeout_run.completed_at = cls._now()
                            timeout_runtime = PublishedAppCodingAgentRuntimeService(timeout_db)
                            await timeout_runtime._clear_preview_run_lock(
                                app_id=timeout_run.published_app_id,
                                actor_id=timeout_run.initiator_user_id or timeout_run.user_id,
                                run_id=timeout_run.id,
                            )
                            await timeout_db.commit()
                    else:
                        timeout_run = await db.get(AgentRun, run_id)
                        if timeout_run is None:
                            return False
                        timeout_status = (
                            timeout_run.status.value
                            if hasattr(timeout_run.status, "value")
                            else str(timeout_run.status)
                        )
                        if timeout_status in _TERMINAL_RUN_STATUSES:
                            return False
                        timeout_run.status = RunStatus.failed
                        timeout_run.error_message = message
                        timeout_run.completed_at = cls._now()
                        await runtime._clear_preview_run_lock(
                            app_id=timeout_run.published_app_id,
                            actor_id=timeout_run.initiator_user_id or timeout_run.user_id,
                            run_id=timeout_run.id,
                        )
                        await db.commit()
                    logger.error(
                        "CODING_AGENT_MONITOR %s run_id=%s app_id=%s message=%s",
                        log_reason,
                        run_id,
                        app_id,
                        message,
                    )
                    return True

                async def _emit_terminal_from_status(*, status: str) -> None:
                    nonlocal terminal_emitted
                    if terminal_emitted:
                        return
                    refreshed_for_terminal = await _load_run_fresh()
                    if refreshed_for_terminal is None:
                        return
                    diagnostics: list[dict[str, Any]] = []
                    if status == RunStatus.failed.value:
                        diagnostics = [{"message": refreshed_for_terminal.error_message or "run failed"}]
                    await cls._emit_to_subscribers(
                        run_id=run_id,
                        payload=cls._envelope(
                            event=cls._terminal_event_for_status(status),
                            run_id=run_id,
                            app_id=app_id,
                            stage="run",
                            payload=runtime.serialize_run(refreshed_for_terminal),
                            diagnostics=diagnostics,
                        ),
                    )
                    terminal_emitted = True
                    cls._trace(
                        "monitor.synthetic_terminal_from_status",
                        run_id=str(run_id),
                        app_id=str(app_id),
                        status=status,
                    )

                last_emitted_plan_summary = ""
                last_emitted_plan_at = 0.0

                def _is_progress_event(*, event_name: str, payload: dict[str, Any]) -> bool:
                    nonlocal last_plan_summary
                    if event_name == "plan.updated":
                        summary = str(payload.get("summary") or "").strip()
                        if summary and summary != last_plan_summary:
                            last_plan_summary = summary
                            return True
                        return False
                    return event_name in {
                        "assistant.delta",
                        "tool.started",
                        "tool.completed",
                        "tool.failed",
                        "revision.created",
                        "checkpoint.created",
                    }

                def _should_emit_event_to_subscribers(*, event_name: str, payload: dict[str, Any]) -> bool:
                    nonlocal last_emitted_plan_summary, last_emitted_plan_at
                    if event_name != "plan.updated":
                        return True
                    summary = str(payload.get("summary") or "").strip()
                    if not summary:
                        return False
                    now = time.monotonic()
                    # Throttle duplicate plan updates that can flood the stream and
                    # delay/drown assistant deltas in the UI pipeline.
                    if summary == last_emitted_plan_summary and (now - last_emitted_plan_at) < 0.75:
                        return False
                    last_emitted_plan_summary = summary
                    last_emitted_plan_at = now
                    return True

                try:
                    while True:
                        now_monotonic = time.monotonic()
                        if (
                            last_status_probe_at <= 0.0
                            or (now_monotonic - last_status_probe_at) >= status_probe_interval_seconds
                        ):
                            refreshed_status = await _read_run_status()
                            last_status_probe_at = now_monotonic
                            if refreshed_status is None:
                                break
                            if refreshed_status in _TERMINAL_RUN_STATUSES:
                                await _emit_terminal_from_status(status=refreshed_status)
                                break
                        run_elapsed_seconds = max(0.0, now_monotonic - monitor_started_at)
                        if run_elapsed_seconds >= max_runtime_seconds:
                            terminalized = await _terminalize_stalled_run(
                                message=f"OpenCode monitor exceeded max runtime ({int(run_elapsed_seconds)}s)",
                                log_reason="max_runtime_timeout",
                            )
                            if terminalized:
                                cls._trace(
                                    "monitor.force_terminal.max_runtime",
                                    run_id=str(run_id),
                                    app_id=str(app_id),
                                    elapsed_seconds=int(run_elapsed_seconds),
                                )
                                break

                        idle_progress_seconds = max(0.0, now_monotonic - last_progress_at)
                        if idle_progress_seconds >= inactivity_timeout_seconds:
                            terminalized = await _terminalize_stalled_run(
                                message=(
                                    "OpenCode stream stalled before terminal event "
                                    f"(no progress for {int(idle_progress_seconds)}s)"
                                ),
                                log_reason="progress_inactivity_timeout",
                            )
                            if terminalized:
                                cls._trace(
                                    "monitor.force_terminal.no_progress",
                                    run_id=str(run_id),
                                    app_id=str(app_id),
                                    idle_seconds=int(idle_progress_seconds),
                                )
                                break

                        if pending_next is None:
                            pending_next = asyncio.create_task(run_event_iterator.__anext__())

                        done, _ = await asyncio.wait({pending_next}, timeout=poll_interval_seconds)
                        if not done:
                            now_monotonic = time.monotonic()
                            if (now_monotonic - last_status_probe_at) >= status_probe_interval_seconds:
                                refreshed_for_timeout_status = await _read_run_status()
                                last_status_probe_at = now_monotonic
                                if refreshed_for_timeout_status is None:
                                    break
                                if refreshed_for_timeout_status in _TERMINAL_RUN_STATUSES:
                                    await _emit_terminal_from_status(status=refreshed_for_timeout_status)
                                    break
                            idle_for_seconds = max(0.0, time.monotonic() - last_event_at)
                            if idle_for_seconds >= inactivity_timeout_seconds:
                                terminalized = await _terminalize_stalled_run(
                                    message=(
                                        "OpenCode stream stalled before terminal event "
                                        f"(idle for {int(idle_for_seconds)}s)"
                                    ),
                                    log_reason="read_poll_timeout",
                                )
                                if terminalized:
                                    cls._trace(
                                        "monitor.force_terminal.read_poll_timeout",
                                        run_id=str(run_id),
                                        app_id=str(app_id),
                                        idle_seconds=int(idle_for_seconds),
                                    )
                                    break
                            continue

                        try:
                            envelope = pending_next.result()
                        except StopAsyncIteration:
                            break
                        finally:
                            pending_next = None

                        last_event_at = time.monotonic()
                        payload = {
                            "event": str(envelope.get("event") or ""),
                            "run_id": str(run_id),
                            "app_id": str(app_id),
                            "ts": str(envelope.get("ts") or datetime.now(timezone.utc).isoformat()),
                            "stage": str(envelope.get("stage") or "run"),
                            "payload": dict(envelope.get("payload") or {}),
                            "diagnostics": list(envelope.get("diagnostics") or []),
                        }
                        if _should_emit_event_to_subscribers(
                            event_name=payload["event"],
                            payload=payload["payload"],
                        ):
                            await cls._emit_to_subscribers(run_id=run_id, payload=payload)
                        if _is_progress_event(event_name=payload["event"], payload=payload["payload"]):
                            last_progress_at = time.monotonic()
                        if payload["event"] in _TERMINAL_EVENTS:
                            terminal_emitted = True
                            cls._trace(
                                "monitor.terminal_event_seen",
                                run_id=str(run_id),
                                app_id=str(app_id),
                                run_event=payload["event"],
                            )
                            break
                finally:
                    if pending_next is not None:
                        pending_next.cancel()
                        with suppress(asyncio.CancelledError, StopAsyncIteration, Exception):
                            await pending_next
                    aclose = getattr(run_event_stream, "aclose", None)
                    if callable(aclose):
                        with suppress(Exception):
                            await aclose()

                refreshed_run = await _load_run_fresh()
                if refreshed_run is None:
                    return

                refreshed_status = refreshed_run.status.value if hasattr(refreshed_run.status, "value") else str(refreshed_run.status)
                if refreshed_status not in _TERMINAL_RUN_STATUSES:
                    await _terminalize_stalled_run(
                        message="OpenCode stream ended before terminal event",
                        log_reason="stream_ended_no_terminal",
                    )
                    refreshed_run = await _load_run_fresh()
                    if refreshed_run is None:
                        return
                    refreshed_status = refreshed_run.status.value if hasattr(refreshed_run.status, "value") else str(refreshed_run.status)

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
                    if refreshed_status == RunStatus.completed.value:
                        asyncio.create_task(
                            cls._finalize_completed_run_detached(app_id=app_id, run_id=run_id)
                        )

                    next_run = None
                    if use_external_probe:
                        async with cls._session_factory() as dispatch_db:
                            dispatch_queue_service = PublishedAppCodingQueueService(dispatch_db)
                            dispatch_terminal_run = await dispatch_db.get(AgentRun, run_id)
                            if dispatch_terminal_run is not None:
                                dispatch_terminal_status = (
                                    dispatch_terminal_run.status.value
                                    if hasattr(dispatch_terminal_run.status, "value")
                                    else str(dispatch_terminal_run.status)
                                )
                                if dispatch_terminal_status in _TERMINAL_RUN_STATUSES:
                                    next_run = await dispatch_queue_service.dispatch_next_for_terminal_run(
                                        terminal_run=dispatch_terminal_run
                                    )
                    else:
                        dispatch_queue_service = PublishedAppCodingQueueService(db)
                        dispatch_terminal_run = await db.get(AgentRun, run_id)
                        if dispatch_terminal_run is not None:
                            dispatch_terminal_status = (
                                dispatch_terminal_run.status.value
                                if hasattr(dispatch_terminal_run.status, "value")
                                else str(dispatch_terminal_run.status)
                            )
                            if dispatch_terminal_status in _TERMINAL_RUN_STATUSES:
                                next_run = await dispatch_queue_service.dispatch_next_for_terminal_run(
                                    terminal_run=dispatch_terminal_run
                                )
                    if next_run is not None:
                        cls._trace(
                            "monitor.queue_dispatched_next",
                            run_id=str(run_id),
                            app_id=str(app_id),
                            next_run_id=str(next_run.id),
                        )
                        asyncio.create_task(
                            cls.ensure_monitor_detached(app_id=app_id, run_id=next_run.id)
                        )
        except Exception as exc:
            logger.exception("CODING_AGENT_MONITOR runner_failed run_id=%s app_id=%s", run_id, app_id)
            cls._trace(
                "monitor.runner_failed",
                run_id=str(run_id),
                app_id=str(app_id),
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
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
                            cls._trace(
                                "monitor.fail_closed_terminalized",
                                run_id=str(run_id),
                                app_id=str(app_id),
                                status=RunStatus.failed.value,
                                error=str(exc),
                            )
            except Exception:
                logger.exception("CODING_AGENT_MONITOR fail_closed_terminalize_failed run_id=%s", run_id)
                cls._trace(
                    "monitor.fail_closed_terminalize_failed",
                    run_id=str(run_id),
                    app_id=str(app_id),
                    error=str(exc),
                )
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
                cls._trace("monitor.stopped", run_id=str(run_id), app_id=str(app_id))
