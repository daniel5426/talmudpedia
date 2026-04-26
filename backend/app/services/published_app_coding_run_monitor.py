from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import json
import os
import time
from typing import Any, AsyncGenerator
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from app.db.postgres.engine import sessionmaker
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppRevision
from app.api.routers.published_apps_admin_files import _filter_builder_snapshot_files
from app.services.apps_builder_trace import apps_builder_trace
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService
from app.services.published_app_draft_revision_materializer import (
    PublishedAppDraftRevisionMaterializerError,
    PublishedAppDraftRevisionMaterializerService,
)
from app.services.published_app_live_preview import build_canonical_workspace_fingerprint
from app.services.published_app_templates import TemplateRuntimeContext
from app.services.published_app_coding_run_monitor_config import (
    monitor_force_terminal_on_inactivity,
    monitor_force_terminal_on_stream_end_without_terminal,
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
    next_seq: int = 1


class PublishedAppCodingRunMonitor:
    _monitors: dict[str, _MonitorState] = {}
    _monitors_lock = asyncio.Lock()
    _session_factory = sessionmaker
    _trace = staticmethod(monitor_trace)
    _monitor_inactivity_timeout_seconds = staticmethod(monitor_inactivity_timeout_seconds)
    _monitor_poll_interval_seconds = staticmethod(monitor_poll_interval_seconds)
    _monitor_max_runtime_seconds = staticmethod(monitor_max_runtime_seconds)
    _monitor_status_probe_interval_seconds = staticmethod(monitor_status_probe_interval_seconds)
    _monitor_force_terminal_on_inactivity = staticmethod(monitor_force_terminal_on_inactivity)
    _monitor_force_terminal_on_stream_end_without_terminal = staticmethod(
        monitor_force_terminal_on_stream_end_without_terminal
    )

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

    async def _try_acquire_advisory_lock(self, *, run_id: UUID) -> tuple[bool, int | None]:
        dialect_name = getattr(getattr(self.db.get_bind(), "dialect", None), "name", "")
        if str(dialect_name or "").strip().lower() != "postgresql":
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
            await self.db.commit()
        except Exception:
            logger.exception("CODING_AGENT_MONITOR advisory_unlock_failed key=%s", advisory_key)

    @staticmethod
    def _finalization_state(run: AgentRun) -> dict[str, Any]:
        payload = run.output_result if isinstance(run.output_result, dict) else {}
        state = payload.get("draft_revision_finalization")
        return dict(state) if isinstance(state, dict) else {}

    @staticmethod
    def _set_finalization_state(run: AgentRun, state: dict[str, Any] | None) -> None:
        payload = dict(run.output_result) if isinstance(run.output_result, dict) else {}
        if state:
            payload["draft_revision_finalization"] = dict(state)
        else:
            payload.pop("draft_revision_finalization", None)
        run.output_result = payload

    @staticmethod
    def _finalization_attempt_id(*, run_id: UUID) -> str:
        return f"{run_id}:{datetime.now(timezone.utc).isoformat()}"

    @staticmethod
    def _finalization_claim_timeout_seconds() -> float:
        raw = (os.getenv("APPS_DRAFT_REVISION_FINALIZATION_CLAIM_TIMEOUT_SECONDS") or "").strip()
        try:
            value = float(raw) if raw else 900.0
        except Exception:
            value = 900.0
        return max(30.0, value)

    @classmethod
    def _is_stale_finalization_claim(cls, state: dict[str, Any]) -> bool:
        claimed_at = str(state.get("claimed_at") or "").strip()
        if not claimed_at:
            return True
        try:
            claimed = datetime.fromisoformat(claimed_at)
        except Exception:
            return True
        age = (cls._now() - claimed).total_seconds()
        return age >= cls._finalization_claim_timeout_seconds()

    @classmethod
    async def _reconcile_live_workspace_metadata(
        cls,
        *,
        db: AsyncSession,
        run: AgentRun,
        app: PublishedApp,
        actor_id: UUID | None,
        source_revision_id: UUID | None,
        entry_file: str,
    ) -> dict[str, Any] | None:
        if actor_id is None:
            apps_builder_trace(
                "monitor.finalize.workspace_reconcile_skipped",
                domain="coding_agent.finalizer",
                run_id=str(run.id),
                app_id=str(app.id),
                reason="missing_actor_id",
            )
            return None
        input_params = run.input_params if isinstance(run.input_params, dict) else {}
        context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
        sandbox_id = str(context.get("preview_sandbox_id") or "").strip()
        if not sandbox_id:
            apps_builder_trace(
                "monitor.finalize.workspace_reconcile_skipped",
                domain="coding_agent.finalizer",
                run_id=str(run.id),
                app_id=str(app.id),
                reason="missing_sandbox_id",
            )
            return None
        runtime_service = PublishedAppDraftDevRuntimeService(db)
        apps_builder_trace(
            "monitor.finalize.workspace_reconcile_begin",
            domain="coding_agent.finalizer",
            run_id=str(run.id),
            app_id=str(app.id),
            sandbox_id=sandbox_id,
            source_revision_id=str(source_revision_id or "") or None,
        )
        try:
            payload = await runtime_service.client.snapshot_files(sandbox_id=sandbox_id)
            raw_files = payload.get("files")
            if not isinstance(raw_files, dict):
                apps_builder_trace(
                    "monitor.finalize.workspace_reconcile_skipped",
                    domain="coding_agent.finalizer",
                    run_id=str(run.id),
                    app_id=str(app.id),
                    reason="snapshot_missing_files",
                )
                return None
            files = _filter_builder_snapshot_files(raw_files)
            revision_token = str(payload.get("revision_token") or "").strip() or None
            workspace_fingerprint = build_canonical_workspace_fingerprint(
                entry_file=entry_file,
                files=files,
                runtime_context=TemplateRuntimeContext(
                    app_id=str(app.id),
                    app_public_id=str(app.public_id or ""),
                    agent_id=str(app.agent_id or ""),
                ),
            )
            await runtime_service.record_workspace_live_snapshot(
                app_id=app.id,
                revision_id=source_revision_id or app.current_draft_revision_id,
                entry_file=entry_file,
                files=files,
                revision_token=revision_token,
                workspace_fingerprint=workspace_fingerprint,
            )
            session = await runtime_service.get_session(app_id=app.id, user_id=actor_id)
            if session is not None:
                await runtime_service.record_live_workspace_revision_token(
                    session=session,
                    revision_token=revision_token,
                )
            try:
                await runtime_service.client.update_live_preview_context(
                    sandbox_id=sandbox_id,
                    workspace_fingerprint=workspace_fingerprint,
                )
            except Exception as exc:
                apps_builder_trace(
                    "monitor.finalize.workspace_reconcile_context_update_failed",
                    domain="coding_agent.finalizer",
                    run_id=str(run.id),
                    app_id=str(app.id),
                    sandbox_id=sandbox_id,
                    workspace_fingerprint=workspace_fingerprint,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
            apps_builder_trace(
                "monitor.finalize.workspace_reconcile_done",
                domain="coding_agent.finalizer",
                run_id=str(run.id),
                app_id=str(app.id),
                sandbox_id=sandbox_id,
                file_count=len(files),
                sample_paths=sorted(list(files.keys()))[:8],
                revision_token=revision_token,
                workspace_fingerprint=workspace_fingerprint,
            )
            return {
                "entry_file": entry_file,
                "files": files,
                "revision_token": revision_token,
                "workspace_fingerprint": workspace_fingerprint,
            }
        except Exception as exc:
            apps_builder_trace(
                "monitor.finalize.workspace_reconcile_failed",
                domain="coding_agent.finalizer",
                run_id=str(run.id),
                app_id=str(app.id),
                sandbox_id=sandbox_id,
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            return None

    @staticmethod
    def _template_runtime_context(*, app: PublishedApp) -> TemplateRuntimeContext:
        return TemplateRuntimeContext(
            app_id=str(app.id),
            app_public_id=str(app.public_id or ""),
            agent_id=str(app.agent_id or ""),
        )

    @classmethod
    def _revision_source_fingerprint(
        cls,
        *,
        revision: PublishedAppRevision | None,
        app: PublishedApp,
        entry_file: str,
    ) -> str:
        if revision is None:
            return ""
        dist_manifest = dict(revision.dist_manifest or {}) if isinstance(revision.dist_manifest, dict) else {}
        manifest_fingerprint = str(dist_manifest.get("source_fingerprint") or "").strip()
        if manifest_fingerprint:
            return manifest_fingerprint
        return build_canonical_workspace_fingerprint(
            entry_file=str(revision.entry_file or entry_file).strip() or entry_file,
            files=dict(revision.files or {}),
            runtime_context=cls._template_runtime_context(app=app),
        )

    @classmethod
    async def _claim_run_finalization(
        cls,
        *,
        db: AsyncSession,
        app_id: UUID,
        run_id: UUID,
    ) -> tuple[AgentRun | None, PublishedApp | None, UUID | None, str, UUID | None]:
        apps_builder_trace(
            "monitor.finalize.claim_begin",
            domain="coding_agent.finalizer",
            run_id=str(run_id),
            app_id=str(app_id),
        )
        run_result = await db.execute(
            select(AgentRun)
            .where(AgentRun.id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        run = run_result.scalar_one_or_none()
        app = await db.get(PublishedApp, app_id)
        if run is None or app is None:
            apps_builder_trace(
                "monitor.finalize.claim_missing_entities",
                domain="coding_agent.finalizer",
                run_id=str(run_id),
                app_id=str(app_id),
                run_found=bool(run is not None),
                app_found=bool(app is not None),
            )
            await db.commit()
            return None, None, None, "", None

        run_status = run.status.value if hasattr(run.status, "value") else str(run.status)
        apps_builder_trace(
            "monitor.finalize.claim_loaded",
            domain="coding_agent.finalizer",
            run_id=str(run_id),
            app_id=str(app_id),
            run_status=run_status,
            has_workspace_writes=bool(getattr(run, "has_workspace_writes", False)),
            result_revision_id=str(getattr(run, "result_revision_id", None) or "") or None,
            batch_finalized_at=run.batch_finalized_at.isoformat()
            if isinstance(run.batch_finalized_at, datetime)
            else None,
        )
        if getattr(run, "batch_finalized_at", None) is not None:
            apps_builder_trace(
                "monitor.finalize.claim_skipped",
                domain="coding_agent.finalizer",
                run_id=str(run_id),
                app_id=str(app_id),
                reason="already_batch_finalized",
            )
            await db.commit()
            return None, None, None, "", None
        if run_status != RunStatus.completed.value:
            apps_builder_trace(
                "monitor.finalize.claim_skipped",
                domain="coding_agent.finalizer",
                run_id=str(run_id),
                app_id=str(app_id),
                reason="run_not_completed",
                run_status=run_status,
            )
            await db.commit()
            return None, None, None, "", None
        state = cls._finalization_state(run)
        if state.get("status") == "in_progress" and not cls._is_stale_finalization_claim(state):
            apps_builder_trace(
                "monitor.finalize.claim_skipped",
                domain="coding_agent.finalizer",
                run_id=str(run_id),
                app_id=str(app_id),
                reason="already_claimed",
                claim_state=state,
            )
            await db.commit()
            return None, None, None, "", None

        source_revision_id = run.base_revision_id or app.current_draft_revision_id
        actor_id = run.initiator_user_id or run.user_id
        attempt_id = cls._finalization_attempt_id(run_id=run_id)
        cls._set_finalization_state(
            run,
            {
                "status": "in_progress",
                "attempt_id": attempt_id,
                "claimed_at": cls._now().isoformat(),
                "source_revision_id": str(source_revision_id or "") or None,
            },
        )
        apps_builder_trace(
            "monitor.finalize.claim_acquired",
            domain="coding_agent.finalizer",
            run_id=str(run_id),
            app_id=str(app_id),
            attempt_id=attempt_id,
            source_revision_id=str(source_revision_id or "") or None,
        )
        await db.commit()
        return run, app, source_revision_id, attempt_id, actor_id

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
        envelope = dict(payload)
        async with cls._monitors_lock:
            state = cls._monitors.get(run_key)
            if state is not None:
                seq_value = envelope.get("seq")
                try:
                    seq = int(seq_value)
                except Exception:
                    seq = 0
                if seq <= 0:
                    seq = int(state.next_seq or 1)
                envelope["seq"] = seq
                state.next_seq = max(int(state.next_seq or 1), seq + 1)
            subscribers = list(state.subscribers) if state is not None else []
        event_name = str(envelope.get("event") or "").strip()
        if event_name and event_name != "assistant.delta":
            cls._trace(
                "monitor.emit",
                run_id=run_key,
                run_event=event_name,
                subscriber_count=len(subscribers),
            )
            if event_name in _TERMINAL_EVENTS:
                run_payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
                cls._trace(
                    "monitor.terminal_payload",
                    run_id=run_key,
                    run_event=event_name,
                    status=run_payload.get("status"),
                    result_revision_id=run_payload.get("result_revision_id"),
                    error=run_payload.get("error"),
                )
        for queue in subscribers:
            try:
                queue.put_nowait(dict(envelope))
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
    async def _finalize_terminal_scope_detached(cls, *, app_id: UUID, run_id: UUID) -> None:
        try:
            apps_builder_trace(
                "monitor.revision_materialize_begin",
                domain="coding_agent.finalizer",
                run_id=str(run_id),
                app_id=str(app_id),
            )
            async with cls._session_factory() as db:
                apps_builder_trace(
                    "monitor.finalize.session_opened",
                    domain="coding_agent.finalizer",
                    run_id=str(run_id),
                    app_id=str(app_id),
                )
                claimed_run, claimed_app, source_revision_id, attempt_id, actor_id = await cls._claim_run_finalization(
                    db=db,
                    app_id=app_id,
                    run_id=run_id,
                )
                if claimed_run is None or claimed_app is None:
                    return

            entry_file = "src/main.tsx"
            async with cls._session_factory() as read_db:
                source_revision = (
                    await read_db.get(PublishedAppRevision, source_revision_id)
                    if source_revision_id is not None
                    else None
                )
                if source_revision is not None:
                    entry_file = str(source_revision.entry_file or entry_file)
                source_fingerprint = cls._revision_source_fingerprint(
                    revision=source_revision,
                    app=claimed_app,
                    entry_file=entry_file,
                )
                apps_builder_trace(
                    "monitor.finalize.source_revision_loaded",
                    domain="coding_agent.finalizer",
                    run_id=str(run_id),
                    app_id=str(app_id),
                    source_revision_id=str(source_revision_id or "") or None,
                    source_fingerprint=source_fingerprint or None,
                    source_entry_file=entry_file,
                    source_file_count=len(dict(source_revision.files or {})) if source_revision is not None else None,
                )
            cls._trace(
                "monitor.revision_materialize_begin",
                run_id=str(run_id),
                app_id=str(app_id),
                source_revision_id=str(source_revision_id or ""),
                has_workspace_writes=bool(getattr(claimed_run, "has_workspace_writes", False)),
            )
            result_revision_id: str | None = None
            async with cls._session_factory() as work_db:
                work_run = await work_db.get(AgentRun, run_id)
                work_app = await work_db.get(PublishedApp, app_id)
                if work_run is None or work_app is None:
                    apps_builder_trace(
                        "monitor.finalize.session_missing_entities",
                        domain="coding_agent.finalizer",
                        run_id=str(run_id),
                        app_id=str(app_id),
                        run_found=bool(work_run is not None),
                        app_found=bool(work_app is not None),
                    )
                    return
                materializer = PublishedAppDraftRevisionMaterializerService(work_db)
                apps_builder_trace(
                    "monitor.finalize.materializer_call_begin",
                    domain="coding_agent.finalizer",
                    run_id=str(run_id),
                    app_id=str(app_id),
                    source_revision_id=str(source_revision_id or "") or None,
                    entry_file=entry_file,
                    attempt_id=attempt_id,
                )
                snapshot = await cls._reconcile_live_workspace_metadata(
                    db=work_db,
                    run=work_run,
                    app=work_app,
                    actor_id=actor_id,
                    source_revision_id=source_revision_id,
                    entry_file=entry_file,
                )
                final_workspace_fingerprint = (
                    str(snapshot.get("workspace_fingerprint") or "").strip() if isinstance(snapshot, dict) else ""
                )
                has_workspace_writes = bool(
                    final_workspace_fingerprint
                    and (
                        not source_fingerprint
                        or final_workspace_fingerprint != source_fingerprint
                    )
                )
                work_run.has_workspace_writes = has_workspace_writes
                apps_builder_trace(
                    "monitor.finalize.workspace_diff_decided",
                    domain="coding_agent.finalizer",
                    run_id=str(run_id),
                    app_id=str(app_id),
                    source_revision_id=str(source_revision_id or "") or None,
                    source_fingerprint=source_fingerprint or None,
                    final_workspace_fingerprint=final_workspace_fingerprint or None,
                    has_workspace_writes=has_workspace_writes,
                    snapshot_available=bool(snapshot is not None),
                    snapshot_revision_token=(
                        str(snapshot.get("revision_token") or "").strip()
                        if isinstance(snapshot, dict)
                        else None
                    ) or None,
                    snapshot_file_count=len(dict(snapshot.get("files") or {})) if isinstance(snapshot, dict) else None,
                )
                result_revision = None
                if has_workspace_writes:
                    result_revision = await materializer.finalize_run_materialization(
                        app=work_app,
                        run=work_run,
                        entry_file=entry_file,
                        source_revision_id=source_revision_id,
                        created_by=actor_id,
                    )
                    result_revision_id = str(result_revision.id) if result_revision is not None else None
                else:
                    apps_builder_trace(
                        "monitor.finalize.materialization_skipped",
                        domain="coding_agent.finalizer",
                        run_id=str(run_id),
                        app_id=str(app_id),
                        reason="final_workspace_matches_source_revision",
                        source_revision_id=str(source_revision_id or "") or None,
                    )
                apps_builder_trace(
                    "monitor.finalize.materializer_call_done",
                    domain="coding_agent.finalizer",
                    run_id=str(run_id),
                    app_id=str(app_id),
                    result_revision_id=result_revision_id,
                    attempt_id=attempt_id,
                )
                if result_revision is not None and actor_id is not None:
                    apps_builder_trace(
                        "monitor.finalize.bind_session_skipped",
                        domain="coding_agent.finalizer",
                        run_id=str(run_id),
                        app_id=str(app_id),
                        actor_id=str(actor_id),
                        result_revision_id=str(result_revision.id),
                        reason="live_preview_session_remains_bound_to_workspace",
                    )
                await work_db.commit()

            async with cls._session_factory() as finalize_db:
                run_result = await finalize_db.execute(
                    select(AgentRun)
                    .where(AgentRun.id == run_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                finalize_run = run_result.scalar_one_or_none()
                if finalize_run is None:
                    return
                state = cls._finalization_state(finalize_run)
                if str(state.get("attempt_id") or "") != attempt_id:
                    apps_builder_trace(
                        "monitor.finalize.claim_skipped",
                        domain="coding_agent.finalizer",
                        run_id=str(run_id),
                        app_id=str(app_id),
                        reason="attempt_id_mismatch",
                        expected_attempt_id=attempt_id,
                        actual_attempt_id=str(state.get("attempt_id") or ""),
                    )
                    await finalize_db.commit()
                    return
                if result_revision_id:
                    finalize_run.result_revision_id = UUID(result_revision_id)
                finalize_run.batch_finalized_at = cls._now()
                cls._set_finalization_state(finalize_run, None)
                apps_builder_trace(
                    "monitor.finalize.db_commit_begin",
                    domain="coding_agent.finalizer",
                    run_id=str(run_id),
                    app_id=str(app_id),
                    result_revision_id=result_revision_id,
                    attempt_id=attempt_id,
                )
                await finalize_db.commit()
                apps_builder_trace(
                    "monitor.finalize.db_commit_done",
                    domain="coding_agent.finalizer",
                    run_id=str(run_id),
                    app_id=str(app_id),
                    result={"result_revision_id": result_revision_id},
                    attempt_id=attempt_id,
                )
            cls._trace(
                "monitor.revision_materialize_done",
                run_id=str(run_id),
                app_id=str(app_id),
                result={"result_revision_id": result_revision_id},
            )
            apps_builder_trace(
                "monitor.revision_materialize_done",
                domain="coding_agent.finalizer",
                run_id=str(run_id),
                app_id=str(app_id),
                result={"result_revision_id": result_revision_id},
                attempt_id=attempt_id,
            )
        except PublishedAppDraftRevisionMaterializerError as exc:
            async with cls._session_factory() as db:
                run_result = await db.execute(
                    select(AgentRun)
                    .where(AgentRun.id == run_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                failed_run = run_result.scalar_one_or_none()
                if failed_run is not None:
                    cls._set_finalization_state(
                        failed_run,
                        {
                            "status": "failed",
                            "failed_at": cls._now().isoformat(),
                            "error": str(exc),
                            "error_type": exc.__class__.__name__,
                        },
                    )
                    await db.commit()
            apps_builder_trace(
                "monitor.finalize.materializer_error",
                domain="coding_agent.finalizer",
                run_id=str(run_id),
                app_id=str(app_id),
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            logger.exception(
                "CODING_AGENT_MONITOR revision_materialize_failed run_id=%s app_id=%s error=%s",
                run_id,
                app_id,
                exc,
            )
        except Exception as exc:
            async with cls._session_factory() as db:
                run_result = await db.execute(
                    select(AgentRun)
                    .where(AgentRun.id == run_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                failed_run = run_result.scalar_one_or_none()
                if failed_run is not None:
                    cls._set_finalization_state(
                        failed_run,
                        {
                            "status": "failed",
                            "failed_at": cls._now().isoformat(),
                            "error": str(exc),
                            "error_type": exc.__class__.__name__,
                        },
                    )
                    await db.commit()
            apps_builder_trace(
                "monitor.finalize.exception",
                domain="coding_agent.finalizer",
                run_id=str(run_id),
                app_id=str(app_id),
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            logger.exception(
                "CODING_AGENT_MONITOR revision_materialize_failed run_id=%s app_id=%s",
                run_id,
                app_id,
            )
            cls._trace(
                "monitor.preview_finalize_failed",
                run_id=str(run_id),
                app_id=str(app_id),
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            apps_builder_trace(
                "monitor.preview_finalize_failed",
                domain="coding_agent.finalizer",
                run_id=str(run_id),
                app_id=str(app_id),
                error=str(exc),
                error_type=exc.__class__.__name__,
            )

    async def stream_events(
        self,
        *,
        app_id: UUID,
        run_id: UUID,
    ) -> AsyncGenerator[dict[str, Any], None]:
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
            asyncio.create_task(
                self.__class__._finalize_terminal_scope_detached(app_id=app_id, run_id=run_id)
            )
            payload = runtime.serialize_run(run)
            diagnostics: list[dict[str, Any]] = []
            if run_status == RunStatus.failed.value:
                diagnostics = [{"message": run.error_message or "run failed"}]
            envelope = self._envelope(
                event=self._terminal_event_for_status(run_status),
                run_id=run.id,
                app_id=UUID(str(app_id)),
                stage="run",
                payload=payload,
                diagnostics=diagnostics,
            )
            yield envelope
            return

        state = await self.ensure_monitor(app_id=app_id, run_id=run_id)
        if state is None:
            refreshed = await runtime.get_run_for_app(app_id=app_id, run_id=run_id)
            refreshed_status = refreshed.status.value if hasattr(refreshed.status, "value") else str(refreshed.status)
            if refreshed_status in _TERMINAL_RUN_STATUSES:
                asyncio.create_task(
                    self.__class__._finalize_terminal_scope_detached(app_id=app_id, run_id=run_id)
                )
            payload = runtime.serialize_run(refreshed)
            diagnostics: list[dict[str, Any]] = []
            if refreshed_status == RunStatus.failed.value:
                diagnostics = [{"message": refreshed.error_message or "run failed"}]
            envelope = self._envelope(
                event=self._terminal_event_for_status(refreshed_status),
                run_id=refreshed.id,
                app_id=UUID(str(app_id)),
                stage="run",
                payload=payload,
                diagnostics=diagnostics,
            )
            yield envelope
            return

        # Keep subscriber queue unbounded so assistant deltas are never dropped
        # under transient plan/tool event bursts.
        queue: asyncio.Queue = asyncio.Queue()
        attached = False
        async with self.__class__._monitors_lock:
            current = self.__class__._monitors.get(str(run_id))
            if current is not None:
                current.subscribers.add(queue)
                attached = True
                self.__class__._trace(
                    "monitor.subscriber_attached",
                    run_id=str(run_id),
                    app_id=str(app_id),
                    subscriber_count=len(current.subscribers),
                )

        if not attached:
            self.__class__._trace(
                "monitor.subscriber_attach_miss",
                run_id=str(run_id),
                app_id=str(app_id),
            )

        try:
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
                        terminal_envelope = self._envelope(
                            event=self._terminal_event_for_status(refreshed_status),
                            run_id=refreshed.id,
                            app_id=UUID(str(app_id)),
                            stage="run",
                            payload=runtime.serialize_run(refreshed),
                            diagnostics=diagnostics,
                        )
                        yield terminal_envelope
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
                force_terminal_on_inactivity = cls._monitor_force_terminal_on_inactivity()
                force_terminal_on_stream_end_without_terminal = (
                    cls._monitor_force_terminal_on_stream_end_without_terminal()
                )
                last_progress_at = monitor_started_at
                last_status_probe_at = 0.0
                last_plan_summary = ""
                awaiting_question_prompt = False

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
                        "tool.question",
                        "tool.question.answered",
                        "tool.question.rejected",
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
                        if (not awaiting_question_prompt) and run_elapsed_seconds >= max_runtime_seconds:
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
                        if (
                            force_terminal_on_inactivity
                            and (not awaiting_question_prompt)
                            and idle_progress_seconds >= inactivity_timeout_seconds
                        ):
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
                            if (
                                force_terminal_on_inactivity
                                and (not awaiting_question_prompt)
                                and idle_for_seconds >= inactivity_timeout_seconds
                            ):
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
                            refreshed_status_after_eof = await _read_run_status()
                            if refreshed_status_after_eof is None:
                                break
                            if refreshed_status_after_eof in _TERMINAL_RUN_STATUSES:
                                await _emit_terminal_from_status(status=refreshed_status_after_eof)
                                break
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
                        event_name = payload["event"]
                        if event_name == "tool.question":
                            awaiting_question_prompt = True
                        elif event_name in {"tool.question.answered", "tool.question.rejected"}:
                            awaiting_question_prompt = False
                        elif event_name in {"assistant.delta", "tool.started", "tool.completed", "tool.failed"}:
                            # Any resumed model/tool activity means question wait has been resolved.
                            awaiting_question_prompt = False
                        if _should_emit_event_to_subscribers(
                            event_name=event_name,
                            payload=payload["payload"],
                        ):
                            await cls._emit_to_subscribers(run_id=run_id, payload=payload)
                        if _is_progress_event(event_name=event_name, payload=payload["payload"]):
                            last_progress_at = time.monotonic()
                        if event_name in _TERMINAL_EVENTS:
                            terminal_emitted = True
                            awaiting_question_prompt = False
                            cls._trace(
                                "monitor.terminal_event_seen",
                                run_id=str(run_id),
                                app_id=str(app_id),
                                run_event=event_name,
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
                    if force_terminal_on_stream_end_without_terminal:
                        await _terminalize_stalled_run(
                            message="OpenCode stream ended before terminal event",
                            log_reason="stream_ended_no_terminal",
                        )
                        refreshed_run = await _load_run_fresh()
                        if refreshed_run is None:
                            return
                        refreshed_status = refreshed_run.status.value if hasattr(refreshed_run.status, "value") else str(refreshed_run.status)
                    else:
                        cls._trace(
                            "monitor.stream_ended_without_terminal_nonfatal",
                            run_id=str(run_id),
                            app_id=str(app_id),
                            status=refreshed_status,
                        )
                        return

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
                    asyncio.create_task(
                        cls._finalize_terminal_scope_detached(app_id=app_id, run_id=run_id)
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
                            asyncio.create_task(
                                cls._finalize_terminal_scope_detached(app_id=app_id, run_id=run_id)
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
