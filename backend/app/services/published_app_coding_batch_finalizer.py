from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.published_apps_admin_files import _filter_builder_snapshot_files, _validate_builder_project_or_raise
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
)
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService
from app.services.published_app_revision_store import PublishedAppRevisionStore

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
    def _scope_filters(*, app_id: UUID, actor_id: UUID) -> list[Any]:
        return [
            AgentRun.surface == CODING_AGENT_SURFACE,
            AgentRun.published_app_id == app_id,
            or_(
                AgentRun.initiator_user_id == actor_id,
                and_(AgentRun.initiator_user_id.is_(None), AgentRun.user_id == actor_id),
            ),
        ]

    async def _count_active_runs(self, *, app_id: UUID, actor_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count(AgentRun.id)).where(
                and_(
                    *self._scope_filters(app_id=app_id, actor_id=actor_id),
                    AgentRun.status.in_(list(_ACTIVE_RUN_STATUSES)),
                )
            )
        )
        return int(result.scalar() or 0)

    async def _load_unfinalized_completed_runs(self, *, app_id: UUID, actor_id: UUID) -> list[AgentRun]:
        result = await self.db.execute(
            select(AgentRun)
            .where(
                and_(
                    *self._scope_filters(app_id=app_id, actor_id=actor_id),
                    AgentRun.status == RunStatus.completed,
                    AgentRun.batch_finalized_at.is_(None),
                )
            )
            .order_by(AgentRun.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    def _pick_owner_run(runs: list[AgentRun]) -> AgentRun | None:
        if not runs:
            return None
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return max(
            runs,
            key=lambda run: (
                run.completed_at or run.created_at or epoch,
                run.created_at or epoch,
                str(run.id),
            ),
        )

    async def _try_scope_advisory_lock(self, *, app_id: UUID, actor_id: UUID) -> tuple[bool, int | None]:
        dialect_name = str(getattr(getattr(self.db.get_bind(), "dialect", None), "name", "")).lower()
        if dialect_name != "postgresql":
            return True, None
        lock_key = ((app_id.int ^ (actor_id.int << 1)) & ((1 << 63) - 1))
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
        return _filter_builder_snapshot_files(files)

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
        return _filter_builder_snapshot_files(files)

    async def _create_draft_revision(
        self,
        *,
        app: PublishedApp,
        current: PublishedAppRevision,
        actor_id: UUID | None,
        files: dict[str, str],
    ) -> PublishedAppRevision:
        _validate_builder_project_or_raise(files, current.entry_file)
        revision_store = PublishedAppRevisionStore(self.db)
        manifest_json, bundle_hash = await revision_store.build_manifest_and_store_blobs(files)
        revision = PublishedAppRevision(
            published_app_id=app.id,
            kind=PublishedAppRevisionKind.draft,
            template_key=app.template_key,
            entry_file=current.entry_file,
            files=files,
            manifest_json=manifest_json,
            build_status=PublishedAppRevisionBuildStatus.queued,
            build_seq=int(current.build_seq or 0) + 1,
            build_error=None,
            build_started_at=None,
            build_finished_at=None,
            dist_storage_prefix=None,
            dist_manifest=None,
            template_runtime="vite_static",
            compiled_bundle=None,
            bundle_hash=bundle_hash,
            source_revision_id=current.id,
            created_by=actor_id,
        )
        self.db.add(revision)
        await self.db.flush()
        app.current_draft_revision_id = revision.id
        return revision

    async def _promote_shared_stage_and_create_revision(
        self,
        *,
        app_id: UUID,
        actor_id: UUID,
        owner_run: AgentRun,
    ) -> UUID | None:
        app = await self.db.get(PublishedApp, app_id)
        if app is None:
            return None
        current_revision_id = app.current_draft_revision_id or owner_run.base_revision_id
        if current_revision_id is None:
            return None
        current = await self.db.get(PublishedAppRevision, current_revision_id)
        if current is None:
            return None

        runtime_service = PublishedAppDraftDevRuntimeService(self.db)
        session = await runtime_service.get_session(app_id=app_id, user_id=actor_id)
        if session is None or not session.sandbox_id:
            return None
        sandbox_id = str(session.sandbox_id)

        stage_files = await self._snapshot_shared_stage_files(
            runtime_service=runtime_service,
            sandbox_id=sandbox_id,
        )
        if stage_files == dict(current.files or {}):
            return None

        await runtime_service.client.promote_stage_workspace(sandbox_id=sandbox_id)
        live_files = await self._snapshot_live_files(
            runtime_service=runtime_service,
            sandbox_id=sandbox_id,
        )
        revision = await self._create_draft_revision(
            app=app,
            current=current,
            actor_id=actor_id,
            files=live_files,
        )
        return revision.id

    async def finalize_for_terminal_run(self, *, run_id: UUID) -> dict[str, Any]:
        run = await self.db.get(AgentRun, run_id)
        if run is None:
            return {"status": "run_not_found"}
        if str(run.surface or "") != CODING_AGENT_SURFACE:
            return {"status": "surface_not_supported"}
        status_value = run.status.value if hasattr(run.status, "value") else str(run.status)
        terminal_values = {item.value for item in _TERMINAL_RUN_STATUSES}
        if status_value not in terminal_values:
            return {"status": "run_not_terminal"}
        app_id = run.published_app_id
        actor_id = run.initiator_user_id or run.user_id
        if app_id is None or actor_id is None:
            return {"status": "scope_unavailable"}

        lock_acquired = False
        lock_key: int | None = None
        try:
            lock_acquired, lock_key = await self._try_scope_advisory_lock(app_id=app_id, actor_id=actor_id)
            if not lock_acquired:
                return {"status": "scope_lock_busy"}

            active_count = await self._count_active_runs(app_id=app_id, actor_id=actor_id)
            if active_count > 0:
                return {"status": "active_runs_remaining", "active_count": active_count}

            completed_candidates = await self._load_unfinalized_completed_runs(app_id=app_id, actor_id=actor_id)
            if not completed_candidates:
                return {"status": "no_unfinalized_completed_runs"}

            owner_run = self._pick_owner_run(completed_candidates)
            if owner_run is None:
                return {"status": "no_owner_run"}

            revision_id = await self._promote_shared_stage_and_create_revision(
                app_id=app_id,
                actor_id=actor_id,
                owner_run=owner_run,
            )

            finalized_at = datetime.now(timezone.utc)
            for candidate in completed_candidates:
                is_owner = str(candidate.id) == str(owner_run.id)
                candidate.batch_finalized_at = finalized_at
                candidate.batch_owner = is_owner
                if is_owner and revision_id is not None:
                    candidate.result_revision_id = revision_id
                    candidate.checkpoint_revision_id = revision_id
                else:
                    candidate.result_revision_id = None
                    candidate.checkpoint_revision_id = None

            await self.db.commit()
            return {
                "status": "finalized",
                "candidate_count": len(completed_candidates),
                "owner_run_id": str(owner_run.id),
                "revision_id": str(revision_id) if revision_id is not None else None,
            }
        finally:
            if lock_acquired:
                await self._release_scope_advisory_lock(lock_key)
