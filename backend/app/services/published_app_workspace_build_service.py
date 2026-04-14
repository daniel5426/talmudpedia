from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import tarfile
import tempfile
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
from app.services.published_app_templates import TemplateRuntimeContext, apply_runtime_bootstrap_overlay

logger = logging.getLogger(__name__)

_NPM_INSTALL_COMMAND = ["npm", "install", "--no-audit", "--no-fund"]
_NPM_CI_COMMAND = ["npm", "ci"]


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
    def _resolve_install_command(files: Dict[str, str]) -> list[str]:
        if isinstance(files.get("package-lock.json"), str):
            return list(_NPM_CI_COMMAND)
        return list(_NPM_INSTALL_COMMAND)

    @staticmethod
    def _extract_exit_code(result: Dict[str, Any], *, command_name: str) -> int:
        raw_code = result.get("code", result.get("exit_code"))
        try:
            return int(raw_code)
        except Exception as exc:
            raise PublishedAppWorkspaceBuildError(
                f"{command_name} result has invalid exit code: {raw_code!r}"
            ) from exc

    @classmethod
    def _assert_command_success(cls, *, result: Dict[str, Any], command_name: str) -> None:
        code = cls._extract_exit_code(result, command_name=command_name)
        if code == 0:
            return
        stdout = str(result.get("stdout") or result.get("output") or "").strip()
        stderr = str(result.get("stderr") or "").strip()
        detail = stderr or stdout or "Command failed"
        raise PublishedAppWorkspaceBuildError(f"`{command_name}` failed with exit code {code}\n{detail}")

    @staticmethod
    def _build_source_fingerprint(*, entry_file: str, files: Dict[str, str]) -> str:
        payload = {
            "entry_file": str(entry_file or "").strip() or "src/main.tsx",
            "files": {path: files[path] for path in sorted(files)},
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

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
        self._trace(
            "build.ensure_ready.begin",
            app_id=app.id,
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
                app_slug=str(app.slug or ""),
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

            source_fingerprint = self._build_source_fingerprint(entry_file=normalized_entry_file, files=build_files)
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
                    raise PublishedAppWorkspaceBuildError(
                        "Workspace build already in progress for this workspace state."
                    )
                self._trace(
                    "build.reclaim_stale",
                    app_id=app.id,
                    workspace_build_id=str(build.id),
                    workspace_fingerprint=source_fingerprint,
                    previous_started_at=build.build_started_at.isoformat()
                    if isinstance(build.build_started_at, datetime)
                    else None,
                )
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

            live_workspace_path = str(
                snapshot.get("workspace_path")
                or workspace.live_workspace_path
                or ""
            ).strip()
            if not live_workspace_path:
                raise PublishedAppWorkspaceBuildError("Live workspace path is unavailable.")

            dependency_prepare = await self.runtime_service.client.prepare_publish_dependencies(
                sandbox_id=sandbox_id,
                workspace_path=live_workspace_path,
            )
            dependency_status = str(dependency_prepare.get("status") or "").strip().lower()
            self._trace(
                "build.dependencies.done",
                app_id=app.id,
                workspace_build_id=str(build.id),
                dependency_status=dependency_status,
            )
            if dependency_status not in {"reused", "prepared"}:
                install_command = self._resolve_install_command(build_files)
                install_result = await self.runtime_service.client.run_command(
                    sandbox_id=sandbox_id,
                    command=install_command,
                    timeout_seconds=int(os.getenv("APPS_BUILD_NPM_INSTALL_TIMEOUT_SECONDS", "360")),
                    max_output_bytes=int(os.getenv("APPS_PUBLISH_SANDBOX_MAX_OUTPUT_BYTES", "30000")),
                    workspace_path=live_workspace_path,
                )
                self._assert_command_success(result=install_result, command_name=" ".join(install_command))

            build_root = f"{live_workspace_path.rstrip('/')}/.talmudpedia/materialized-build/{build.id}"
            dist_workspace = f"{build_root}/dist"
            self._trace(
                "build.prepare_dir.begin",
                app_id=app.id,
                workspace_build_id=str(build.id),
                build_root=build_root,
            )
            prepare_build_dir = await self.runtime_service.client.run_command(
                sandbox_id=sandbox_id,
                command=["bash", "-lc", f"rm -rf {json.dumps(build_root)} && mkdir -p {json.dumps(build_root)}"],
                timeout_seconds=60,
                max_output_bytes=8000,
                workspace_path=live_workspace_path,
            )
            self._assert_command_success(result=prepare_build_dir, command_name="prepare workspace build dir")
            self._trace(
                "build.prepare_dir.done",
                app_id=app.id,
                workspace_build_id=str(build.id),
                build_root=build_root,
            )

            self._trace(
                "build.run.begin",
                app_id=app.id,
                workspace_build_id=str(build.id),
                dist_workspace=dist_workspace,
            )
            build_result = await self.runtime_service.client.run_command(
                sandbox_id=sandbox_id,
                command=["npm", "run", "build", "--", "--outDir", dist_workspace],
                timeout_seconds=int(os.getenv("APPS_BUILD_NPM_BUILD_TIMEOUT_SECONDS", "300")),
                max_output_bytes=int(os.getenv("APPS_PUBLISH_SANDBOX_MAX_OUTPUT_BYTES", "30000")),
                workspace_path=live_workspace_path,
            )
            self._assert_command_success(result=build_result, command_name="npm run build")
            self._trace(
                "build.run.done",
                app_id=app.id,
                workspace_build_id=str(build.id),
                dist_workspace=dist_workspace,
                exit_code=self._extract_exit_code(build_result, command_name="npm run build"),
            )
            build.build_finished_at = datetime.now(timezone.utc)

            self._trace(
                "build.export.begin",
                app_id=app.id,
                workspace_build_id=str(build.id),
                dist_workspace=dist_workspace,
            )
            archive_response = await self.runtime_service.client.export_workspace_archive(
                sandbox_id=sandbox_id,
                workspace_path=dist_workspace,
                format="tar.gz",
            )
            archive_bytes = self.runtime_service.client.decode_archive_payload(archive_response)
            self._trace(
                "build.export.done",
                app_id=app.id,
                workspace_build_id=str(build.id),
                archive_bytes=len(archive_bytes),
            )

            with tempfile.TemporaryDirectory(prefix=f"apps-workspace-build-{str(app.id)[:8]}-") as temp_dir:
                extract_dir = Path(temp_dir) / "dist"
                extract_dir.mkdir(parents=True, exist_ok=True)
                archive_path = Path(temp_dir) / "dist.tar.gz"
                archive_path.write_bytes(archive_bytes)
                with tarfile.open(archive_path, mode="r:gz") as tar:
                    tar.extractall(path=extract_dir)
                dist_root = self._normalize_extracted_dist_root(extract_dir)
                if not dist_root.exists() or not dist_root.is_dir():
                    raise PublishedAppWorkspaceBuildError("Build succeeded but dist directory was not produced.")

                dist_manifest = self._build_dist_manifest(dist_root)
                dist_manifest["source_fingerprint"] = source_fingerprint
                dist_manifest["workspace_revision_token"] = workspace_revision_token

                storage = PublishedAppBundleStorage.from_env()
                dist_storage_prefix = PublishedAppBundleStorage.build_workspace_build_dist_prefix(
                    tenant_id=str(app.tenant_id),
                    app_id=str(app.id),
                    workspace_build_id=str(build.id),
                )
                dist_manifest["uploaded_assets"] = self._upload_dist_dir(
                    storage=storage,
                    dist_dir=dist_root,
                    dist_storage_prefix=dist_storage_prefix,
                )
                build.dist_storage_prefix = dist_storage_prefix
                build.dist_manifest = dist_manifest

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
                app_id=app.id,
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
                    app_id=app.id,
                    workspace_build_id=build_id,
                    workspace_fingerprint=locals().get("source_fingerprint"),
                )
                await self.db.flush()
                self._trace(
                    "build.failed.flush_done",
                    app_id=app.id,
                    workspace_build_id=build_id,
                    workspace_fingerprint=locals().get("source_fingerprint"),
                )
                self._trace(
                    "build.failed.commit_begin",
                    app_id=app.id,
                    workspace_build_id=build_id,
                    workspace_fingerprint=locals().get("source_fingerprint"),
                )
                await self.db.commit()
                self._trace(
                    "build.failed.commit_done",
                    app_id=app.id,
                    workspace_build_id=build_id,
                    workspace_fingerprint=locals().get("source_fingerprint"),
                )
            self._trace(
                "build.failed",
                app_id=app.id,
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
