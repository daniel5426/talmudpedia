from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator
from uuid import UUID, uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from app.db.postgres.engine import sessionmaker
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppCodingRunEvent,
)
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_run_orchestrator_queue import PublishedAppCodingRunOrchestratorQueueMixin

logger = logging.getLogger(__name__)

_TERMINAL_RUN_STATUSES = {RunStatus.completed.value, RunStatus.failed.value, RunStatus.cancelled.value, RunStatus.paused.value}
_TERMINAL_EVENTS = {"run.completed", "run.failed", "run.cancelled", "run.paused"}


@dataclass
class _RunnerState:
    run_id: str
    owner_token: str
    task: asyncio.Task
    subscribers: set[asyncio.Queue] = field(default_factory=set)


class PublishedAppCodingRunOrchestrator(PublishedAppCodingRunOrchestratorQueueMixin):
    _runners: dict[str, _RunnerState] = {}
    _runners_lock = asyncio.Lock()
    _last_retention_run_at: datetime | None = None
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
    def _json_safe(value: Any) -> Any:
        return jsonable_encoder(value)

    @staticmethod
    def _resolve_session_factory_bind(db: AsyncSession) -> Any | None:
        direct_bind = getattr(db, "bind", None)
        if isinstance(direct_bind, AsyncConnection):
            return direct_bind.engine
        if isinstance(direct_bind, AsyncEngine):
            return direct_bind

        # AsyncSession.get_bind() can return a sync Engine/Connection.
        # Detached async runners must only be bound to AsyncEngine/AsyncConnection.
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
    def _is_generic_failure_message(message: str | None) -> bool:
        normalized = str(message or "").strip().lower()
        return normalized in {"", "run failed", "runtime error", "error", "failed"}

    @classmethod
    def _resolve_failure_message(
        cls,
        *,
        diagnostics: list[dict[str, Any]] | None = None,
        payload: dict[str, Any] | None = None,
        run_error_message: str | None = None,
        fallback: str = "run failed",
    ) -> str:
        diagnostic_message = ""
        if isinstance(diagnostics, list) and diagnostics:
            first = diagnostics[0] if isinstance(diagnostics[0], dict) else {}
            diagnostic_message = str(first.get("message") or "").strip()
        payload_message = str((payload or {}).get("error") or "").strip()
        run_message = str(run_error_message or "").strip()
        fallback_message = str(fallback or "").strip()

        for candidate in (diagnostic_message, payload_message, run_message, fallback_message):
            if candidate and not cls._is_generic_failure_message(candidate):
                return candidate
        for candidate in (diagnostic_message, payload_message, run_message, fallback_message):
            if candidate:
                return candidate
        return "run failed"

    @staticmethod
    def _serialize_event_row(*, row: PublishedAppCodingRunEvent, run_id: UUID, app_id: UUID) -> dict[str, Any]:
        return {
            "event": str(row.event or ""),
            "run_id": str(run_id),
            "app_id": str(app_id),
            "seq": int(row.seq or 0),
            "ts": row.created_at.isoformat() if row.created_at else PublishedAppCodingRunOrchestrator._now().isoformat(),
            "stage": str(row.stage or "run"),
            "payload": dict(row.payload_json or {}),
            "diagnostics": list(row.diagnostics_json or []),
        }

    @staticmethod
    def _is_run_event_seq_conflict(exc: Exception) -> bool:
        if not isinstance(exc, IntegrityError):
            return False
        original = getattr(exc, "orig", None)
        diag = getattr(original, "diag", None)
        constraint_name = str(getattr(diag, "constraint_name", "") or "")
        if constraint_name == "uq_published_app_coding_run_events_run_seq":
            return True

        message = str(original or exc).lower()
        return (
            "published_app_coding_run_events" in message
            and "run_id" in message
            and "seq" in message
            and ("unique" in message or "duplicate key value" in message)
        )

    @staticmethod
    async def _next_event_seq(*, db: AsyncSession, run_id: UUID) -> int:
        result = await db.execute(
            select(func.max(PublishedAppCodingRunEvent.seq)).where(PublishedAppCodingRunEvent.run_id == run_id)
        )
        return int(result.scalar_one_or_none() or 0) + 1

    @staticmethod
    async def _latest_terminal_event_row(*, db: AsyncSession, run_id: UUID) -> PublishedAppCodingRunEvent | None:
        result = await db.execute(
            select(PublishedAppCodingRunEvent)
            .where(
                PublishedAppCodingRunEvent.run_id == run_id,
                PublishedAppCodingRunEvent.event.in_(list(_TERMINAL_EVENTS)),
            )
            .order_by(PublishedAppCodingRunEvent.seq.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def _append_event_row_with_retry(
        cls,
        *,
        db: AsyncSession,
        run_id: UUID,
        event: str,
        stage: str,
        payload_json: dict[str, Any],
        diagnostics_json: list[dict[str, Any]],
        preferred_seq: int | None = None,
        minimum_seq: int = 1,
        reuse_terminal_event: bool = False,
        max_attempts: int = 8,
    ) -> PublishedAppCodingRunEvent:
        min_seq = max(1, int(minimum_seq or 1))
        if reuse_terminal_event and event in _TERMINAL_EVENTS:
            existing = await cls._latest_terminal_event_row(db=db, run_id=run_id)
            if existing is not None and int(existing.seq or 0) >= min_seq:
                return existing

        next_seq = int(preferred_seq or 0)
        if next_seq < min_seq:
            next_seq = max(min_seq, await cls._next_event_seq(db=db, run_id=run_id))

        attempts = max(1, int(max_attempts))
        for _ in range(attempts):
            row = PublishedAppCodingRunEvent(
                run_id=run_id,
                seq=next_seq,
                event=event,
                stage=stage,
                payload_json=payload_json,
                diagnostics_json=diagnostics_json,
            )
            db.add(row)
            try:
                await db.commit()
                await db.refresh(row)
                return row
            except IntegrityError as exc:
                await db.rollback()
                if not cls._is_run_event_seq_conflict(exc):
                    raise
                if reuse_terminal_event and event in _TERMINAL_EVENTS:
                    existing = await cls._latest_terminal_event_row(db=db, run_id=run_id)
                    if existing is not None and int(existing.seq or 0) >= min_seq:
                        return existing
                next_seq = max(min_seq, await cls._next_event_seq(db=db, run_id=run_id))

        raise RuntimeError(f"Unable to append coding run event after {attempts} attempts for run {run_id}")

    @classmethod
    async def _reconcile_run_from_terminal_event(
        cls,
        *,
        db: AsyncSession,
        run_id: UUID,
        event_name: str,
        payload_json: dict[str, Any] | None = None,
        diagnostics_json: list[dict[str, Any]] | None = None,
        owner_token: str | None = None,
    ) -> AgentRun | None:
        run = await db.get(AgentRun, run_id)
        if run is None:
            return None

        normalized_event = str(event_name or "").strip().lower()
        if normalized_event not in _TERMINAL_EVENTS:
            return run

        payload = dict(payload_json or {})
        diagnostics = list(diagnostics_json or [])
        if normalized_event == "run.completed":
            run.status = RunStatus.completed
            run.error_message = None
        elif normalized_event == "run.cancelled":
            run.status = RunStatus.cancelled
            run.error_message = None
        elif normalized_event == "run.paused":
            run.status = RunStatus.paused
            run.error_message = None
        else:
            run.status = RunStatus.failed
            run.error_message = cls._resolve_failure_message(
                diagnostics=diagnostics,
                payload=payload,
                run_error_message=run.error_message,
                fallback="run failed",
            )
        run.completed_at = run.completed_at or cls._now()
        run.is_cancelling = False

        if owner_token and str(run.runner_owner_id or "") == owner_token:
            run.runner_heartbeat_at = cls._now()
            run.runner_lease_expires_at = cls._now() + timedelta(minutes=2)

        runtime = PublishedAppCodingAgentRuntimeService(db)
        await runtime._clear_preview_run_lock(
            app_id=run.published_app_id,
            actor_id=run.initiator_user_id or run.user_id,
            run_id=run.id,
        )
        await db.commit()
        await db.refresh(run)
        return run

    async def get_next_replay_seq(self, *, run_id: UUID) -> int:
        result = await self.db.execute(
            select(func.max(PublishedAppCodingRunEvent.seq)).where(PublishedAppCodingRunEvent.run_id == run_id)
        )
        max_seq = result.scalar_one_or_none()
        return int(max_seq or 0) + 1

    async def list_run_events(self, *, run_id: UUID, app_id: UUID, from_seq: int = 1) -> list[dict[str, Any]]:
        normalized_from_seq = max(1, int(from_seq or 1))
        result = await self.db.execute(
            select(PublishedAppCodingRunEvent)
            .where(
                PublishedAppCodingRunEvent.run_id == run_id,
                PublishedAppCodingRunEvent.seq >= normalized_from_seq,
            )
            .order_by(PublishedAppCodingRunEvent.seq.asc())
        )
        rows = list(result.scalars().all())
        return [self._serialize_event_row(row=row, run_id=run_id, app_id=app_id) for row in rows]

    async def purge_old_events(self, *, retention_hours: int = 24) -> None:
        now = self._now()
        last_run = self.__class__._last_retention_run_at
        if last_run is not None and (now - last_run) < timedelta(minutes=5):
            return
        cutoff = now - timedelta(hours=max(1, retention_hours))
        await self.db.execute(
            PublishedAppCodingRunEvent.__table__.delete().where(PublishedAppCodingRunEvent.created_at < cutoff)
        )
        await self.db.commit()
        self.__class__._last_retention_run_at = now

    async def ensure_runner(self, *, app_id: UUID, run_id: UUID) -> _RunnerState | None:
        run = await self.db.get(AgentRun, run_id)
        if run is None:
            return None
        status = run.status.value if hasattr(run.status, "value") else str(run.status)
        if status in _TERMINAL_RUN_STATUSES:
            return None

        run_key = str(run_id)
        async with self.__class__._runners_lock:
            existing = self.__class__._runners.get(run_key)
            if existing is not None and not existing.task.done():
                return existing

            owner_token = str(uuid4())
            task = asyncio.create_task(
                self.__class__._runner_main(
                    app_id=app_id,
                    run_id=run_id,
                    owner_token=owner_token,
                )
            )
            state = _RunnerState(run_id=run_key, owner_token=owner_token, task=task)
            self.__class__._runners[run_key] = state

        run.runner_owner_id = owner_token
        run.runner_heartbeat_at = self._now()
        run.runner_lease_expires_at = self._now() + timedelta(minutes=2)
        await self.db.commit()

        logger.info("CODING_AGENT_REATTACH ensure_runner_started run_id=%s app_id=%s owner=%s", run_id, app_id, owner_token)
        return state

    async def stream_events(
        self,
        *,
        app_id: UUID,
        run_id: UUID,
        from_seq: int = 1,
        replay: bool = True,
    ) -> AsyncGenerator[dict[str, Any], None]:
        normalized_from_seq = max(1, int(from_seq or 1))
        run = await self.db.get(AgentRun, run_id)
        if run is None:
            return

        state = await self.ensure_runner(app_id=app_id, run_id=run_id)
        queue: asyncio.Queue | None = None
        replay_last_seq = normalized_from_seq - 1
        replay_saw_terminal_event = False

        if state is not None:
            queue = asyncio.Queue(maxsize=500)
            async with self.__class__._runners_lock:
                current = self.__class__._runners.get(str(run_id))
                if current is not None:
                    current.subscribers.add(queue)

        try:
            if replay:
                logger.info(
                    "CODING_AGENT_REPLAY run_id=%s app_id=%s from_seq=%s replay=%s",
                    run_id,
                    app_id,
                    normalized_from_seq,
                    replay,
                )
                existing = await self.list_run_events(run_id=run_id, app_id=app_id, from_seq=normalized_from_seq)
                for item in existing:
                    replay_last_seq = max(replay_last_seq, int(item.get("seq") or 0))
                    if str(item.get("event") or "") in _TERMINAL_EVENTS:
                        replay_saw_terminal_event = True
                    yield item

            run = await self.db.get(AgentRun, run_id)
            status = run.status.value if hasattr(run.status, "value") else str(run.status) if run is not None else "failed"
            if status in _TERMINAL_RUN_STATUSES:
                if replay_saw_terminal_event or run is None:
                    return

                terminal_event = self._terminal_event_for_status(status)
                runtime = PublishedAppCodingAgentRuntimeService(self.db)
                payload_body = self._json_safe(runtime.serialize_run(run))
                if not isinstance(payload_body, dict):
                    payload_body = {"value": payload_body}
                diagnostics_body: list[dict[str, Any]] = []
                if status == RunStatus.failed.value:
                    diagnostics_body = [
                        {
                            "message": self._resolve_failure_message(
                                diagnostics=[],
                                payload=payload_body if isinstance(payload_body, dict) else {},
                                run_error_message=run.error_message,
                                fallback="run failed",
                            )
                        }
                    ]
                diagnostics_body = self._json_safe(diagnostics_body)
                if not isinstance(diagnostics_body, list):
                    diagnostics_body = [diagnostics_body]

                latest_terminal = await self.__class__._latest_terminal_event_row(db=self.db, run_id=run_id)
                if latest_terminal is not None and int(latest_terminal.seq or 0) >= normalized_from_seq:
                    terminal_row = latest_terminal
                else:
                    preferred_seq = int(latest_terminal.seq or 0) + 1 if latest_terminal is not None else normalized_from_seq
                    preferred_seq = max(preferred_seq, replay_last_seq + 1, normalized_from_seq)
                    terminal_row = await self.__class__._append_event_row_with_retry(
                        db=self.db,
                        run_id=run_id,
                        event=terminal_event,
                        stage="run",
                        payload_json=payload_body,
                        diagnostics_json=diagnostics_body,
                        preferred_seq=preferred_seq,
                        minimum_seq=normalized_from_seq,
                        reuse_terminal_event=True,
                    )

                await self.__class__._reconcile_run_from_terminal_event(
                    db=self.db,
                    run_id=run_id,
                    event_name=str(terminal_row.event or terminal_event),
                    payload_json=dict(terminal_row.payload_json or {}),
                    diagnostics_json=list(terminal_row.diagnostics_json or []),
                )
                yield self._serialize_event_row(row=terminal_row, run_id=run_id, app_id=app_id)
                return

            if queue is None:
                return

            while True:
                payload = await queue.get()
                if payload is None:
                    break
                seq = int(payload.get("seq") or 0)
                if seq <= replay_last_seq:
                    continue
                yield payload
                if str(payload.get("event") or "") in _TERMINAL_EVENTS:
                    logger.info(
                        "CODING_AGENT_REPLAY run_id=%s app_id=%s terminal_event=%s seq=%s",
                        run_id,
                        app_id,
                        str(payload.get("event") or ""),
                        seq,
                    )
                    break
        finally:
            if queue is not None:
                async with self.__class__._runners_lock:
                    current = self.__class__._runners.get(str(run_id))
                    if current is not None:
                        current.subscribers.discard(queue)

    @classmethod
    async def _emit_to_subscribers(cls, *, run_id: UUID, payload: dict[str, Any]) -> None:
        async with cls._runners_lock:
            state = cls._runners.get(str(run_id))
            subscribers = list(state.subscribers) if state is not None else []
        for queue in subscribers:
            try:
                queue.put_nowait(payload)
            except Exception:
                # Drop if subscriber is slow or closed.
                pass

    @classmethod
    async def _close_subscribers(cls, *, run_id: UUID) -> None:
        async with cls._runners_lock:
            state = cls._runners.get(str(run_id))
            subscribers = list(state.subscribers) if state is not None else []
            if state is not None:
                state.subscribers.clear()
        for queue in subscribers:
            try:
                queue.put_nowait(None)
            except Exception:
                pass

    @classmethod
    async def _fail_closed_terminalize_runner_error(
        cls,
        *,
        app_id: UUID,
        run_id: UUID,
        error_message: str,
    ) -> None:
        async def _terminalize_with_db(active_db: AsyncSession) -> None:
            runtime = PublishedAppCodingAgentRuntimeService(active_db)
            run = await active_db.get(AgentRun, run_id)
            if run is None:
                return

            status = run.status.value if hasattr(run.status, "value") else str(run.status)
            if status not in _TERMINAL_RUN_STATUSES:
                run.status = RunStatus.failed
                run.error_message = error_message
                run.completed_at = cls._now()

            await runtime._clear_preview_run_lock(
                app_id=run.published_app_id,
                actor_id=run.initiator_user_id or run.user_id,
                run_id=run.id,
            )

            payload_body = cls._json_safe(runtime.serialize_run(run))
            if not isinstance(payload_body, dict):
                payload_body = {"value": payload_body}
            diagnostics_body = cls._json_safe([{"message": error_message}])
            if not isinstance(diagnostics_body, list):
                diagnostics_body = [diagnostics_body]
            terminal_row = await cls._append_event_row_with_retry(
                db=active_db,
                run_id=run_id,
                event="run.failed",
                stage="run",
                payload_json=payload_body,
                diagnostics_json=diagnostics_body,
                reuse_terminal_event=True,
            )
            emitted_payload = cls._serialize_event_row(row=terminal_row, run_id=run_id, app_id=app_id)
            await cls._emit_to_subscribers(run_id=run_id, payload=emitted_payload)

            status = run.status.value if hasattr(run.status, "value") else str(run.status)
            if status in _TERMINAL_RUN_STATUSES:
                await cls._dispatch_next_queued_prompt_from_terminal_run(db=active_db, terminal_run=run)

        try:
            async with cls._session_factory() as detached_db:
                await _terminalize_with_db(detached_db)
        except Exception:
            logger.exception(
                "CODING_AGENT_REATTACH fail_closed_terminalize_failed run_id=%s app_id=%s",
                run_id,
                app_id,
            )

    @classmethod
    async def _runner_main(cls, *, app_id: UUID, run_id: UUID, owner_token: str) -> None:
        try:
            async with cls._session_factory() as runtime_db, cls._session_factory() as event_db:
                runtime = PublishedAppCodingAgentRuntimeService(runtime_db)
                app = await runtime_db.get(PublishedApp, app_id)
                run = await runtime.get_run_for_app(app_id=app_id, run_id=run_id)
                if app is None:
                    return

                next_seq = await cls._next_event_seq(db=event_db, run_id=run_id)
                terminal_seen = False

                async for envelope in runtime.stream_run_events(app=app, run=run):
                    if terminal_seen:
                        continue
                    payload = dict(envelope or {})
                    event_name = str(payload.get("event") or "")
                    event_stage = str(payload.get("stage") or "run")
                    payload_body = cls._json_safe(payload.get("payload") or {})
                    if not isinstance(payload_body, dict):
                        payload_body = {"value": payload_body}
                    diagnostics_body = cls._json_safe(payload.get("diagnostics") or [])
                    if not isinstance(diagnostics_body, list):
                        diagnostics_body = [diagnostics_body]

                    proposed_seq = max(1, int(next_seq or 1))
                    row = await cls._append_event_row_with_retry(
                        db=event_db,
                        run_id=run_id,
                        event=event_name,
                        stage=event_stage,
                        payload_json=payload_body,
                        diagnostics_json=diagnostics_body,
                        preferred_seq=proposed_seq,
                        minimum_seq=next_seq,
                        reuse_terminal_event=event_name in _TERMINAL_EVENTS,
                    )
                    persisted_seq = int(row.seq or proposed_seq)
                    payload["seq"] = persisted_seq
                    event_name = str(row.event or event_name)
                    payload_body = dict(row.payload_json or payload_body)
                    diagnostics_body = list(row.diagnostics_json or diagnostics_body)

                    if event_name in _TERMINAL_EVENTS:
                        await cls._reconcile_run_from_terminal_event(
                            db=event_db,
                            run_id=run_id,
                            event_name=event_name,
                            payload_json=payload_body if isinstance(payload_body, dict) else {},
                            diagnostics_json=diagnostics_body if isinstance(diagnostics_body, list) else [],
                            owner_token=owner_token,
                        )
                        terminal_seen = True
                    else:
                        run_row = await event_db.get(AgentRun, run_id)
                        if run_row is not None and str(run_row.runner_owner_id or "") == owner_token:
                            now = cls._now()
                            heartbeat_at = run_row.runner_heartbeat_at
                            heartbeat_age_s = (
                                (now - heartbeat_at).total_seconds() if heartbeat_at is not None else 9999.0
                            )
                            if heartbeat_age_s >= 10.0:
                                run_row.runner_heartbeat_at = now
                                run_row.runner_lease_expires_at = now + timedelta(minutes=2)
                                await event_db.commit()
                    next_seq = max(int(payload.get("seq") or 0) + 1, persisted_seq + 1)
                    await cls._emit_to_subscribers(run_id=run_id, payload=payload)

                terminal_run = await event_db.get(AgentRun, run_id)
                terminal_status = terminal_run.status.value if terminal_run is not None else ""
                if terminal_run is not None and terminal_status not in _TERMINAL_RUN_STATUSES:
                    latest_terminal = await cls._latest_terminal_event_row(db=event_db, run_id=run_id)
                    if latest_terminal is not None:
                        terminal_run = await cls._reconcile_run_from_terminal_event(
                            db=event_db,
                            run_id=run_id,
                            event_name=str(latest_terminal.event or ""),
                            payload_json=dict(latest_terminal.payload_json or {}),
                            diagnostics_json=list(latest_terminal.diagnostics_json or []),
                            owner_token=owner_token,
                        )
                        terminal_status = terminal_run.status.value if terminal_run is not None else ""

                if terminal_run is not None and terminal_status in _TERMINAL_RUN_STATUSES:
                    await cls._dispatch_next_queued_prompt_from_terminal_run(db=event_db, terminal_run=terminal_run)
        except Exception as exc:
            logger.exception("CODING_AGENT_REATTACH runner_failed run_id=%s app_id=%s error=%s", run_id, app_id, exc)
            await cls._fail_closed_terminalize_runner_error(
                app_id=app_id,
                run_id=run_id,
                error_message=str(exc),
            )
        finally:
            try:
                async with cls._session_factory() as db:
                    run = await db.get(AgentRun, run_id)
                    if run is not None and str(run.runner_owner_id or "") == owner_token:
                        run.runner_owner_id = None
                        run.runner_lease_expires_at = None
                        run.runner_heartbeat_at = cls._now()
                        await db.commit()
            except Exception:
                pass

            await cls._close_subscribers(run_id=run_id)
            async with cls._runners_lock:
                state = cls._runners.get(str(run_id))
                if state is not None and state.owner_token == owner_token:
                    cls._runners.pop(str(run_id), None)
