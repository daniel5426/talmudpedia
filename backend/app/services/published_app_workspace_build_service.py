from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import mimetypes
import os
import tarfile
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppDraftWorkspace,
    PublishedAppRevision,
    PublishedAppWorkspaceBuild,
    PublishedAppWorkspaceBuildStatus,
)
from app.services.apps_builder_trace import apps_builder_trace
from app.services.apps_builder_dependency_policy import validate_builder_dependency_policy
from app.services.published_app_builder_snapshot_filter import filter_and_validate_builder_snapshot_files
from app.services.published_app_bundle_storage import PublishedAppBundleStorage
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService
from app.services.published_app_live_preview import build_canonical_workspace_fingerprint
from app.services.published_app_templates import TemplateRuntimeContext, apply_runtime_bootstrap_overlay
from app.services.published_app_draft_dev_runtime_client import PublishedAppDraftDevRuntimeClientError

logger = logging.getLogger(__name__)


class PublishedAppWorkspaceBuildError(Exception):
    pass


@dataclass(frozen=True)
class ReadyWorkspaceBuildResult:
    build: PublishedAppWorkspaceBuild
    source_files: Dict[str, str]
    build_files: Dict[str, str]
    source_fingerprint: str
    workspace_revision_token: str | None
    reused: bool


