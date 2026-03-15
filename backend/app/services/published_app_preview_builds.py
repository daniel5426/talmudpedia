from __future__ import annotations

import base64
import json
import logging
import mimetypes
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppDraftWorkspace,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
)
from app.services.published_app_bundle_storage import PublishedAppBundleStorage
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService
from app.services.published_app_versioning import create_app_version

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreviewBuildSnapshot:
    build_id: str
    build_seq: int
    built_at: datetime | None
    status: str
    last_error: str | None
    snapshot_root: str
    source_root: str
    dist_root: str
    source_bundle_hash: str | None
    entry_file: str
    dist_manifest: Dict[str, Any]


def _parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class PublishedAppPreviewBuildService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.runtime_service = PublishedAppDraftDevRuntimeService(db)

    @staticmethod
    def _preview_build_payload(metadata: object) -> dict[str, Any]:
        payload = metadata if isinstance(metadata, dict) else {}
        current = payload.get("preview_build") if isinstance(payload.get("preview_build"), dict) else {}
        return dict(current)

    @staticmethod
    def _current_payload(payload: dict[str, Any]) -> dict[str, Any]:
        current = payload.get("current")
        return dict(current) if isinstance(current, dict) else {}

    @classmethod
    def snapshot_from_workspace(cls, workspace: PublishedAppDraftWorkspace | None) -> PreviewBuildSnapshot | None:
        if workspace is None:
            return None
        payload = cls._preview_build_payload(getattr(workspace, "backend_metadata", None))
        current = cls._current_payload(payload)
        current_build_id = str(current.get("build_id") or "").strip()
        current_snapshot_root = str(current.get("snapshot_root") or "").strip()
        current_source_root = str(current.get("source_root") or "").strip()
        current_dist_root = str(current.get("dist_root") or "").strip()
        if current_build_id and current_snapshot_root and current_source_root and current_dist_root:
            return PreviewBuildSnapshot(
                build_id=current_build_id,
                build_seq=max(0, int(current.get("build_seq") or payload.get("build_seq") or 0)),
                built_at=_parse_datetime(current.get("built_at") or payload.get("built_at")),
                status="succeeded",
                last_error=None,
                snapshot_root=current_snapshot_root,
                source_root=current_source_root,
                dist_root=current_dist_root,
                source_bundle_hash=str(payload.get("source_bundle_hash") or "").strip() or None,
                entry_file=str(payload.get("entry_file") or "src/main.tsx").strip() or "src/main.tsx",
                dist_manifest=dict(payload.get("dist_manifest") or {}) if isinstance(payload.get("dist_manifest"), dict) else {},
            )

        build_id = str(payload.get("build_id") or "").strip()
        snapshot_root = str(payload.get("snapshot_root") or "").strip()
        source_root = str(payload.get("source_root") or "").strip()
        dist_root = str(payload.get("dist_root") or "").strip()
        if not build_id or not snapshot_root or not source_root or not dist_root:
            return None
        return PreviewBuildSnapshot(
            build_id=build_id,
            build_seq=max(0, int(payload.get("build_seq") or 0)),
            built_at=_parse_datetime(payload.get("built_at")),
            status=str(payload.get("status") or "").strip() or "unknown",
            last_error=str(payload.get("last_error") or "").strip() or None,
            snapshot_root=snapshot_root,
            source_root=source_root,
            dist_root=dist_root,
            source_bundle_hash=str(payload.get("source_bundle_hash") or "").strip() or None,
            entry_file=str(payload.get("entry_file") or "src/main.tsx").strip() or "src/main.tsx",
            dist_manifest=dict(payload.get("dist_manifest") or {}) if isinstance(payload.get("dist_manifest"), dict) else {},
        )

    async def _refresh_workspace_preview_state(self, *, workspace: PublishedAppDraftWorkspace) -> None:
        sandbox_id = str(getattr(workspace, "sandbox_id", "") or "").strip()
        if not sandbox_id:
            return
        refreshed = await self.runtime_service.client.heartbeat_session(
            sandbox_id=sandbox_id,
            idle_timeout_seconds=self.runtime_service.settings.idle_timeout_seconds,
        )
        refreshed_metadata = refreshed.get("backend_metadata")
        if not isinstance(refreshed_metadata, dict):
            return
        workspace.backend_metadata = self.runtime_service._merge_backend_metadata(
            existing_metadata=workspace.backend_metadata,
            refreshed_metadata=refreshed_metadata,
            preview_base_path=str(workspace.preview_url or "").strip() or "/",
        )
        await self.db.flush()

    async def get_current_build(
        self,
        *,
        app_id: UUID,
        refresh: bool = True,
    ) -> tuple[PublishedAppDraftWorkspace | None, PreviewBuildSnapshot | None]:
        workspace = await self.runtime_service.get_workspace(app_id=app_id)
        if workspace is not None and refresh:
            try:
                await self._refresh_workspace_preview_state(workspace=workspace)
            except Exception:
                logger.exception("preview_build_refresh_failed app_id=%s", app_id)
        return workspace, self.snapshot_from_workspace(workspace)

    async def find_revision_for_build(self, *, app_id: UUID, build_id: str) -> PublishedAppRevision | None:
        result = await self.db.execute(
            select(PublishedAppRevision)
            .where(PublishedAppRevision.published_app_id == app_id)
            .order_by(PublishedAppRevision.created_at.desc())
            .limit(100)
        )
        for revision in result.scalars().all():
            dist_manifest = revision.dist_manifest if isinstance(revision.dist_manifest, dict) else {}
            if str(dist_manifest.get("preview_build_id") or "").strip() == build_id:
                return revision
        return None

    async def materialize_revision_from_build(
        self,
        *,
        app: PublishedApp,
        workspace: PublishedAppDraftWorkspace,
        snapshot: PreviewBuildSnapshot,
        created_by: UUID | None,
        source_revision_id: UUID | None,
        origin_kind: str,
        origin_run_id: UUID | None = None,
        restored_from_revision_id: UUID | None = None,
    ) -> PublishedAppRevision:
        existing = await self.find_revision_for_build(app_id=app.id, build_id=snapshot.build_id)
        if existing is not None:
            return existing
        sandbox_id = str(workspace.sandbox_id or "").strip()
        if not sandbox_id:
            raise RuntimeError("Draft workspace sandbox is unavailable for preview build export")
        archive = await self.runtime_service.client.export_workspace_archive(
            sandbox_id=sandbox_id,
            workspace_path=snapshot.snapshot_root,
        )
        archive_base64 = str(archive.get("archive_base64") or "").strip()
        if not archive_base64:
            raise RuntimeError("Preview build export returned an empty archive payload")

        with tempfile.TemporaryDirectory(prefix=f"preview-build-{snapshot.build_id[:12]}-") as temp_dir:
            temp_root = Path(temp_dir)
            archive_path = temp_root / "snapshot.tar.gz"
            archive_path.write_bytes(base64.b64decode(archive_base64.encode("ascii")))
            extracted_root = temp_root / "snapshot"
            extracted_root.mkdir(parents=True, exist_ok=True)
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(extracted_root)

            source_dir = extracted_root / Path(snapshot.source_root).name
            dist_dir = extracted_root / Path(snapshot.dist_root).name
            state_path = extracted_root / "state.json"
            if not source_dir.exists():
                source_dir = extracted_root / "source"
            if not dist_dir.exists():
                dist_dir = extracted_root / "dist"
            if not source_dir.exists() or not dist_dir.exists():
                raise RuntimeError("Preview build snapshot archive is missing source or dist directories")

            files = self._read_text_files(source_dir)
            dist_manifest = dict(snapshot.dist_manifest or {})
            if state_path.exists():
                try:
                    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
                except Exception:
                    state_payload = None
                if isinstance(state_payload, dict) and isinstance(state_payload.get("dist_manifest"), dict):
                    dist_manifest = dict(state_payload.get("dist_manifest") or {})

            storage = PublishedAppBundleStorage.from_env()

            revision = await create_app_version(
                self.db,
                app=app,
                kind=PublishedAppRevisionKind.draft,
                template_key=app.template_key,
                entry_file=snapshot.entry_file,
                files=files,
                created_by=created_by,
                source_revision_id=source_revision_id,
                origin_kind=origin_kind,
                origin_run_id=origin_run_id,
                restored_from_revision_id=restored_from_revision_id,
                build_status=PublishedAppRevisionBuildStatus.succeeded,
                build_seq=max(0, int(snapshot.build_seq)),
                build_started_at=snapshot.built_at,
                build_finished_at=snapshot.built_at,
                template_runtime="vite_static",
            )

            dist_storage_prefix = PublishedAppBundleStorage.build_revision_dist_prefix(
                tenant_id=str(app.tenant_id),
                app_id=str(app.id),
                revision_id=str(revision.id),
            )
            uploaded = self._upload_dist_dir(
                storage=storage,
                dist_dir=dist_dir,
                dist_storage_prefix=dist_storage_prefix,
            )
            manifest_payload = dict(dist_manifest or {})
            manifest_payload["preview_build_id"] = snapshot.build_id
            manifest_payload["preview_build_seq"] = int(snapshot.build_seq)
            manifest_payload["preview_built_at"] = snapshot.built_at.isoformat() if snapshot.built_at else None
            manifest_payload["source_bundle_hash"] = snapshot.source_bundle_hash
            manifest_payload["uploaded_assets"] = uploaded

            revision.dist_storage_prefix = dist_storage_prefix
            revision.dist_manifest = manifest_payload
            revision.build_error = None
            revision.build_status = PublishedAppRevisionBuildStatus.succeeded
            revision.build_started_at = snapshot.built_at
            revision.build_finished_at = snapshot.built_at
            await self.db.flush()
            return revision

    async def finalize_waiting_runs_for_build(
        self,
        *,
        app: PublishedApp,
        workspace: PublishedAppDraftWorkspace,
        snapshot: PreviewBuildSnapshot,
    ) -> PublishedAppRevision | None:
        if snapshot.status != "succeeded":
            return None
        result = await self.db.execute(
            select(AgentRun)
            .where(
                and_(
                    AgentRun.surface == "published_app_coding_agent",
                    AgentRun.published_app_id == app.id,
                    AgentRun.status == RunStatus.completed,
                    AgentRun.result_revision_id.is_(None),
                )
            )
            .order_by(AgentRun.completed_at.asc(), AgentRun.created_at.asc())
        )
        waiting = [
            run for run in result.scalars().all()
            if self._run_waiting_for_build(run=run, build_seq=snapshot.build_seq)
        ]
        if not waiting:
            return None
        revision = await self.materialize_revision_from_build(
            app=app,
            workspace=workspace,
            snapshot=snapshot,
            created_by=waiting[-1].initiator_user_id or waiting[-1].user_id,
            source_revision_id=app.current_draft_revision_id,
            origin_kind="coding_run",
            origin_run_id=waiting[-1].id,
        )
        app.current_draft_revision_id = revision.id
        finalized_at = datetime.now(timezone.utc)
        for run in waiting:
            run.result_revision_id = revision.id
            run.batch_finalized_at = finalized_at
            context = self._run_context(run)
            context["awaiting_preview_build"] = False
            context["result_preview_build_id"] = snapshot.build_id
        await self.db.flush()
        return revision

    @staticmethod
    def _run_context(run: AgentRun) -> dict[str, Any]:
        input_params = dict(run.input_params) if isinstance(run.input_params, dict) else {}
        context = dict(input_params.get("context") or {}) if isinstance(input_params.get("context"), dict) else {}
        input_params["context"] = context
        run.input_params = input_params
        return context

    @classmethod
    def mark_run_waiting_for_build(cls, *, run: AgentRun, min_build_seq: int) -> None:
        context = cls._run_context(run)
        context["awaiting_preview_build"] = True
        context["awaiting_preview_build_min_seq"] = max(0, int(min_build_seq))
        context["awaiting_preview_build_marked_at"] = datetime.now(timezone.utc).isoformat()

    @classmethod
    def mark_run_waiting_for_next_build(cls, *, run: AgentRun, current_build_seq: int) -> None:
        cls.mark_run_waiting_for_build(run=run, min_build_seq=max(0, int(current_build_seq)) + 1)

    @classmethod
    def _run_waiting_for_build(cls, *, run: AgentRun, build_seq: int) -> bool:
        context = cls._run_context(run)
        if not bool(context.get("awaiting_preview_build")):
            return False
        return int(context.get("awaiting_preview_build_min_seq") or 0) <= int(build_seq)

    @staticmethod
    def _read_text_files(root: Path) -> Dict[str, str]:
        files: Dict[str, str] = {}
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel_path = path.relative_to(root).as_posix()
            files[rel_path] = path.read_text(encoding="utf-8", errors="replace")
        return files

    @staticmethod
    def _upload_dist_dir(
        *,
        storage: PublishedAppBundleStorage,
        dist_dir: Path,
        dist_storage_prefix: str,
    ) -> int:
        uploaded = 0
        for file_path in sorted(dist_dir.rglob("*")):
            if not file_path.is_file():
                continue
            relative_path = file_path.relative_to(dist_dir).as_posix()
            cache_control = "public, max-age=31536000, immutable"
            if relative_path.endswith(".html"):
                cache_control = "no-store"
            storage.write_asset_bytes(
                dist_storage_prefix=dist_storage_prefix,
                asset_path=relative_path,
                payload=file_path.read_bytes(),
                content_type=mimetypes.guess_type(file_path.name)[0] or "application/octet-stream",
                cache_control=cache_control,
            )
            uploaded += 1
        return uploaded
