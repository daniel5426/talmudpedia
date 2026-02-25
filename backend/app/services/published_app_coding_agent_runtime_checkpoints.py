from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
import time
from uuid import UUID

from fastapi import HTTPException

from app.db.postgres.models.agents import AgentRun, RunStatus
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
    @staticmethod
    def _checkpoint_trace_enabled() -> bool:
        raw = str(os.getenv("APPS_CODING_AGENT_DEBUG_TRACE_ENABLED", "1") or "1").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _checkpoint_trace_file_path() -> str:
        return str(
            os.getenv("APPS_CODING_AGENT_DEBUG_TRACE_FILE", "/tmp/talmudpedia-coding-agent-trace.log")
            or "/tmp/talmudpedia-coding-agent-trace.log"
        ).strip()

    @classmethod
    def _checkpoint_trace(cls, event: str, **fields: object) -> None:
        if not cls._checkpoint_trace_enabled():
            return
        payload: dict[str, object] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        try:
            rendered = json.dumps(payload, sort_keys=True, default=str)
        except Exception:
            rendered = str(payload)
        try:
            with open(cls._checkpoint_trace_file_path(), "a", encoding="utf-8") as handle:
                handle.write(rendered + "\n")
        except Exception:
            pass

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
        self._checkpoint_trace("checkpoint.start", run_id=str(run.id), app_id=str(run.published_app_id or ""))
        logger.info(
            "CODING_AGENT_CHECKPOINT start run_id=%s app_id=%s existing_result_revision_id=%s",
            run.id,
            run.published_app_id,
            run.result_revision_id,
        )
        if run.result_revision_id is not None:
            existing = await self.db.get(PublishedAppRevision, run.result_revision_id)
            logger.info(
                "CODING_AGENT_CHECKPOINT already_has_result run_id=%s revision_id=%s exists=%s",
                run.id,
                run.result_revision_id,
                existing is not None,
            )
            return existing

        if run.published_app_id is None:
            logger.info("CODING_AGENT_CHECKPOINT skip_missing_app_id run_id=%s", run.id)
            return None
        actor_id = run.initiator_user_id or run.user_id
        if actor_id is None:
            logger.info("CODING_AGENT_CHECKPOINT skip_missing_actor run_id=%s", run.id)
            return None

        app = await self.db.get(PublishedApp, run.published_app_id)
        if app is None:
            logger.info("CODING_AGENT_CHECKPOINT skip_app_not_found run_id=%s app_id=%s", run.id, run.published_app_id)
            return None

        current_revision_id = app.current_draft_revision_id or run.base_revision_id
        if current_revision_id is None:
            logger.info("CODING_AGENT_CHECKPOINT skip_missing_current_revision run_id=%s app_id=%s", run.id, app.id)
            return None
        current = await self.db.get(PublishedAppRevision, current_revision_id)
        if current is None:
            logger.info(
                "CODING_AGENT_CHECKPOINT skip_current_revision_not_found run_id=%s revision_id=%s",
                run.id,
                current_revision_id,
            )
            return None

        runtime_service = PublishedAppDraftDevRuntimeService(self.db)
        input_params = run.input_params if isinstance(run.input_params, dict) else {}
        context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
        preview_sandbox_id = str(context.get("preview_sandbox_id") or "").strip()
        if not preview_sandbox_id:
            logger.info("CODING_AGENT_CHECKPOINT resolve_sandbox_from_session run_id=%s app_id=%s", run.id, app.id)
            try:
                session = await runtime_service.ensure_active_session(
                    app=app,
                    revision=current,
                    user_id=actor_id,
                )
            except PublishedAppDraftDevRuntimeDisabled:
                logger.info("CODING_AGENT_CHECKPOINT skip_runtime_disabled run_id=%s", run.id)
                return None

            if session.status == PublishedAppDraftDevSessionStatus.error or not session.sandbox_id:
                logger.warning(
                    "CODING_AGENT_CHECKPOINT skip_session_unusable run_id=%s session_id=%s status=%s last_error=%s",
                    run.id,
                    session.id,
                    session.status,
                    session.last_error,
                )
                return None
            preview_sandbox_id = str(session.sandbox_id)
        logger.info(
            "CODING_AGENT_CHECKPOINT using_sandbox run_id=%s sandbox_id=%s current_revision_id=%s",
            run.id,
            preview_sandbox_id,
            current.id,
        )

        try:
            snapshot = await runtime_service.client.snapshot_workspace(
                sandbox_id=preview_sandbox_id,
                workspace="stage",
            )
        except Exception as exc:
            logger.warning(
                "CODING_AGENT_CHECKPOINT stage_snapshot_failed_retrying_prepare run_id=%s sandbox_id=%s error=%s",
                run.id,
                preview_sandbox_id,
                exc,
            )
            await runtime_service.client.prepare_stage_workspace(
                sandbox_id=preview_sandbox_id,
                reset=False,
            )
            snapshot = await runtime_service.client.snapshot_workspace(
                sandbox_id=preview_sandbox_id,
                workspace="stage",
            )

        raw_files = snapshot.get("files")
        if not isinstance(raw_files, dict):
            logger.warning(
                "CODING_AGENT_CHECKPOINT skip_stage_snapshot_invalid_files run_id=%s sandbox_id=%s payload_keys=%s",
                run.id,
                preview_sandbox_id,
                list(snapshot.keys()) if isinstance(snapshot, dict) else [],
            )
            return None
        files = _filter_builder_snapshot_files(raw_files)
        current_files = dict(current.files or {})
        logger.info(
            "CODING_AGENT_CHECKPOINT stage_snapshot_ok run_id=%s stage_file_count=%s filtered_stage_file_count=%s current_file_count=%s",
            run.id,
            len(raw_files),
            len(files),
            len(current_files),
        )
        if files == current_files:
            self._checkpoint_trace(
                "checkpoint.skip_no_diff",
                run_id=str(run.id),
                sandbox_id=preview_sandbox_id,
                stage_file_count=len(files),
                current_file_count=len(current_files),
            )
            logger.info(
                "CODING_AGENT_CHECKPOINT skip_no_diff run_id=%s sandbox_id=%s",
                run.id,
                preview_sandbox_id,
            )
            run.result_revision_id = None
            run.checkpoint_revision_id = None
            await self.db.commit()
            return None

        promote_started_at = time.monotonic()
        self._checkpoint_trace("checkpoint.promote_begin", run_id=str(run.id), sandbox_id=preview_sandbox_id)
        logger.info("CODING_AGENT_CHECKPOINT promote_stage_begin run_id=%s sandbox_id=%s", run.id, preview_sandbox_id)
        await runtime_service.client.promote_stage_workspace(
            sandbox_id=preview_sandbox_id,
        )
        self._set_timing_metric_value(
            run,
            metric="promote_live",
            value=max(0, int((time.monotonic() - promote_started_at) * 1000)),
        )
        live_snapshot = await runtime_service.client.snapshot_workspace(
            sandbox_id=preview_sandbox_id,
            workspace="live",
        )
        live_raw_files = live_snapshot.get("files")
        if not isinstance(live_raw_files, dict):
            self._checkpoint_trace(
                "checkpoint.live_snapshot_invalid",
                run_id=str(run.id),
                sandbox_id=preview_sandbox_id,
            )
            logger.error(
                "CODING_AGENT_CHECKPOINT live_snapshot_invalid_files run_id=%s sandbox_id=%s payload_keys=%s",
                run.id,
                preview_sandbox_id,
                list(live_snapshot.keys()) if isinstance(live_snapshot, dict) else [],
            )
            raise RuntimeError("Preview live workspace snapshot did not return files after stage promotion")
        live_files = _filter_builder_snapshot_files(live_raw_files)
        self._checkpoint_trace(
            "checkpoint.promote_ok",
            run_id=str(run.id),
            sandbox_id=preview_sandbox_id,
            live_file_count=len(live_files),
        )
        logger.info(
            "CODING_AGENT_CHECKPOINT promote_stage_ok run_id=%s live_file_count=%s filtered_live_file_count=%s",
            run.id,
            len(live_raw_files),
            len(live_files),
        )

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
        self._checkpoint_trace(
            "checkpoint.revision_created",
            run_id=str(run.id),
            revision_id=str(revision.id),
            file_count=len(revision.files or {}),
        )
        logger.info(
            "CODING_AGENT_CHECKPOINT revision_created run_id=%s revision_id=%s file_count=%s",
            run.id,
            revision.id,
            len(revision.files or {}),
        )

        # If the user already has an active builder draft session, best-effort sync it
        # to the newly auto-applied revision so preview reflects coding-run changes.
        try:
            existing_builder_session = await runtime_service.get_session(
                app_id=app.id,
                user_id=actor_id,
            )
            if existing_builder_session is not None and existing_builder_session.sandbox_id:
                logger.info(
                    "CODING_AGENT_CHECKPOINT sync_builder_session_begin run_id=%s session_id=%s sandbox_id=%s",
                    run.id,
                    existing_builder_session.id,
                    existing_builder_session.sandbox_id,
                )
                await runtime_service.sync_session(
                    app=app,
                    revision=revision,
                    user_id=actor_id,
                    files=live_files,
                    entry_file=revision.entry_file,
                )
                await self.db.commit()
                self._checkpoint_trace(
                    "checkpoint.sync_builder_session_ok",
                    run_id=str(run.id),
                    session_id=str(existing_builder_session.id),
                )
                logger.info(
                    "CODING_AGENT_CHECKPOINT sync_builder_session_ok run_id=%s session_id=%s",
                    run.id,
                    existing_builder_session.id,
                )
            else:
                self._checkpoint_trace(
                    "checkpoint.sync_builder_session_skipped",
                    run_id=str(run.id),
                    reason="no_active_session",
                )
                logger.info(
                    "CODING_AGENT_CHECKPOINT sync_builder_session_skipped run_id=%s reason=no_active_session",
                    run.id,
                )
        except PublishedAppDraftDevRuntimeDisabled:
            self._checkpoint_trace(
                "checkpoint.sync_builder_session_skipped",
                run_id=str(run.id),
                reason="runtime_disabled",
            )
            logger.info("CODING_AGENT_CHECKPOINT sync_builder_session_skipped run_id=%s reason=runtime_disabled", run.id)
        except Exception as exc:
            self._checkpoint_trace(
                "checkpoint.sync_builder_session_failed",
                run_id=str(run.id),
                error=str(exc),
            )
            logger.warning(
                "Failed to sync existing builder draft session after auto-apply for app %s run %s: %s",
                app.id,
                run.id,
                exc,
            )
        return revision

    async def finalize_completed_run_postprocessing(self, *, run_id: UUID) -> tuple[str | None, str | None]:
        run = await self.db.get(AgentRun, run_id)
        if run is None:
            return None, None
        status = run.status.value if hasattr(run.status, "value") else str(run.status)
        if status != RunStatus.completed.value:
            return None, None

        revision = await self.auto_apply_and_checkpoint(run)
        refreshed_run = await self.db.get(AgentRun, run_id)
        revision_id = str(revision.id) if revision is not None else None
        checkpoint_id = None
        if refreshed_run is not None and refreshed_run.checkpoint_revision_id is not None:
            checkpoint_id = str(refreshed_run.checkpoint_revision_id)
        return revision_id, checkpoint_id
