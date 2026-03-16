from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
)
from app.services.apps_builder_trace import apps_builder_trace
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService
from app.services.published_app_templates import TemplateRuntimeContext, apply_runtime_bootstrap_overlay
from app.services.published_app_versioning import create_app_version
from app.services.published_app_workspace_build_service import (
    PublishedAppWorkspaceBuildError,
    PublishedAppWorkspaceBuildService,
    ReadyWorkspaceBuildResult,
)


@dataclass(frozen=True)
class MaterializedDraftRevisionResult:
    revision: PublishedAppRevision
    reused: bool
    source_fingerprint: str
    workspace_revision_token: str | None


class PublishedAppDraftRevisionMaterializerError(Exception):
    pass


class PublishedAppDraftRevisionMaterializerService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.runtime_service = PublishedAppDraftDevRuntimeService(db)
        self.workspace_builds = PublishedAppWorkspaceBuildService(db)

    @staticmethod
    def _trace(event: str, *, app_id: UUID, **fields: Any) -> None:
        apps_builder_trace(
            event,
            domain="draft_revision.materializer",
            app_id=str(app_id),
            **fields,
        )

    @staticmethod
    def _workspace_lock_key(*, app_id: UUID) -> int:
        digest = hashlib.sha256(f"draft-revision-materialize:{app_id}".encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF

    async def _acquire_app_lock(self, *, app_id: UUID) -> None:
        bind = self.db.get_bind()
        dialect_name = str(getattr(getattr(bind, "dialect", None), "name", "") or "").lower()
        if dialect_name == "sqlite":
            return
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": int(self._workspace_lock_key(app_id=app_id))},
        )

    async def _find_existing_revision_for_build(
        self,
        *,
        app_id: UUID,
        workspace_build_id: UUID,
    ) -> PublishedAppRevision | None:
        result = await self.db.execute(
            select(PublishedAppRevision)
            .where(
                PublishedAppRevision.published_app_id == app_id,
                PublishedAppRevision.kind == PublishedAppRevisionKind.draft,
                PublishedAppRevision.workspace_build_id == workspace_build_id,
                PublishedAppRevision.build_status == PublishedAppRevisionBuildStatus.succeeded,
            )
            .order_by(PublishedAppRevision.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _create_or_reuse_revision_from_build(
        self,
        *,
        app: PublishedApp,
        build_result: ReadyWorkspaceBuildResult,
        source_revision_id: UUID | None,
        created_by: UUID | None,
        origin_kind: str,
        origin_run_id: UUID | None,
    ) -> MaterializedDraftRevisionResult:
        existing = await self._find_existing_revision_for_build(
            app_id=app.id,
            workspace_build_id=build_result.build.id,
        )
        if existing is not None:
            app.current_draft_revision_id = existing.id
            await self.runtime_service.bind_live_workspace_snapshot_to_revision(
                app_id=app.id,
                revision_id=existing.id,
            )
            self._trace(
                "materialize.reused_existing_revision",
                app_id=app.id,
                revision_id=str(existing.id),
                source_fingerprint=build_result.source_fingerprint,
                workspace_revision_token=str(build_result.workspace_revision_token or ""),
                workspace_build_id=str(build_result.build.id),
            )
            return MaterializedDraftRevisionResult(
                revision=existing,
                reused=True,
                source_fingerprint=build_result.source_fingerprint,
                workspace_revision_token=build_result.workspace_revision_token,
            )

        template_runtime_context = TemplateRuntimeContext(
            app_id=str(app.id),
            app_slug=str(app.slug or ""),
            agent_id=str(app.agent_id or ""),
        )
        revision_files = apply_runtime_bootstrap_overlay(
            dict(build_result.source_files),
            runtime_context=template_runtime_context,
        )
        build_seq = 0
        if source_revision_id is not None:
            source_revision = await self.db.get(PublishedAppRevision, source_revision_id)
            if source_revision is not None:
                build_seq = int(source_revision.build_seq or 0)

        self._trace(
            "materialize.revision_create.begin",
            app_id=app.id,
            source_revision_id=str(source_revision_id or ""),
            source_fingerprint=build_result.source_fingerprint,
            workspace_build_id=str(build_result.build.id),
        )
        revision = await create_app_version(
            self.db,
            workspace_build_id=build_result.build.id,
            app=app,
            kind=PublishedAppRevisionKind.draft,
            template_key=app.template_key,
            entry_file=build_result.build.entry_file,
            files=revision_files,
            created_by=created_by,
            source_revision_id=source_revision_id,
            origin_kind=origin_kind,
            origin_run_id=origin_run_id,
            build_status=PublishedAppRevisionBuildStatus.succeeded,
            build_seq=build_seq + 1,
            build_error=None,
            build_started_at=build_result.build.build_started_at,
            build_finished_at=build_result.build.build_finished_at,
            dist_storage_prefix=build_result.build.dist_storage_prefix,
            dist_manifest=dict(build_result.build.dist_manifest or {}),
            template_runtime=str(build_result.build.template_runtime or "vite_static"),
        )
        app.current_draft_revision_id = revision.id
        await self.runtime_service.bind_live_workspace_snapshot_to_revision(
            app_id=app.id,
            revision_id=revision.id,
        )
        self._trace(
            "materialize.revision_create.done",
            app_id=app.id,
            revision_id=str(revision.id),
            workspace_build_id=str(build_result.build.id),
        )
        return MaterializedDraftRevisionResult(
            revision=revision,
            reused=False,
            source_fingerprint=build_result.source_fingerprint,
            workspace_revision_token=build_result.workspace_revision_token,
        )

    async def materialize_live_workspace(
        self,
        *,
        app: PublishedApp,
        entry_file: str,
        source_revision_id: UUID | None,
        created_by: UUID | None,
        origin_kind: str,
        origin_run_id: UUID | None = None,
    ) -> MaterializedDraftRevisionResult:
        self._trace(
            "materialize.begin",
            app_id=app.id,
            origin_kind=origin_kind,
            origin_run_id=str(origin_run_id or ""),
            source_revision_id=str(source_revision_id or ""),
        )
        await self._acquire_app_lock(app_id=app.id)
        try:
            build_result = await self.workspace_builds.ensure_ready_build(
                app=app,
                entry_file=entry_file,
                source_revision_id=source_revision_id,
                created_by=created_by,
                origin_kind=origin_kind,
                origin_run_id=origin_run_id,
            )
            result = await self._create_or_reuse_revision_from_build(
                app=app,
                build_result=build_result,
                source_revision_id=source_revision_id,
                created_by=created_by,
                origin_kind=origin_kind,
                origin_run_id=origin_run_id,
            )
        except PublishedAppWorkspaceBuildError as exc:
            self._trace(
                "materialize.failed",
                app_id=app.id,
                origin_kind=origin_kind,
                run_id=str(origin_run_id or ""),
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            raise PublishedAppDraftRevisionMaterializerError(str(exc)) from exc
        except Exception as exc:
            self._trace(
                "materialize.failed",
                app_id=app.id,
                origin_kind=origin_kind,
                run_id=str(origin_run_id or ""),
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            raise

        self._trace(
            "materialize.done",
            app_id=app.id,
            revision_id=str(result.revision.id),
            reused=result.reused,
            source_fingerprint=result.source_fingerprint,
            workspace_revision_token=str(result.workspace_revision_token or ""),
            workspace_build_id=str(result.revision.workspace_build_id or ""),
        )
        return result

    async def finalize_run_materialization(
        self,
        *,
        app: PublishedApp,
        run: AgentRun,
        entry_file: str,
        source_revision_id: UUID | None,
        created_by: UUID | None,
    ) -> PublishedAppRevision | None:
        if not bool(getattr(run, "has_workspace_writes", False)):
            return None
        if getattr(run, "result_revision_id", None) is not None:
            revision = await self.db.get(PublishedAppRevision, run.result_revision_id)
            return revision
        result = await self.materialize_live_workspace(
            app=app,
            entry_file=entry_file,
            source_revision_id=source_revision_id,
            created_by=created_by,
            origin_kind="coding_run",
            origin_run_id=run.id,
        )
        run.result_revision_id = result.revision.id
        run.batch_finalized_at = datetime.now(timezone.utc)
        return result.revision
