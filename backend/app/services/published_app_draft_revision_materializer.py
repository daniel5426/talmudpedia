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

from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppDraftWorkspace,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
)
from app.services.apps_builder_trace import apps_builder_trace
from app.services.apps_builder_dependency_policy import validate_builder_dependency_policy
from app.services.published_app_builder_snapshot_filter import filter_builder_snapshot_files
from app.services.published_app_bundle_storage import PublishedAppBundleStorage
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService
from app.services.published_app_revision_store import PublishedAppRevisionStore
from app.services.published_app_templates import TemplateRuntimeContext, apply_runtime_bootstrap_overlay
from app.services.published_app_versioning import create_app_version

logger = logging.getLogger(__name__)

_NPM_INSTALL_COMMAND = ["npm", "install", "--no-audit", "--no-fund"]
_NPM_CI_COMMAND = ["npm", "ci"]


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
            raise PublishedAppDraftRevisionMaterializerError(
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
        raise PublishedAppDraftRevisionMaterializerError(
            f"`{command_name}` failed with exit code {code}\n{detail}"
        )

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
    def _bundle_hash_for_files(files: Dict[str, str]) -> str:
        manifest = {
            path: PublishedAppRevisionStore._hash_content(content)
            for path, content in sorted((files or {}).items())
        }
        return PublishedAppRevisionStore._manifest_bundle_hash(manifest)

    async def _find_existing_revision(
        self,
        *,
        app_id: UUID,
        entry_file: str,
        bundle_hash: str,
        source_fingerprint: str,
    ) -> PublishedAppRevision | None:
        result = await self.db.execute(
            select(PublishedAppRevision)
            .where(
                PublishedAppRevision.published_app_id == app_id,
                PublishedAppRevision.kind == PublishedAppRevisionKind.draft,
                PublishedAppRevision.entry_file == entry_file,
                PublishedAppRevision.bundle_hash == bundle_hash,
                PublishedAppRevision.build_status == PublishedAppRevisionBuildStatus.succeeded,
            )
            .order_by(PublishedAppRevision.created_at.desc())
            .limit(20)
        )
        for revision in result.scalars().all():
            if not str(revision.dist_storage_prefix or "").strip():
                continue
            manifest = revision.dist_manifest if isinstance(revision.dist_manifest, dict) else {}
            if str(manifest.get("source_fingerprint") or "").strip() == source_fingerprint:
                return revision
        return None

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
            raise PublishedAppDraftRevisionMaterializerError("Draft workspace is unavailable for version materialization.")
        return workspace

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
        workspace = await self._resolve_workspace(app_id=app.id)
        sandbox_id = str(workspace.sandbox_id or "").strip()
        runtime_context = TemplateRuntimeContext(
            app_id=str(app.id),
            app_slug=str(app.slug or ""),
            agent_id=str(app.agent_id or ""),
        )
        self._trace(
            "materialize.snapshot.begin",
            app_id=app.id,
            sandbox_id=sandbox_id,
        )
        snapshot = await self.runtime_service.client.snapshot_workspace(
            sandbox_id=sandbox_id,
            workspace="live",
        )
        self._trace(
            "materialize.snapshot.done",
            app_id=app.id,
            sandbox_id=sandbox_id,
            file_count=int(snapshot.get("file_count") or 0),
            workspace_revision_token=str(snapshot.get("revision_token") or ""),
            workspace_path=str(snapshot.get("workspace_path") or ""),
        )
        raw_files = {
            str(path): str(content if isinstance(content, str) else str(content))
            for path, content in dict(snapshot.get("files") or {}).items()
        }
        build_files = apply_runtime_bootstrap_overlay(
            filter_builder_snapshot_files(raw_files),
            runtime_context=runtime_context,
        )
        diagnostics = validate_builder_dependency_policy(build_files)
        if diagnostics:
            raise PublishedAppDraftRevisionMaterializerError(
                "; ".join(item.get("message", "Build policy violation") for item in diagnostics)
            )

        normalized_entry_file = str(entry_file or "").strip() or "src/main.tsx"
        source_fingerprint = self._build_source_fingerprint(entry_file=normalized_entry_file, files=build_files)
        bundle_hash = self._bundle_hash_for_files(build_files)
        existing = await self._find_existing_revision(
            app_id=app.id,
            entry_file=normalized_entry_file,
            bundle_hash=bundle_hash,
            source_fingerprint=source_fingerprint,
        )
        workspace_revision_token = str(snapshot.get("revision_token") or "").strip() or None
        if existing is not None:
            app.current_draft_revision_id = existing.id
            self._trace(
                "materialize.reused_existing_revision",
                app_id=app.id,
                revision_id=str(existing.id),
                source_fingerprint=source_fingerprint,
                workspace_revision_token=str(workspace_revision_token or ""),
            )
            return MaterializedDraftRevisionResult(
                revision=existing,
                reused=True,
                source_fingerprint=source_fingerprint,
                workspace_revision_token=workspace_revision_token,
            )

        live_workspace_path = str(
            snapshot.get("workspace_path")
            or workspace.live_workspace_path
            or ""
        ).strip()
        if not live_workspace_path:
            raise PublishedAppDraftRevisionMaterializerError("Live workspace path is unavailable.")

        self._trace(
            "materialize.dependencies.begin",
            app_id=app.id,
            sandbox_id=sandbox_id,
            workspace_path=live_workspace_path,
        )
        dependency_prepare = await self.runtime_service.client.prepare_publish_dependencies(
            sandbox_id=sandbox_id,
            workspace_path=live_workspace_path,
        )
        dependency_status = str(dependency_prepare.get("status") or "").strip().lower()
        self._trace(
            "materialize.dependencies.done",
            app_id=app.id,
            sandbox_id=sandbox_id,
            workspace_path=live_workspace_path,
            dependency_status=dependency_status,
        )
        if dependency_status not in {"reused", "prepared"}:
            install_command = self._resolve_install_command(build_files)
            self._trace(
                "materialize.install.begin",
                app_id=app.id,
                sandbox_id=sandbox_id,
                workspace_path=live_workspace_path,
                command=" ".join(install_command),
            )
            install_result = await self.runtime_service.client.run_command(
                sandbox_id=sandbox_id,
                command=install_command,
                timeout_seconds=int(os.getenv("APPS_BUILD_NPM_INSTALL_TIMEOUT_SECONDS", "360")),
                max_output_bytes=int(os.getenv("APPS_PUBLISH_SANDBOX_MAX_OUTPUT_BYTES", "30000")),
                workspace_path=live_workspace_path,
            )
            self._assert_command_success(result=install_result, command_name=" ".join(install_command))
            self._trace(
                "materialize.install.done",
                app_id=app.id,
                sandbox_id=sandbox_id,
                workspace_path=live_workspace_path,
                exit_code=int(install_result.get("exit_code") or 0),
            )

        build_root = f"{live_workspace_path.rstrip('/')}/.talmudpedia/materialized-build"
        dist_workspace = f"{build_root}/dist"
        self._trace(
            "materialize.build_dir.begin",
            app_id=app.id,
            sandbox_id=sandbox_id,
            build_root=build_root,
        )
        prepare_build_dir = await self.runtime_service.client.run_command(
            sandbox_id=sandbox_id,
            command=["bash", "-lc", f"rm -rf {json.dumps(build_root)} && mkdir -p {json.dumps(build_root)}"],
            timeout_seconds=60,
            max_output_bytes=8000,
            workspace_path=live_workspace_path,
        )
        self._assert_command_success(result=prepare_build_dir, command_name="prepare materialized build dir")
        self._trace(
            "materialize.build_dir.done",
            app_id=app.id,
            sandbox_id=sandbox_id,
            build_root=build_root,
        )

        build_started_at = datetime.now(timezone.utc)
        self._trace(
            "materialize.build.begin",
            app_id=app.id,
            sandbox_id=sandbox_id,
            workspace_path=live_workspace_path,
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
        build_finished_at = datetime.now(timezone.utc)
        self._trace(
            "materialize.build.done",
            app_id=app.id,
            sandbox_id=sandbox_id,
            workspace_path=live_workspace_path,
            dist_workspace=dist_workspace,
            exit_code=int(build_result.get("exit_code") or 0),
            build_duration_ms=int((build_finished_at - build_started_at).total_seconds() * 1000),
        )

        self._trace(
            "materialize.export.begin",
            app_id=app.id,
            sandbox_id=sandbox_id,
            workspace_path=dist_workspace,
        )
        archive_response = await self.runtime_service.client.export_workspace_archive(
            sandbox_id=sandbox_id,
            workspace_path=dist_workspace,
            format="tar.gz",
        )
        archive_bytes = self.runtime_service.client.decode_archive_payload(archive_response)
        self._trace(
            "materialize.export.done",
            app_id=app.id,
            sandbox_id=sandbox_id,
            workspace_path=dist_workspace,
            archive_bytes=len(archive_bytes),
        )

        with tempfile.TemporaryDirectory(prefix=f"apps-draft-dist-{str(app.id)[:8]}-") as temp_dir:
            extract_dir = Path(temp_dir) / "dist"
            extract_dir.mkdir(parents=True, exist_ok=True)
            archive_path = Path(temp_dir) / "dist.tar.gz"
            archive_path.write_bytes(archive_bytes)
            with tarfile.open(archive_path, mode="r:gz") as tar:
                tar.extractall(path=extract_dir)
            dist_root = self._normalize_extracted_dist_root(extract_dir)
            if not dist_root.exists() or not dist_root.is_dir():
                raise PublishedAppDraftRevisionMaterializerError("Build succeeded but dist directory was not produced.")

            dist_manifest = self._build_dist_manifest(dist_root)
            dist_manifest["source_fingerprint"] = source_fingerprint
            dist_manifest["workspace_revision_token"] = workspace_revision_token

            source_build_seq = 0
            if source_revision_id is not None:
                source_revision = await self.db.get(PublishedAppRevision, source_revision_id)
                if source_revision is not None:
                    source_build_seq = int(source_revision.build_seq or 0)

            self._trace(
                "materialize.revision_create.begin",
                app_id=app.id,
                source_revision_id=str(source_revision_id or ""),
                source_build_seq=source_build_seq,
                source_fingerprint=source_fingerprint,
            )
            revision = await create_app_version(
                self.db,
                app=app,
                kind=PublishedAppRevisionKind.draft,
                template_key=app.template_key,
                entry_file=normalized_entry_file,
                files=build_files,
                created_by=created_by,
                source_revision_id=source_revision_id,
                origin_kind=origin_kind,
                origin_run_id=origin_run_id,
                build_status=PublishedAppRevisionBuildStatus.succeeded,
                build_seq=source_build_seq + 1,
                build_error=None,
                build_started_at=build_started_at,
                build_finished_at=build_finished_at,
                template_runtime="vite_static",
            )
            self._trace(
                "materialize.revision_create.done",
                app_id=app.id,
                revision_id=str(revision.id),
                build_seq=int(revision.build_seq or 0),
            )

            storage = PublishedAppBundleStorage.from_env()
            dist_storage_prefix = PublishedAppBundleStorage.build_revision_dist_prefix(
                tenant_id=str(app.tenant_id),
                app_id=str(app.id),
                revision_id=str(revision.id),
            )
            self._trace(
                "materialize.upload.begin",
                app_id=app.id,
                revision_id=str(revision.id),
                dist_storage_prefix=dist_storage_prefix,
            )
            dist_manifest["uploaded_assets"] = self._upload_dist_dir(
                storage=storage,
                dist_dir=dist_root,
                dist_storage_prefix=dist_storage_prefix,
            )
            self._trace(
                "materialize.upload.done",
                app_id=app.id,
                revision_id=str(revision.id),
                uploaded_assets=int(dist_manifest.get("uploaded_assets") or 0),
                dist_storage_prefix=dist_storage_prefix,
            )

            revision.dist_storage_prefix = dist_storage_prefix
            revision.dist_manifest = dist_manifest
            revision.build_status = PublishedAppRevisionBuildStatus.succeeded
            revision.build_error = None
            revision.build_started_at = build_started_at
            revision.build_finished_at = build_finished_at
            app.current_draft_revision_id = revision.id
            await self.db.flush()

        self._trace(
            "materialize.done",
            app_id=app.id,
            revision_id=str(revision.id),
            reused=False,
            source_fingerprint=source_fingerprint,
            workspace_revision_token=str(workspace_revision_token or ""),
        )
        return MaterializedDraftRevisionResult(
            revision=revision,
            reused=False,
            source_fingerprint=source_fingerprint,
            workspace_revision_token=workspace_revision_token,
        )

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
        try:
            result = await self.materialize_live_workspace(
                app=app,
                entry_file=entry_file,
                source_revision_id=source_revision_id,
                created_by=created_by,
                origin_kind="coding_run",
                origin_run_id=run.id,
            )
        except Exception as exc:
            self._trace(
                "materialize.failed",
                app_id=app.id,
                run_id=str(run.id),
                origin_kind="coding_run",
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            raise
        run.result_revision_id = result.revision.id
        run.batch_finalized_at = datetime.now(timezone.utc)
        return result.revision