class PublishedAppWorkspaceBuildService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.runtime_service = PublishedAppDraftDevRuntimeService(db)

    @staticmethod
    def _trace(event: str, *, app_id: UUID, **fields: Any) -> None:
        apps_builder_trace(
            event,
            domain="workspace_build.cache",
            app_id=str(app_id),
            **fields,
        )

    @staticmethod
    def _app_lock_key(*, app_id: UUID) -> int:
        digest = hashlib.sha256(f"workspace-build:{app_id}".encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF

    @staticmethod
    def _stale_build_timeout_seconds() -> float:
        raw = (os.getenv("APPS_WORKSPACE_BUILD_STALE_TIMEOUT_SECONDS") or "").strip()
        try:
            value = float(raw) if raw else 900.0
        except Exception:
            value = 900.0
        return max(60.0, value)

    @staticmethod
    def _watcher_wait_timeout_seconds() -> float:
        raw = (os.getenv("APPS_WORKSPACE_BUILD_WATCHER_WAIT_TIMEOUT_SECONDS") or "").strip()
        try:
            value = float(raw) if raw else 30.0
        except Exception:
            value = 30.0
        return max(3.0, value)

    @staticmethod
    def _watcher_poll_interval_seconds() -> float:
        raw = (os.getenv("APPS_WORKSPACE_BUILD_WATCHER_POLL_INTERVAL_SECONDS") or "").strip()
        try:
            value = float(raw) if raw else 0.5
        except Exception:
            value = 0.5
        return max(0.1, value)

    @staticmethod
    def _dist_export_timeout_seconds() -> float:
        raw = (os.getenv("APPS_WORKSPACE_BUILD_DIST_EXPORT_TIMEOUT_SECONDS") or "").strip()
        try:
            value = float(raw) if raw else 75.0
        except Exception:
            value = 75.0
        return max(5.0, value)

    @staticmethod
    def _dist_upload_timeout_seconds() -> float:
        raw = (os.getenv("APPS_WORKSPACE_BUILD_DIST_UPLOAD_TIMEOUT_SECONDS") or "").strip()
        try:
            value = float(raw) if raw else 75.0
        except Exception:
            value = 75.0
        return max(5.0, value)

    @staticmethod
    def _duration_ms(started_at: float) -> int:
        return max(0, int((time.monotonic() - started_at) * 1000))

    @classmethod
    def _is_stale_build(cls, build: PublishedAppWorkspaceBuild) -> bool:
        started_at = build.build_started_at
        if not isinstance(started_at, datetime):
            return True
        return (datetime.now(timezone.utc) - started_at).total_seconds() >= cls._stale_build_timeout_seconds()

    async def _acquire_app_lock(self, *, app_id: UUID) -> None:
        bind = self.db.get_bind()
        dialect_name = str(getattr(getattr(bind, "dialect", None), "name", "") or "").lower()
        if dialect_name == "sqlite":
            self._trace("build.lock.skipped", app_id=app_id, reason="sqlite")
            return
        self._trace("build.lock.begin", app_id=app_id, dialect=dialect_name)
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": int(self._app_lock_key(app_id=app_id))},
        )
        self._trace("build.lock.acquired", app_id=app_id, dialect=dialect_name)

    @staticmethod
    def _build_source_fingerprint(
        *,
        entry_file: str,
        files: Dict[str, str],
        runtime_context: TemplateRuntimeContext | Dict[str, Any] | None = None,
    ) -> str:
        return build_canonical_workspace_fingerprint(
            entry_file=entry_file,
            files=files,
            runtime_context=runtime_context,
        )

    @staticmethod
    def _live_preview_matches_workspace_state(
        *,
        live_preview_metadata: Dict[str, Any],
        workspace_fingerprint: str,
        workspace_revision_token: str | None,
    ) -> tuple[bool, str | None]:
        live_preview_status = str(live_preview_metadata.get("status") or "").strip().lower()
        live_preview_dist_path = str(live_preview_metadata.get("dist_path") or "").strip()
        if live_preview_status != "ready" or not live_preview_dist_path:
            return False, None
        live_preview_fingerprint = str(live_preview_metadata.get("workspace_fingerprint") or "").strip()
        if live_preview_fingerprint and live_preview_fingerprint == workspace_fingerprint:
            return True, "fingerprint"
        live_preview_revision_token = str(live_preview_metadata.get("debug_last_trigger_revision_token") or "").strip()
        normalized_revision_token = str(workspace_revision_token or "").strip()
        if normalized_revision_token and live_preview_revision_token == normalized_revision_token:
            return True, "revision_token"
        return False, None

    @staticmethod
    def _build_dist_manifest(dist_dir: Path) -> Dict[str, Any]:
        assets: list[dict[str, Any]] = []
        entry_html = "index.html"
        for file_path in sorted(dist_dir.rglob("*")):
            if not file_path.is_file():
                continue
            relative = file_path.relative_to(dist_dir).as_posix()
            if relative == "index.html":
                entry_html = "index.html"
            assets.append(
                {
                    "path": relative,
                    "size": int(file_path.stat().st_size),
                    "content_type": mimetypes.guess_type(file_path.name)[0] or "application/octet-stream",
                }
            )
        return {
            "entry_html": entry_html,
            "assets": assets,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _normalize_extracted_dist_root(extract_dir: Path) -> Path:
        dot_dir = extract_dir / "."
        if dot_dir.exists() and dot_dir.is_dir() and (dot_dir / "index.html").exists():
            return dot_dir
        return extract_dir

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

    async def _resolve_workspace(self, *, app_id: UUID) -> PublishedAppDraftWorkspace:
        workspace = await self.runtime_service.get_workspace(app_id=app_id)
        if workspace is None or not str(workspace.sandbox_id or "").strip():
            raise PublishedAppWorkspaceBuildError("Draft workspace is unavailable for build materialization.")
        return workspace

    async def _get_ready_build(
        self,
        *,
        app_id: UUID,
        workspace_fingerprint: str,
    ) -> PublishedAppWorkspaceBuild | None:
        self._trace(
            "build.lookup_ready.begin",
            app_id=app_id,
            workspace_fingerprint=workspace_fingerprint,
        )
        result = await self.db.execute(
            select(PublishedAppWorkspaceBuild)
            .where(
                PublishedAppWorkspaceBuild.published_app_id == app_id,
                PublishedAppWorkspaceBuild.workspace_fingerprint == workspace_fingerprint,
                PublishedAppWorkspaceBuild.status == PublishedAppWorkspaceBuildStatus.ready,
            )
            .limit(1)
        )
        build = result.scalar_one_or_none()
        self._trace(
            "build.lookup_ready.done",
            app_id=app_id,
            workspace_fingerprint=workspace_fingerprint,
            found=bool(build is not None),
            workspace_build_id=str(build.id) if build is not None else None,
            status=str(build.status.value if hasattr(build.status, "value") else build.status) if build is not None else None,
        )
        return build

    async def _get_or_create_build(
        self,
        *,
        app: PublishedApp,
        workspace_fingerprint: str,
    ) -> PublishedAppWorkspaceBuild:
        self._trace(
            "build.get_or_create.begin",
            app_id=app.id,
            workspace_fingerprint=workspace_fingerprint,
        )
        result = await self.db.execute(
            select(PublishedAppWorkspaceBuild)
            .where(
                PublishedAppWorkspaceBuild.published_app_id == app.id,
                PublishedAppWorkspaceBuild.workspace_fingerprint == workspace_fingerprint,
            )
            .limit(1)
        )
        build = result.scalar_one_or_none()
        if build is not None:
            self._trace(
                "build.get_or_create.reused",
                app_id=app.id,
                workspace_fingerprint=workspace_fingerprint,
                workspace_build_id=str(build.id),
                status=str(build.status.value if hasattr(build.status, "value") else build.status),
            )
            return build
        build = PublishedAppWorkspaceBuild(
            published_app_id=app.id,
            workspace_fingerprint=workspace_fingerprint,
            status=PublishedAppWorkspaceBuildStatus.queued,
            entry_file="src/main.tsx",
            source_snapshot={},
            template_runtime="vite_static",
        )
        self.db.add(build)
        self._trace(
            "build.get_or_create.flush_begin",
            app_id=app.id,
            workspace_fingerprint=workspace_fingerprint,
            workspace_build_id=str(build.id),
        )
        await self.db.flush()
        self._trace(
            "build.get_or_create.flush_done",
            app_id=app.id,
            workspace_fingerprint=workspace_fingerprint,
            workspace_build_id=str(build.id),
            status=str(build.status.value if hasattr(build.status, "value") else build.status),
        )
        return build

    async def _get_build_by_id(self, *, build_id: UUID) -> PublishedAppWorkspaceBuild | None:
        return await self.db.get(PublishedAppWorkspaceBuild, build_id)

    async def _wait_for_existing_build_result(
        self,
        *,
        app_id: UUID,
        build_id: UUID,
        workspace_fingerprint: str,
    ) -> PublishedAppWorkspaceBuild:
        deadline = asyncio.get_running_loop().time() + self._watcher_wait_timeout_seconds()
        poll_seconds = self._watcher_poll_interval_seconds()
        while True:
            await self.db.rollback()
            build = await self._get_build_by_id(build_id=build_id)
            if build is None:
                raise PublishedAppWorkspaceBuildError("Workspace build row disappeared during watcher materialization.")
            if (
                build.status == PublishedAppWorkspaceBuildStatus.ready
                and str(build.dist_storage_prefix or "").strip()
            ):
                return build
            if build.status == PublishedAppWorkspaceBuildStatus.failed:
                raise PublishedAppWorkspaceBuildError(
                    str(build.build_error or "Workspace watcher materialization failed.")
                )
            if asyncio.get_running_loop().time() >= deadline:
                raise PublishedAppWorkspaceBuildError(
                    "Timed out waiting for watcher-owned workspace materialization to finish."
                )
            self._trace(
                "build.wait_existing.pending",
                app_id=app_id,
                workspace_build_id=str(build_id),
                workspace_fingerprint=workspace_fingerprint,
                status=str(build.status.value if hasattr(build.status, "value") else build.status),
            )
            await asyncio.sleep(poll_seconds)

    async def _refresh_workspace_live_preview(
        self,
        *,
        workspace: PublishedAppDraftWorkspace,
    ) -> Dict[str, Any]:
        backend_metadata = dict(workspace.backend_metadata or {}) if isinstance(workspace.backend_metadata, dict) else {}
        live_preview = (
            dict(backend_metadata.get("live_preview") or {})
            if isinstance(backend_metadata.get("live_preview"), dict)
            else {}
        )
        sandbox_id = str(workspace.sandbox_id or "").strip()
        if not sandbox_id:
            return live_preview
        try:
            heartbeat_result = await self.runtime_service.client.heartbeat_session(
                sandbox_id=sandbox_id,
                idle_timeout_seconds=self.runtime_service.settings.idle_timeout_seconds,
            )
        except PublishedAppDraftDevRuntimeClientError as exc:
            self._trace(
                "build.watcher_refresh.failed",
                app_id=workspace.published_app_id,
                workspace_id=str(workspace.id),
                sandbox_id=sandbox_id,
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            return live_preview

        refreshed_metadata = (
            dict(heartbeat_result.get("backend_metadata") or {})
            if isinstance(heartbeat_result.get("backend_metadata"), dict)
            else {}
        )
        workspace.runtime_backend = str(
            heartbeat_result.get("runtime_backend") or workspace.runtime_backend or self.runtime_service.client.backend_name
        )
        if refreshed_metadata:
            workspace.backend_metadata = self.runtime_service._merge_backend_metadata(
                existing_metadata=workspace.backend_metadata,
                refreshed_metadata=refreshed_metadata,
                preview_base_path=str(workspace.preview_url or "").strip() or "/",
            )
        merged_metadata = dict(workspace.backend_metadata or {}) if isinstance(workspace.backend_metadata, dict) else {}
        return (
            dict(merged_metadata.get("live_preview") or {})
            if isinstance(merged_metadata.get("live_preview"), dict)
            else {}
        )

    async def _wait_for_matching_watcher_build(
        self,
        *,
        workspace: PublishedAppDraftWorkspace,
        app_id: UUID,
        workspace_fingerprint: str,
        workspace_revision_token: str | None,
    ) -> tuple[Dict[str, Any], str]:
        deadline = asyncio.get_running_loop().time() + self._watcher_wait_timeout_seconds()
        poll_seconds = self._watcher_poll_interval_seconds()
        last_status = "unknown"
        while True:
            live_preview_metadata = await self._refresh_workspace_live_preview(workspace=workspace)
            last_status = str(live_preview_metadata.get("status") or "").strip().lower() or last_status
            matched, match_mode = self._live_preview_matches_workspace_state(
                live_preview_metadata=live_preview_metadata,
                workspace_fingerprint=workspace_fingerprint,
                workspace_revision_token=workspace_revision_token,
            )
            if matched:
                return live_preview_metadata, str(match_mode or "unknown")
            if asyncio.get_running_loop().time() >= deadline:
                raise PublishedAppWorkspaceBuildError(
                    "Timed out waiting for a watcher-ready build that matches the current workspace state."
                )
            self._trace(
                "build.wait_watcher.pending",
                app_id=app_id,
                workspace_id=str(workspace.id),
                workspace_fingerprint=workspace_fingerprint,
                workspace_revision_token=str(workspace_revision_token or "") or None,
                live_preview_status=last_status,
                live_preview_fingerprint=str(live_preview_metadata.get("workspace_fingerprint") or "").strip() or None,
                live_preview_revision_token=str(
                    live_preview_metadata.get("debug_last_trigger_revision_token") or ""
                ).strip()
                or None,
            )
            await asyncio.sleep(poll_seconds)

    async def _promote_live_preview_dist(
        self,
        *,
        app: PublishedApp,
        build: PublishedAppWorkspaceBuild,
        source_fingerprint: str,
        workspace_revision_token: str | None,
        live_preview_metadata: Dict[str, Any],
    ) -> None:
        live_preview_dist_path = str(live_preview_metadata.get("dist_path") or "").strip()
        sandbox_id = str(build.source_snapshot.get("sandbox_id") or "").strip()
        if not sandbox_id:
            workspace = await self._resolve_workspace(app_id=app.id)
            sandbox_id = str(workspace.sandbox_id or "").strip()
        if not live_preview_dist_path:
            raise PublishedAppWorkspaceBuildError("Watcher-ready build is missing a dist path.")
        self._trace(
            "build.promote_watcher.export_begin",
            app_id=app.id,
            workspace_build_id=str(build.id),
            sandbox_id=sandbox_id,
            live_preview_dist_path=live_preview_dist_path,
            live_preview_build_id=str(live_preview_metadata.get("last_successful_build_id") or "").strip() or None,
            timeout_seconds=self._dist_export_timeout_seconds(),
        )
        export_started_at = time.monotonic()
        try:
            archive_response = await asyncio.wait_for(
                self.runtime_service.client.export_workspace_archive(
                    sandbox_id=sandbox_id,
                    workspace_path=live_preview_dist_path,
                    format="tar.gz",
                ),
                timeout=self._dist_export_timeout_seconds(),
            )
        except asyncio.TimeoutError as exc:
            self._trace(
                "build.promote_watcher.export_timeout",
                app_id=app.id,
                workspace_build_id=str(build.id),
                sandbox_id=sandbox_id,
                live_preview_dist_path=live_preview_dist_path,
                duration_ms=self._duration_ms(export_started_at),
            )
            raise PublishedAppWorkspaceBuildError("Timed out exporting watcher-ready dist from preview sandbox.") from exc
        self._trace(
            "build.promote_watcher.export_done",
            app_id=app.id,
            workspace_build_id=str(build.id),
            sandbox_id=sandbox_id,
            live_preview_dist_path=live_preview_dist_path,
            duration_ms=self._duration_ms(export_started_at),
            archive_base64_bytes=len(str(archive_response.get("archive_base64") or "").encode("utf-8"))
            if isinstance(archive_response, dict)
            else None,
        )

        decode_started_at = time.monotonic()
        archive_bytes = self.runtime_service.client.decode_archive_payload(archive_response)
        self._trace(
            "build.promote_watcher.decode_done",
            app_id=app.id,
            workspace_build_id=str(build.id),
            duration_ms=self._duration_ms(decode_started_at),
            archive_bytes=len(archive_bytes),
        )
        with tempfile.TemporaryDirectory(prefix=f"apps-live-preview-{str(app.id)[:8]}-") as temp_dir:
            extract_dir = Path(temp_dir) / "dist"
            extract_dir.mkdir(parents=True, exist_ok=True)
            archive_path = Path(temp_dir) / "dist.tar.gz"
            archive_path.write_bytes(archive_bytes)
            extract_started_at = time.monotonic()
            with tarfile.open(archive_path, mode="r:gz") as tar:
                tar.extractall(path=extract_dir)
            dist_root = self._normalize_extracted_dist_root(extract_dir)
            if not dist_root.exists() or not dist_root.is_dir():
                raise PublishedAppWorkspaceBuildError("Watcher-ready dist directory is unavailable.")
            self._trace(
                "build.promote_watcher.extract_done",
                app_id=app.id,
                workspace_build_id=str(build.id),
                duration_ms=self._duration_ms(extract_started_at),
            )
            dist_manifest = self._build_dist_manifest(dist_root)
            dist_manifest["source_fingerprint"] = source_fingerprint
            dist_manifest["workspace_revision_token"] = workspace_revision_token
            dist_manifest["live_preview_build_id"] = str(
                live_preview_metadata.get("last_successful_build_id") or ""
            ).strip() or None
            storage = PublishedAppBundleStorage.from_env()
            dist_storage_prefix = PublishedAppBundleStorage.build_workspace_build_dist_prefix(
                organization_id=str(app.organization_id),
                app_id=str(app.id),
                workspace_build_id=str(build.id),
            )
            upload_started_at = time.monotonic()
            asset_count = len(dist_manifest.get("assets") or [])
            self._trace(
                "build.promote_watcher.upload_begin",
                app_id=app.id,
                workspace_build_id=str(build.id),
                dist_storage_prefix=dist_storage_prefix,
                asset_count=asset_count,
                timeout_seconds=self._dist_upload_timeout_seconds(),
            )
            try:
                uploaded_assets = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._upload_dist_dir,
                        storage=storage,
                        dist_dir=dist_root,
                        dist_storage_prefix=dist_storage_prefix,
                    ),
                    timeout=self._dist_upload_timeout_seconds(),
                )
            except asyncio.TimeoutError as exc:
                self._trace(
                    "build.promote_watcher.upload_timeout",
                    app_id=app.id,
                    workspace_build_id=str(build.id),
                    dist_storage_prefix=dist_storage_prefix,
                    asset_count=asset_count,
                    duration_ms=self._duration_ms(upload_started_at),
                )
                raise PublishedAppWorkspaceBuildError("Timed out uploading watcher-ready dist artifacts.") from exc
            dist_manifest["uploaded_assets"] = uploaded_assets
            self._trace(
                "build.promote_watcher.upload_done",
                app_id=app.id,
                workspace_build_id=str(build.id),
                dist_storage_prefix=dist_storage_prefix,
                asset_count=asset_count,
                uploaded_assets=uploaded_assets,
                duration_ms=self._duration_ms(upload_started_at),
            )
            build.dist_storage_prefix = dist_storage_prefix
            build.dist_manifest = dist_manifest

    async def ensure_ready_build(
        self,
        *,
        app: PublishedApp,
        entry_file: str,
        source_revision_id: UUID | None,
        created_by: UUID | None,
        origin_kind: str,
        origin_run_id: UUID | None = None,
    ) -> ReadyWorkspaceBuildResult:
        app_id = app.id
        self._trace(
            "build.ensure_ready.begin",
            app_id=app_id,
            source_revision_id=str(source_revision_id or "") or None,
            origin_kind=origin_kind,
            origin_run_id=str(origin_run_id or "") or None,
            created_by=str(created_by or "") or None,
        )
        try:
            workspace = await self._resolve_workspace(app_id=app.id)
            sandbox_id = str(workspace.sandbox_id or "").strip()
            runtime_context = TemplateRuntimeContext(
                app_id=str(app.id),
                app_public_id=str(app.public_id or ""),
                agent_id=str(app.agent_id or ""),
            )
            normalized_entry_file = str(entry_file or "").strip() or "src/main.tsx"

            self._trace("build.snapshot.begin", app_id=app.id, sandbox_id=sandbox_id)
            snapshot = await self.runtime_service.client.snapshot_workspace(
                sandbox_id=sandbox_id,
                workspace="live",
            )
            raw_files = {
                str(path): str(content if isinstance(content, str) else str(content))
                for path, content in dict(snapshot.get("files") or {}).items()
            }
            source_files = filter_and_validate_builder_snapshot_files(raw_files)
            workspace_revision_token = str(snapshot.get("revision_token") or "").strip() or None
            dependency_hash = self.runtime_service._dependency_hash(source_files)
            build_files = apply_runtime_bootstrap_overlay(dict(source_files), runtime_context=runtime_context)
            diagnostics = validate_builder_dependency_policy(build_files)
            if diagnostics:
                raise PublishedAppWorkspaceBuildError(
                    "; ".join(item.get("message", "Build policy violation") for item in diagnostics)
                )

            source_fingerprint = self._build_source_fingerprint(
                entry_file=normalized_entry_file,
                files=source_files,
                runtime_context=runtime_context,
            )
            await self.runtime_service.record_workspace_live_snapshot(
                app_id=app.id,
                revision_id=source_revision_id,
                entry_file=normalized_entry_file,
                files=source_files,
                revision_token=workspace_revision_token,
                workspace_fingerprint=source_fingerprint,
            )
            self._trace(
                "build.snapshot.done",
                app_id=app.id,
                sandbox_id=sandbox_id,
                workspace_revision_token=str(workspace_revision_token or ""),
                workspace_fingerprint=source_fingerprint,
                file_count=len(source_files),
            )

            existing_ready = await self._get_ready_build(app_id=app.id, workspace_fingerprint=source_fingerprint)
            if existing_ready is not None and str(existing_ready.dist_storage_prefix or "").strip():
                self._trace(
                    "build.reused",
                    app_id=app.id,
                    workspace_build_id=str(existing_ready.id),
                    workspace_fingerprint=source_fingerprint,
                )
                return ReadyWorkspaceBuildResult(
                    build=existing_ready,
                    source_files=source_files,
                    build_files=build_files,
                    source_fingerprint=source_fingerprint,
                    workspace_revision_token=workspace_revision_token,
                    reused=True,
                )

            await self._acquire_app_lock(app_id=app.id)
            build = await self._get_or_create_build(app=app, workspace_fingerprint=source_fingerprint)
            if (
                build.status == PublishedAppWorkspaceBuildStatus.ready
                and str(build.dist_storage_prefix or "").strip()
            ):
                self._trace(
                    "build.reused_after_lock",
                    app_id=app.id,
                    workspace_build_id=str(build.id),
                    workspace_fingerprint=source_fingerprint,
                )
                return ReadyWorkspaceBuildResult(
                    build=build,
                    source_files=source_files,
                    build_files=build_files,
                    source_fingerprint=source_fingerprint,
                    workspace_revision_token=workspace_revision_token,
                    reused=True,
                )
            if build.status == PublishedAppWorkspaceBuildStatus.building:
                if not self._is_stale_build(build):
                    live_preview_metadata = await self._refresh_workspace_live_preview(workspace=workspace)
                    live_preview_matched, live_preview_match_mode = self._live_preview_matches_workspace_state(
                        live_preview_metadata=live_preview_metadata,
                        workspace_fingerprint=source_fingerprint,
                        workspace_revision_token=workspace_revision_token,
                    )
                    if live_preview_matched:
                        self._trace(
                            "build.reclaim_active_from_ready_watcher",
                            app_id=app.id,
                            workspace_build_id=str(build.id),
                            workspace_fingerprint=source_fingerprint,
                            match_mode=live_preview_match_mode,
                            live_preview_build_id=str(
                                live_preview_metadata.get("last_successful_build_id") or ""
                            ).strip()
                            or None,
                        )
                    else:
                        waited_build = await self._wait_for_existing_build_result(
                            app_id=app.id,
                            build_id=build.id,
                            workspace_fingerprint=source_fingerprint,
                        )
                        return ReadyWorkspaceBuildResult(
                            build=waited_build,
                            source_files=source_files,
                            build_files=build_files,
                            source_fingerprint=source_fingerprint,
                            workspace_revision_token=workspace_revision_token,
                            reused=True,
                        )
                else:
                    self._trace(
                        "build.reclaim_stale",
                        app_id=app.id,
                        workspace_build_id=str(build.id),
                        workspace_fingerprint=source_fingerprint,
                        previous_started_at=build.build_started_at.isoformat()
                        if isinstance(build.build_started_at, datetime)
                        else None,
                    )
            else:
                live_preview_metadata = None
                live_preview_match_mode = None
            self._trace(
                "build.row_update.begin",
                app_id=app.id,
                workspace_build_id=str(build.id),
                current_status=str(build.status.value if hasattr(build.status, "value") else build.status),
            )
            build.status = PublishedAppWorkspaceBuildStatus.building
            build.entry_file = normalized_entry_file
            build.source_snapshot = {
                "files": source_files,
                "entry_file": normalized_entry_file,
                "workspace_revision_token": workspace_revision_token,
                "workspace_fingerprint": source_fingerprint,
                "sandbox_id": sandbox_id,
            }
            build.dependency_hash = dependency_hash
            build.source_revision_id = source_revision_id
            build.origin_kind = str(origin_kind or "unknown").strip() or "unknown"
            build.origin_run_id = origin_run_id
            build.created_by = created_by
            build.build_error = None
            build.build_started_at = datetime.now(timezone.utc)
            build.build_finished_at = None
            self._trace(
                "build.row_update.flush_begin",
                app_id=app.id,
                workspace_build_id=str(build.id),
                workspace_fingerprint=source_fingerprint,
            )
            await self.db.flush()
            self._trace(
                "build.row_update.flush_done",
                app_id=app.id,
                workspace_build_id=str(build.id),
                workspace_fingerprint=source_fingerprint,
                status=str(build.status.value if hasattr(build.status, "value") else build.status),
            )
            self._trace(
                "build.row_update.commit_begin",
                app_id=app.id,
                workspace_build_id=str(build.id),
                workspace_fingerprint=source_fingerprint,
            )
            await self.db.commit()
            self._trace(
                "build.row_update.commit_done",
                app_id=app.id,
                workspace_build_id=str(build.id),
                workspace_fingerprint=source_fingerprint,
            )

            if live_preview_metadata is None:
                live_preview_metadata, live_preview_match_mode = await self._wait_for_matching_watcher_build(
                    workspace=workspace,
                    app_id=app.id,
                    workspace_fingerprint=source_fingerprint,
                    workspace_revision_token=workspace_revision_token,
                )
            self._trace(
                "build.promote_watcher.begin",
                app_id=app.id,
                workspace_build_id=str(build.id),
                workspace_fingerprint=source_fingerprint,
                match_mode=live_preview_match_mode,
                live_preview_build_id=str(live_preview_metadata.get("last_successful_build_id") or "").strip() or None,
            )
            await self._promote_live_preview_dist(
                app=app,
                build=build,
                source_fingerprint=source_fingerprint,
                workspace_revision_token=workspace_revision_token,
                live_preview_metadata=live_preview_metadata,
            )
            build.build_finished_at = datetime.now(timezone.utc)
            build.status = PublishedAppWorkspaceBuildStatus.ready
            build.template_runtime = "vite_static"
            self._trace(
                "build.ready.flush_begin",
                app_id=app.id,
                workspace_build_id=str(build.id),
                workspace_fingerprint=source_fingerprint,
            )
            await self.db.flush()
            self._trace(
                "build.ready.flush_done",
                app_id=app.id,
                workspace_build_id=str(build.id),
                workspace_fingerprint=source_fingerprint,
            )
            self._trace(
                "build.ready.commit_begin",
                app_id=app.id,
                workspace_build_id=str(build.id),
                workspace_fingerprint=source_fingerprint,
            )
            await self.db.commit()
            self._trace(
                "build.ready.commit_done",
                app_id=app.id,
                workspace_build_id=str(build.id),
                workspace_fingerprint=source_fingerprint,
            )
        except Exception as exc:
            build_id = str(build.id) if "build" in locals() and getattr(build, "id", None) is not None else None
            self._trace(
                "build.exception",
                app_id=app_id,
                workspace_build_id=build_id,
                workspace_fingerprint=locals().get("source_fingerprint"),
                error=str(exc),
                error_type=exc.__class__.__name__,
                phase="ensure_ready_build",
            )
            if "build" in locals():
                build.status = PublishedAppWorkspaceBuildStatus.failed
                build.build_error = str(exc)
                build.build_finished_at = datetime.now(timezone.utc)
                self._trace(
                    "build.failed.flush_begin",
                    app_id=app_id,
                    workspace_build_id=build_id,
                    workspace_fingerprint=locals().get("source_fingerprint"),
                )
                await self.db.flush()
                self._trace(
                    "build.failed.flush_done",
                    app_id=app_id,
                    workspace_build_id=build_id,
                    workspace_fingerprint=locals().get("source_fingerprint"),
                )
                self._trace(
                    "build.failed.commit_begin",
                    app_id=app_id,
                    workspace_build_id=build_id,
                    workspace_fingerprint=locals().get("source_fingerprint"),
                )
                await self.db.commit()
                self._trace(
                    "build.failed.commit_done",
                    app_id=app_id,
                    workspace_build_id=build_id,
                    workspace_fingerprint=locals().get("source_fingerprint"),
                )
            self._trace(
                "build.failed",
                app_id=app_id,
                workspace_build_id=build_id,
                workspace_fingerprint=locals().get("source_fingerprint"),
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            raise PublishedAppWorkspaceBuildError(str(exc)) from exc

        self._trace(
            "build.ready",
            app_id=app.id,
            workspace_build_id=str(build.id),
            workspace_fingerprint=source_fingerprint,
            reused=False,
        )
        return ReadyWorkspaceBuildResult(
            build=build,
            source_files=source_files,
            build_files=build_files,
            source_fingerprint=source_fingerprint,
            workspace_revision_token=workspace_revision_token,
            reused=False,
        )
