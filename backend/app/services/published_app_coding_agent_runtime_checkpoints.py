from __future__ import annotations

import logging
import time
from uuid import UUID

from fastapi import HTTPException

from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppDraftDevSessionStatus,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
)
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeDisabled, PublishedAppDraftDevRuntimeService
from app.services.published_app_revision_store import PublishedAppRevisionStore
from app.api.routers.published_apps_admin_files import _filter_builder_snapshot_files, _validate_builder_project_or_raise

logger = logging.getLogger(__name__)


class PublishedAppCodingAgentRuntimeCheckpointsMixin:
    async def restore_checkpoint(
        self,
        *,
        app: PublishedApp,
        checkpoint_revision_id: UUID,
        actor_id: UUID | None,
        run: AgentRun | None = None,
    ) -> PublishedAppRevision:
        checkpoint_revision = await self.db.get(PublishedAppRevision, checkpoint_revision_id)
        if checkpoint_revision is None or str(checkpoint_revision.published_app_id) != str(app.id):
            raise HTTPException(status_code=404, detail="Checkpoint revision not found")

        current_revision = await self.db.get(PublishedAppRevision, app.current_draft_revision_id)
        if current_revision is None:
            current_revision = checkpoint_revision
        revision_store = PublishedAppRevisionStore(self.db)
        checkpoint_files = await revision_store.materialize_revision_files(checkpoint_revision)

        restored = await self._create_draft_revision_from_files(
            app=app,
            current=current_revision,
            actor_id=actor_id,
            files=checkpoint_files,
            entry_file=checkpoint_revision.entry_file,
        )

        if actor_id is not None:
            runtime_service = PublishedAppDraftDevRuntimeService(self.db)
            try:
                await runtime_service.sync_session(
                    app=app,
                    revision=restored,
                    user_id=actor_id,
                    files=dict(restored.files or {}),
                    entry_file=restored.entry_file,
                )
            except PublishedAppDraftDevRuntimeDisabled:
                pass

        if run is not None:
            run.result_revision_id = restored.id
            run.checkpoint_revision_id = checkpoint_revision.id

        await self.db.commit()
        await self.db.refresh(restored)
        return restored

    async def _create_draft_revision_from_files(
        self,
        *,
        app: PublishedApp,
        current: PublishedAppRevision,
        actor_id: UUID | None,
        files: dict[str, str],
        entry_file: str,
    ) -> PublishedAppRevision:
        sanitized_files = _filter_builder_snapshot_files(files)
        _validate_builder_project_or_raise(sanitized_files, entry_file)
        revision_store = PublishedAppRevisionStore(self.db)
        manifest_json, bundle_hash = await revision_store.build_manifest_and_store_blobs(sanitized_files)
        revision = PublishedAppRevision(
            published_app_id=app.id,
            kind=PublishedAppRevisionKind.draft,
            template_key=app.template_key,
            entry_file=entry_file,
            files=sanitized_files,
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

    async def auto_apply_and_checkpoint(self, run: AgentRun) -> PublishedAppRevision | None:
        if run.result_revision_id is not None:
            existing = await self.db.get(PublishedAppRevision, run.result_revision_id)
            return existing

        if run.published_app_id is None:
            return None
        actor_id = run.initiator_user_id or run.user_id
        if actor_id is None:
            return None

        app = await self.db.get(PublishedApp, run.published_app_id)
        if app is None:
            return None

        current_revision_id = app.current_draft_revision_id or run.base_revision_id
        if current_revision_id is None:
            return None
        current = await self.db.get(PublishedAppRevision, current_revision_id)
        if current is None:
            return None

        runtime_service = PublishedAppDraftDevRuntimeService(self.db)
        input_params = run.input_params if isinstance(run.input_params, dict) else {}
        context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
        preview_sandbox_id = str(context.get("preview_sandbox_id") or "").strip()
        run_scope_id = str(run.id)

        if not preview_sandbox_id:
            try:
                session = await runtime_service.ensure_active_session(
                    app=app,
                    revision=current,
                    user_id=actor_id,
                )
            except PublishedAppDraftDevRuntimeDisabled:
                return None

            if session.status == PublishedAppDraftDevSessionStatus.error or not session.sandbox_id:
                return None
            preview_sandbox_id = str(session.sandbox_id)

        try:
            snapshot = await runtime_service.client.snapshot_workspace(
                sandbox_id=preview_sandbox_id,
                workspace="stage",
                run_id=run_scope_id,
            )
        except Exception:
            await runtime_service.client.prepare_stage_workspace(
                sandbox_id=preview_sandbox_id,
                run_id=run_scope_id,
            )
            snapshot = await runtime_service.client.snapshot_workspace(
                sandbox_id=preview_sandbox_id,
                workspace="stage",
                run_id=run_scope_id,
            )

        raw_files = snapshot.get("files")
        if not isinstance(raw_files, dict):
            return None
        files = _filter_builder_snapshot_files(raw_files)
        current_files = dict(current.files or {})
        if files == current_files:
            run.result_revision_id = None
            run.checkpoint_revision_id = None
            await self.db.commit()
            return None

        promote_started_at = time.monotonic()
        await runtime_service.client.promote_stage_workspace(
            sandbox_id=preview_sandbox_id,
            run_id=run_scope_id,
        )
        self._set_timing_metric_value(
            run,
            metric="promote_live",
            value=max(0, int((time.monotonic() - promote_started_at) * 1000)),
        )
        live_snapshot = await runtime_service.client.snapshot_workspace(
            sandbox_id=preview_sandbox_id,
            workspace="live",
            run_id=run_scope_id,
        )
        live_raw_files = live_snapshot.get("files")
        if not isinstance(live_raw_files, dict):
            raise RuntimeError("Preview live workspace snapshot did not return files after stage promotion")
        live_files = _filter_builder_snapshot_files(live_raw_files)

        revision = await self._create_draft_revision_from_files(
            app=app,
            current=current,
            actor_id=actor_id,
            files=live_files,
            entry_file=current.entry_file,
        )
        run.result_revision_id = revision.id
        run.checkpoint_revision_id = revision.id
        await self.db.commit()
        await self.db.refresh(revision)

        # If the user already has an active builder draft session, best-effort sync it
        # to the newly auto-applied revision so preview reflects coding-run changes.
        try:
            existing_builder_session = await runtime_service.get_session(
                app_id=app.id,
                user_id=actor_id,
            )
            if existing_builder_session is not None and existing_builder_session.sandbox_id:
                await runtime_service.sync_session(
                    app=app,
                    revision=revision,
                    user_id=actor_id,
                    files=live_files,
                    entry_file=revision.entry_file,
                )
                await self.db.commit()
        except PublishedAppDraftDevRuntimeDisabled:
            pass
        except Exception as exc:
            logger.warning(
                "Failed to sync existing builder draft session after auto-apply for app %s run %s: %s",
                app.id,
                run.id,
                exc,
            )
        return revision

