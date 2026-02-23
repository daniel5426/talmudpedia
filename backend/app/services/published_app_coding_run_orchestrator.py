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
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.engine import sessionmaker
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppCodingPromptQueue,
    PublishedAppCodingPromptQueueStatus,
    PublishedAppCodingRunEvent,
    PublishedAppRevision,
)
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_chat_history_service import PublishedAppCodingChatHistoryService
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeDisabled, PublishedAppDraftDevRuntimeService

logger = logging.getLogger(__name__)

_TERMINAL_RUN_STATUSES = {RunStatus.completed.value, RunStatus.failed.value, RunStatus.cancelled.value, RunStatus.paused.value}
_TERMINAL_EVENTS = {"run.completed", "run.failed", "run.cancelled", "run.paused"}


@dataclass
class _RunnerState:
    run_id: str
    owner_token: str
    task: asyncio.Task
    subscribers: set[asyncio.Queue] = field(default_factory=set)


class PublishedAppCodingRunOrchestrator:
    _runners: dict[str, _RunnerState] = {}
    _runners_lock = asyncio.Lock()
    _last_retention_run_at: datetime | None = None

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _json_safe(value: Any) -> Any:
        return jsonable_encoder(value)

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
    async def _with_new_session(cls) -> AsyncSession:
        return sessionmaker()

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

    async def enqueue_prompt(
        self,
        *,
        app_id: UUID,
        user_id: UUID,
        chat_session_id: UUID,
        payload: dict[str, Any],
    ) -> PublishedAppCodingPromptQueue:
        max_position_result = await self.db.execute(
            select(func.max(PublishedAppCodingPromptQueue.position)).where(
                PublishedAppCodingPromptQueue.chat_session_id == chat_session_id,
            )
        )
        max_position = int(max_position_result.scalar_one_or_none() or 0)
        item = PublishedAppCodingPromptQueue(
            published_app_id=app_id,
            user_id=user_id,
            chat_session_id=chat_session_id,
            position=max_position + 1,
            status=PublishedAppCodingPromptQueueStatus.queued,
            payload=dict(payload or {}),
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def list_queue_items(
        self,
        *,
        app_id: UUID,
        user_id: UUID,
        chat_session_id: UUID,
    ) -> list[PublishedAppCodingPromptQueue]:
        result = await self.db.execute(
            select(PublishedAppCodingPromptQueue)
            .where(
                PublishedAppCodingPromptQueue.published_app_id == app_id,
                PublishedAppCodingPromptQueue.user_id == user_id,
                PublishedAppCodingPromptQueue.chat_session_id == chat_session_id,
                PublishedAppCodingPromptQueue.status.in_(
                    [
                        PublishedAppCodingPromptQueueStatus.queued,
                        PublishedAppCodingPromptQueueStatus.running,
                    ]
                ),
            )
            .order_by(PublishedAppCodingPromptQueue.position.asc())
        )
        return list(result.scalars().all())

    async def remove_queue_item(
        self,
        *,
        app_id: UUID,
        user_id: UUID,
        chat_session_id: UUID,
        queue_item_id: UUID,
    ) -> bool:
        item = await self.db.get(PublishedAppCodingPromptQueue, queue_item_id)
        if item is None:
            return False
        if (
            item.published_app_id != app_id
            or item.user_id != user_id
            or item.chat_session_id != chat_session_id
        ):
            return False
        if item.status != PublishedAppCodingPromptQueueStatus.queued:
            return False
        item.status = PublishedAppCodingPromptQueueStatus.cancelled
        item.finished_at = self._now()
        await self.db.commit()
        return True

    @staticmethod
    def serialize_queue_item(item: PublishedAppCodingPromptQueue) -> dict[str, Any]:
        payload = dict(item.payload or {})
        return {
            "id": str(item.id),
            "chat_session_id": str(item.chat_session_id),
            "position": int(item.position or 0),
            "status": item.status.value if hasattr(item.status, "value") else str(item.status),
            "input": str(payload.get("input") or ""),
            "client_message_id": str(payload.get("client_message_id") or "").strip() or None,
            "created_at": item.created_at,
            "started_at": item.started_at,
            "finished_at": item.finished_at,
            "error": item.error,
        }

    async def get_active_run_for_chat_session(
        self,
        *,
        app_id: UUID,
        chat_session_id: UUID,
    ) -> AgentRun | None:
        # Keep query simple and portable: scan recent runs and match context chat_session_id.
        result = await self.db.execute(
            select(AgentRun)
            .where(
                AgentRun.published_app_id == app_id,
                AgentRun.surface == "published_app_coding_agent",
            )
            .order_by(AgentRun.created_at.desc())
            .limit(120)
        )
        runs = list(result.scalars().all())
        target_session_id = str(chat_session_id)
        for run in runs:
            status = run.status.value if hasattr(run.status, "value") else str(run.status)
            if status in _TERMINAL_RUN_STATUSES:
                continue
            input_params = run.input_params if isinstance(run.input_params, dict) else {}
            context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
            if str(context.get("chat_session_id") or "").strip() == target_session_id:
                return run
        return None

    async def count_queued_prompts(self, *, chat_session_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count(PublishedAppCodingPromptQueue.id)).where(
                PublishedAppCodingPromptQueue.chat_session_id == chat_session_id,
                PublishedAppCodingPromptQueue.status == PublishedAppCodingPromptQueueStatus.queued,
            )
        )
        return int(result.scalar_one() or 0)

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
            task = asyncio.create_task(self.__class__._runner_main(app_id=app_id, run_id=run_id, owner_token=owner_token))
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
                    diagnostics_body = [{"message": str(run.error_message or "run failed")}]
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
            try:
                await active_db.rollback()
            except Exception:
                pass

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
            async with sessionmaker() as detached_db:
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
            async with sessionmaker() as db:
                runtime = PublishedAppCodingAgentRuntimeService(db)
                app = await db.get(PublishedApp, app_id)
                run = await runtime.get_run_for_app(app_id=app_id, run_id=run_id)
                if app is None:
                    return

                next_seq = await cls._next_event_seq(db=db, run_id=run_id)

                async for envelope in runtime.stream_run_events(app=app, run=run):
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
                    while True:
                        payload["seq"] = proposed_seq
                        db.add(
                            PublishedAppCodingRunEvent(
                                run_id=run_id,
                                seq=proposed_seq,
                                event=event_name,
                                stage=event_stage,
                                payload_json=payload_body,
                                diagnostics_json=diagnostics_body,
                            )
                        )

                        run_row = await db.get(AgentRun, run_id)
                        if run_row is not None:
                            if event_name in _TERMINAL_EVENTS:
                                if event_name == "run.completed":
                                    run_row.status = RunStatus.completed
                                    run_row.error_message = None
                                elif event_name == "run.cancelled":
                                    run_row.status = RunStatus.cancelled
                                    run_row.error_message = None
                                elif event_name == "run.paused":
                                    run_row.status = RunStatus.paused
                                    run_row.error_message = None
                                else:
                                    failure_message = str(
                                        (diagnostics_body[0].get("message") if diagnostics_body else "")
                                        or payload_body.get("error")
                                        or run_row.error_message
                                        or "run failed"
                                    )
                                    run_row.status = RunStatus.failed
                                    run_row.error_message = failure_message
                                run_row.completed_at = run_row.completed_at or cls._now()
                                run_row.is_cancelling = False

                            if str(run_row.runner_owner_id or "") == owner_token:
                                run_row.runner_heartbeat_at = cls._now()
                                run_row.runner_lease_expires_at = cls._now() + timedelta(minutes=2)

                        try:
                            await db.commit()
                            break
                        except IntegrityError as exc:
                            await db.rollback()
                            if not cls._is_run_event_seq_conflict(exc):
                                raise
                            if event_name in _TERMINAL_EVENTS:
                                existing_terminal = await cls._latest_terminal_event_row(db=db, run_id=run_id)
                                if existing_terminal is not None:
                                    payload = cls._serialize_event_row(row=existing_terminal, run_id=run_id, app_id=app_id)
                                    break
                            proposed_seq = await cls._next_event_seq(db=db, run_id=run_id)

                    next_seq = max(int(payload.get("seq") or 0) + 1, proposed_seq + 1)
                    await cls._emit_to_subscribers(run_id=run_id, payload=payload)

                terminal_run = await db.get(AgentRun, run_id)
                if terminal_run is not None and terminal_run.status.value in _TERMINAL_RUN_STATUSES:
                    await cls._dispatch_next_queued_prompt_from_terminal_run(db=db, terminal_run=terminal_run)
        except Exception as exc:
            logger.exception("CODING_AGENT_REATTACH runner_failed run_id=%s app_id=%s error=%s", run_id, app_id, exc)
            await cls._fail_closed_terminalize_runner_error(
                app_id=app_id,
                run_id=run_id,
                error_message=str(exc),
            )
        finally:
            try:
                async with sessionmaker() as db:
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

    @classmethod
    async def _dispatch_next_queued_prompt_from_terminal_run(cls, *, db: AsyncSession, terminal_run: AgentRun) -> None:
        input_params = terminal_run.input_params if isinstance(terminal_run.input_params, dict) else {}
        context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
        raw_chat_session_id = str(context.get("chat_session_id") or "").strip()
        if not raw_chat_session_id:
            return
        try:
            chat_session_id = UUID(raw_chat_session_id)
        except Exception:
            return

        queue_result = await db.execute(
            select(PublishedAppCodingPromptQueue)
            .where(
                PublishedAppCodingPromptQueue.chat_session_id == chat_session_id,
                PublishedAppCodingPromptQueue.status == PublishedAppCodingPromptQueueStatus.queued,
            )
            .order_by(PublishedAppCodingPromptQueue.position.asc())
            .limit(1)
        )
        queue_item = queue_result.scalar_one_or_none()
        if queue_item is None:
            return

        queue_item.status = PublishedAppCodingPromptQueueStatus.running
        queue_item.started_at = cls._now()
        queue_item.error = None
        await db.commit()

        app = await db.get(PublishedApp, queue_item.published_app_id)
        if app is None:
            queue_item.status = PublishedAppCodingPromptQueueStatus.failed
            queue_item.error = "Published app not found for queued prompt"
            queue_item.finished_at = cls._now()
            await db.commit()
            return

        actor_id = queue_item.user_id
        current_revision_id = app.current_draft_revision_id or terminal_run.base_revision_id
        current_revision = await db.get(PublishedAppRevision, current_revision_id) if current_revision_id else None
        if current_revision is None:
            queue_item.status = PublishedAppCodingPromptQueueStatus.failed
            queue_item.error = "Draft revision unavailable for queued prompt"
            queue_item.finished_at = cls._now()
            await db.commit()
            return

        payload = dict(queue_item.payload or {})
        user_prompt = str(payload.get("input") or "").strip()
        if not user_prompt:
            queue_item.status = PublishedAppCodingPromptQueueStatus.failed
            queue_item.error = "Queued prompt input is empty"
            queue_item.finished_at = cls._now()
            await db.commit()
            return

        requested_model_id = None
        raw_model_id = str(payload.get("model_id") or "").strip()
        if raw_model_id:
            try:
                requested_model_id = UUID(raw_model_id)
            except Exception:
                requested_model_id = None

        runtime = PublishedAppCodingAgentRuntimeService(db)
        try:
            run = await runtime.create_run(
                app=app,
                base_revision=current_revision,
                actor_id=actor_id,
                user_prompt=user_prompt,
                messages=None,
                requested_model_id=requested_model_id,
                execution_engine=str(payload.get("engine") or "").strip() or None,
                chat_session_id=chat_session_id,
            )

            draft_runtime = PublishedAppDraftDevRuntimeService(db)
            try:
                draft_session = await draft_runtime.get_session(app_id=app.id, user_id=actor_id)
            except PublishedAppDraftDevRuntimeDisabled:
                draft_session = None
            if draft_session is not None:
                draft_session.active_coding_run_id = run.id
                draft_session.active_coding_run_locked_at = cls._now()
                client_message_id = str(payload.get("client_message_id") or "").strip() or None
                draft_session.active_coding_run_client_message_id = client_message_id

            history = PublishedAppCodingChatHistoryService(db)
            await history.persist_user_message(
                session_id=chat_session_id,
                run_id=run.id,
                content=user_prompt,
            )

            queue_item.status = PublishedAppCodingPromptQueueStatus.completed
            queue_item.finished_at = cls._now()
            queue_item.error = None
            await db.commit()

            asyncio.create_task(cls._ensure_runner_detached(app_id=app.id, run_id=run.id))
            logger.info(
                "CODING_AGENT_QUEUE_DISPATCH app_id=%s from_run_id=%s next_run_id=%s queue_item_id=%s",
                app.id,
                terminal_run.id,
                run.id,
                queue_item.id,
            )
        except Exception as exc:
            queue_item.status = PublishedAppCodingPromptQueueStatus.failed
            queue_item.error = str(exc)
            queue_item.finished_at = cls._now()
            await db.commit()
            logger.exception(
                "CODING_AGENT_QUEUE_DISPATCH_FAILED app_id=%s from_run_id=%s queue_item_id=%s error=%s",
                app.id,
                terminal_run.id,
                queue_item.id,
                exc,
            )

    @classmethod
    async def _ensure_runner_detached(cls, *, app_id: UUID, run_id: UUID) -> None:
        try:
            async with sessionmaker() as db:
                orchestrator = cls(db)
                await orchestrator.ensure_runner(app_id=app_id, run_id=run_id)
        except Exception:
            logger.exception("CODING_AGENT_REATTACH detached_ensure_runner_failed run_id=%s app_id=%s", run_id, app_id)
