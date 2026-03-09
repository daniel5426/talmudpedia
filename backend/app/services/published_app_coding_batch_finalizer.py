from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.published_apps_admin_builder_core import _next_build_seq
from app.api.routers.published_apps_admin_files import _filter_builder_snapshot_files, _validate_builder_project_or_raise
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
)
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from app.services.apps_builder_trace import apps_builder_trace
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService
from app.services.published_app_revision_build_dispatch import (
    enqueue_revision_build,
    mark_revision_build_enqueue_failed,
)
from app.services.published_app_versioning import create_app_version

_ACTIVE_RUN_STATUSES = {RunStatus.queued, RunStatus.running}
_TERMINAL_RUN_STATUSES = {
    RunStatus.completed,
    RunStatus.failed,
    RunStatus.cancelled,
    RunStatus.paused,
}


class PublishedAppCodingBatchFinalizer:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _scope_filters(*, app_id: UUID) -> list[Any]:
        return [
            AgentRun.surface == CODING_AGENT_SURFACE,
            AgentRun.published_app_id == app_id,
        ]

    async def _count_active_runs(self, *, app_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count(AgentRun.id)).where(
                and_(
                    *self._scope_filters(app_id=app_id),
                    AgentRun.status.in_(list(_ACTIVE_RUN_STATUSES)),
                )
            )
        )
        return int(result.scalar() or 0)

    async def _load_unfinalized_completed_runs(self, *, app_id: UUID) -> list[AgentRun]:
        result = await self.db.execute(
            select(AgentRun)
            .where(
                and_(
                    *self._scope_filters(app_id=app_id),
                    AgentRun.status == RunStatus.completed,
                    AgentRun.batch_finalized_at.is_(None),
                )
            )
            .order_by(AgentRun.created_at.asc())
        )
        return list(result.scalars().all())

    async def _try_scope_advisory_lock(self, *, app_id: UUID) -> tuple[bool, int | None]:
        dialect_name = str(getattr(getattr(self.db.get_bind(), "dialect", None), "name", "")).lower()
        if dialect_name != "postgresql":
            return True, None
        lock_key = (app_id.int & ((1 << 63) - 1))
        result = await self.db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": int(lock_key)})
        return bool(result.scalar_one_or_none()), int(lock_key)

    async def _release_scope_advisory_lock(self, lock_key: int | None) -> None:
        if lock_key is None:
            return
        await self.db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": int(lock_key)})

    async def _snapshot_shared_stage_files(
        self,
        *,
        runtime_service: PublishedAppDraftDevRuntimeService,
        sandbox_id: str,
    ) -> dict[str, str]:
        try:
            snapshot = await runtime_service.client.snapshot_workspace(
                sandbox_id=sandbox_id,
                workspace="stage",
            )
        except Exception:
            await runtime_service.client.prepare_stage_workspace(
                sandbox_id=sandbox_id,
                reset=False,
            )
            snapshot = await runtime_service.client.snapshot_workspace(
                sandbox_id=sandbox_id,
                workspace="stage",
            )
        files = snapshot.get("files")
        if not isinstance(files, dict):
            raise RuntimeError("Shared stage workspace snapshot did not return files")
        filtered = _filter_builder_snapshot_files(files)
        apps_builder_trace(
            "batch_finalizer.stage_snapshot",
            domain="coding_agent.finalizer",
            sandbox_id=sandbox_id,
            file_count=len(filtered),
        )
        return filtered

    async def _snapshot_live_files(
        self,
        *,
        runtime_service: PublishedAppDraftDevRuntimeService,
        sandbox_id: str,
    ) -> dict[str, str]:
        snapshot = await runtime_service.client.snapshot_workspace(
            sandbox_id=sandbox_id,
            workspace="live",
        )
        files = snapshot.get("files")
        if not isinstance(files, dict):
            raise RuntimeError("Live workspace snapshot did not return files")
        filtered = _filter_builder_snapshot_files(files)
        apps_builder_trace(
            "batch_finalizer.live_snapshot",
            domain="coding_agent.finalizer",
            sandbox_id=sandbox_id,
            file_count=len(filtered),
        )
        return filtered

    async def _prepare_finalized_live_snapshot(
        self,
        *,
        app_id: UUID,
        sample_run: AgentRun,
    ) -> tuple[PublishedApp, PublishedAppRevision, dict[str, str] | None]:
        app = await self.db.get(PublishedApp, app_id)
        if app is None:
            raise RuntimeError("App not found")

        current_revision_id = app.current_draft_revision_id or sample_run.base_revision_id
        if current_revision_id is None:
            raise RuntimeError("Current draft revision not found")
        current = await self.db.get(PublishedAppRevision, current_revision_id)
        if current is None:
            raise RuntimeError("Current draft revision not found")

        runtime_service = PublishedAppDraftDevRuntimeService(self.db)
        workspace = await runtime_service.get_workspace(app_id=app_id)
        if workspace is None or not workspace.sandbox_id:
            return app, current, None
        sandbox_id = str(workspace.sandbox_id)

        stage_files = await self._snapshot_shared_stage_files(
            runtime_service=runtime_service,
            sandbox_id=sandbox_id,
        )
        if stage_files == dict(current.files or {}):
            apps_builder_trace(
                "batch_finalizer.noop",
                domain="coding_agent.finalizer",
                app_id=str(app_id),
                actor_id=str(sample_run.initiator_user_id or sample_run.user_id or "") or None,
                sandbox_id=sandbox_id,
                reason="stage_matches_current_revision",
                current_revision_id=str(current.id),
            )
            return app, current, None

        await runtime_service.client.promote_stage_workspace(sandbox_id=sandbox_id)
        apps_builder_trace(
            "batch_finalizer.promote_stage",
            domain="coding_agent.finalizer",
            app_id=str(app_id),
            actor_id=str(sample_run.initiator_user_id or sample_run.user_id or "") or None,
            sandbox_id=sandbox_id,
            current_revision_id=str(current.id),
        )
        live_files = await self._snapshot_live_files(
            runtime_service=runtime_service,
            sandbox_id=sandbox_id,
        )
        return app, current, live_files

    async def finalize_for_terminal_run(self, *, run_id: UUID) -> dict[str, Any]:
        run = await self.db.get(AgentRun, run_id)
        apps_builder_trace(
            "batch_finalizer.requested",
            domain="coding_agent.finalizer",
            run_id=str(run_id),
            app_id=str(getattr(run, "published_app_id", "") or "") or None,
            actor_id=str((getattr(run, "initiator_user_id", None) or getattr(run, "user_id", None)) or "") or None,
        )
        if run is None:
            return {"status": "run_not_found"}
        if str(run.surface or "") != CODING_AGENT_SURFACE:
            return {"status": "surface_not_supported"}
        status_value = run.status.value if hasattr(run.status, "value") else str(run.status)
        terminal_values = {item.value for item in _TERMINAL_RUN_STATUSES}
        if status_value not in terminal_values:
            return {"status": "run_not_terminal"}
        app_id = run.published_app_id
        if app_id is None:
            return {"status": "scope_unavailable"}

        lock_acquired = False
        lock_key: int | None = None
        try:
            lock_acquired, lock_key = await self._try_scope_advisory_lock(app_id=app_id)
            if not lock_acquired:
                return {"status": "scope_lock_busy"}

            active_count = await self._count_active_runs(app_id=app_id)
            if active_count > 0:
                apps_builder_trace(
                    "batch_finalizer.deferred",
                    domain="coding_agent.finalizer",
                    run_id=str(run_id),
                    app_id=str(app_id),
                    actor_id=str(run.initiator_user_id or run.user_id or "") or None,
                    active_count=active_count,
                )
                return {"status": "active_runs_remaining", "active_count": active_count}

            completed_candidates = await self._load_unfinalized_completed_runs(app_id=app_id)
            if not completed_candidates:
                return {"status": "no_unfinalized_completed_runs"}

            app, current, live_files = await self._prepare_finalized_live_snapshot(
                app_id=app_id,
                sample_run=completed_candidates[-1],
            )

            finalized_at = datetime.now(timezone.utc)
            created_by_run: dict[str, str] = {}
            build_enqueue_by_run: dict[str, dict[str, str | bool]] = {}
            batch_revision: PublishedAppRevision | None = None

            if live_files is not None:
                _validate_builder_project_or_raise(live_files, current.entry_file)
                apps_builder_trace(
                    "batch_finalizer.live_files_ready",
                    domain="coding_agent.finalizer",
                    run_id=str(run_id),
                    app_id=str(app_id),
                    actor_id=str(run.initiator_user_id or run.user_id or "") or None,
                    file_count=len(live_files),
                    current_revision_id=str(current.id),
                )

            if live_files is not None and live_files != dict(current.files or {}):
                created_by = completed_candidates[-1].initiator_user_id or completed_candidates[-1].user_id
                batch_revision = await create_app_version(
                    self.db,
                    app=app,
                    kind=PublishedAppRevisionKind.draft,
                    template_key=app.template_key,
                    entry_file=current.entry_file,
                    files=live_files,
                    created_by=created_by,
                    source_revision_id=current.id,
                    origin_kind="coding_run",
                    origin_run_id=completed_candidates[-1].id,
                    build_status=PublishedAppRevisionBuildStatus.queued,
                    build_seq=_next_build_seq(current),
                    template_runtime=current.template_runtime or "vite_static",
                )
                app.current_draft_revision_id = batch_revision.id
                apps_builder_trace(
                    "batch_finalizer.revision_created",
                    domain="coding_agent.finalizer",
                    run_id=str(completed_candidates[-1].id),
                    app_id=str(app_id),
                    actor_id=str(created_by or "") or None,
                    revision_id=str(batch_revision.id),
                    source_revision_id=str(current.id),
                    candidate_count=len(completed_candidates),
                )
                enqueue_error = enqueue_revision_build(
                    revision=batch_revision,
                    app=app,
                    build_kind="coding_run",
                )
                build_result: dict[str, str | bool]
                if enqueue_error:
                    mark_revision_build_enqueue_failed(
                        revision=batch_revision,
                        reason=enqueue_error,
                    )
                    build_result = {
                        "ok": False,
                        "error": enqueue_error,
                    }
                else:
                    build_result = {"ok": True}
            else:
                build_result = {"ok": True}

            for candidate in completed_candidates:
                candidate.batch_finalized_at = finalized_at
                candidate.result_revision_id = batch_revision.id if batch_revision is not None else None
                if batch_revision is not None:
                    created_by_run[str(candidate.id)] = str(batch_revision.id)
                    build_enqueue_by_run[str(candidate.id)] = dict(build_result)

            await self.db.commit()
            apps_builder_trace(
                "batch_finalizer.completed",
                domain="coding_agent.finalizer",
                run_id=str(run_id),
                app_id=str(app_id),
                actor_id=str(run.initiator_user_id or run.user_id or "") or None,
                candidate_count=len(completed_candidates),
                latest_revision_id=str(app.current_draft_revision_id) if app.current_draft_revision_id else None,
                live_files_present=live_files is not None,
            )
            return {
                "status": "finalized",
                "candidate_count": len(completed_candidates),
                "revision_ids_by_run": created_by_run,
                "build_enqueue_by_run": build_enqueue_by_run,
                "latest_revision_id": str(app.current_draft_revision_id) if app.current_draft_revision_id else None,
            }
        finally:
            if lock_acquired:
                await self._release_scope_advisory_lock(lock_key)
