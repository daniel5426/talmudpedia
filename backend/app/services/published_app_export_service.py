from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppDraftDevSession,
    PublishedAppDraftWorkspace,
    PublishedAppRevision,
)
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService
from app.services.published_app_revision_store import PublishedAppRevisionStore


EXPORT_BOOTSTRAP_ROOT = (
    Path(__file__).resolve().parent.parent / "templates" / "published_app_export_bootstrap" / "classic-chat-standalone"
)
SUPPORTED_EXPORT_TEMPLATE_KEYS = {"classic-chat"}


@dataclass(frozen=True)
class PublishedAppExportOptions:
    supported: bool
    ready: bool
    template_key: str
    source_kind: str | None
    default_archive_name: str
    reason: str | None = None


@dataclass(frozen=True)
class PublishedAppExportArchive:
    filename: str
    source_kind: str
    files: Dict[str, str]
    diagnostics: list[dict[str, str]]

    def to_zip_bytes(self) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, content in sorted(self.files.items()):
                archive.writestr(path, content)
        return buffer.getvalue()


class PublishedAppExportService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.revision_store = PublishedAppRevisionStore(db)

    def build_options(self, *, app: PublishedApp, has_source: bool, source_kind: str | None) -> PublishedAppExportOptions:
        template_key = str(app.template_key or "").strip()
        supported = template_key in SUPPORTED_EXPORT_TEMPLATE_KEYS
        archive_name = f"{str(app.slug or 'app').strip() or 'app'}-standalone-export.zip"
        if not supported:
            return PublishedAppExportOptions(
                supported=False,
                ready=False,
                template_key=template_key,
                source_kind=None,
                default_archive_name=archive_name,
                reason="Only classic-chat apps are supported by the current standalone export.",
            )
        if not has_source:
            return PublishedAppExportOptions(
                supported=True,
                ready=False,
                template_key=template_key,
                source_kind=None,
                default_archive_name=archive_name,
                reason="The app does not have an exportable draft source snapshot yet.",
            )
        return PublishedAppExportOptions(
            supported=True,
            ready=True,
            template_key=template_key,
            source_kind=source_kind,
            default_archive_name=archive_name,
            reason=None,
        )

    async def build_archive(self, *, app: PublishedApp) -> PublishedAppExportArchive:
        template_key = str(app.template_key or "").strip()
        if template_key not in SUPPORTED_EXPORT_TEMPLATE_KEYS:
            raise ValueError("Only classic-chat apps are supported by the current standalone export.")

        source_files, source_kind = await self._resolve_source_files(app=app)
        if not source_files:
            raise ValueError("The app does not have an exportable draft source snapshot yet.")

        bundle = dict(source_files)
        bundle.update(self._load_bootstrap_files())
        bundle["package.json"] = self._patch_package_json(bundle.get("package.json"))
        bundle["vite.config.ts"] = self._export_vite_config()
        diagnostics = [
            {
                "message": "This export is generated from the current draft source and includes a standalone Vite + /api scaffold.",
            }
        ]
        archive_name = f"{str(app.slug or 'app').strip() or 'app'}-standalone-export.zip"
        return PublishedAppExportArchive(
            filename=archive_name,
            source_kind=source_kind,
            files=bundle,
            diagnostics=diagnostics,
        )

    async def resolve_options(self, *, app: PublishedApp) -> PublishedAppExportOptions:
        try:
            _, source_kind = await self._resolve_source_files(app=app)
            has_source = True
        except Exception:
            source_kind = None
            has_source = False
        return self.build_options(app=app, has_source=has_source, source_kind=source_kind)

    async def _resolve_source_files(self, *, app: PublishedApp) -> tuple[Dict[str, str], str]:
        revision = await self._get_current_draft_revision(app=app)
        revision_files = await self.revision_store.materialize_revision_files(revision)
        snapshot_files = await self._resolve_live_workspace_snapshot_files(app=app, revision=revision)
        if snapshot_files:
            merged_files = dict(revision_files)
            merged_files.update(snapshot_files)
            return merged_files, "live_workspace_snapshot"
        return revision_files, "draft_revision"

    async def _get_current_draft_revision(self, *, app: PublishedApp) -> PublishedAppRevision:
        if app.current_draft_revision_id is None:
            raise ValueError("App has no current draft revision.")
        revision = await self.db.get(PublishedAppRevision, app.current_draft_revision_id)
        if revision is None or str(revision.published_app_id) != str(app.id):
            raise ValueError("App draft revision could not be resolved.")
        return revision

    async def _resolve_live_workspace_snapshot_files(
        self,
        *,
        app: PublishedApp,
        revision: PublishedAppRevision,
    ) -> Dict[str, str] | None:
        snapshots: list[dict[str, Any]] = []
        workspace_result = await self.db.execute(
            select(PublishedAppDraftWorkspace.backend_metadata).where(
                PublishedAppDraftWorkspace.published_app_id == app.id
            )
        )
        for metadata in workspace_result.scalars().all():
            snapshot = PublishedAppDraftDevRuntimeService._get_live_workspace_snapshot_for_revision(
                metadata=metadata,
                revision_id=revision.id,
            )
            if snapshot:
                snapshots.append(snapshot)

        session_result = await self.db.execute(
            select(PublishedAppDraftDevSession.backend_metadata).where(
                PublishedAppDraftDevSession.published_app_id == app.id
            )
        )
        for metadata in session_result.scalars().all():
            snapshot = PublishedAppDraftDevRuntimeService._get_live_workspace_snapshot_for_revision(
                metadata=metadata,
                revision_id=revision.id,
            )
            if snapshot:
                snapshots.append(snapshot)

        if not snapshots:
            return None

        latest = max(
            snapshots,
            key=lambda item: str(item.get("updated_at") or ""),
        )
        files = latest.get("files")
        if not isinstance(files, dict):
            return None
        normalized: Dict[str, str] = {}
        for raw_path, raw_content in files.items():
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue
            if not isinstance(raw_content, str):
                continue
            normalized[raw_path] = raw_content
        return normalized or None

    def _load_bootstrap_files(self) -> Dict[str, str]:
        files: Dict[str, str] = {}
        for path in sorted(EXPORT_BOOTSTRAP_ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel_path = path.relative_to(EXPORT_BOOTSTRAP_ROOT).as_posix()
            files[rel_path] = path.read_text(encoding="utf-8")
        if not files:
            raise ValueError(f"Export bootstrap files are missing under {EXPORT_BOOTSTRAP_ROOT}")
        return files

    def _patch_package_json(self, source: str | None) -> str:
        if not source:
            raise ValueError("Export requires package.json in the app source.")
        payload = json.loads(source)
        if not isinstance(payload, dict):
            raise ValueError("package.json must be a JSON object.")

        scripts = dict(payload.get("scripts") or {})
        scripts.update(
            {
                "dev": 'concurrently -k "pnpm dev:api" "pnpm dev:client"',
                "dev:api": "tsx watch server/dev-api.ts",
                "dev:client": "vite",
                "preview": "vite preview",
            }
        )
        payload["scripts"] = scripts

        dependencies = dict(payload.get("dependencies") or {})
        dependencies.pop("@talmudpedia/runtime-sdk", None)
        dependencies["@agents24/embed-sdk"] = "file:../packages/embed-sdk"
        dependencies["dotenv"] = dependencies.get("dotenv") or "^16.6.1"
        payload["dependencies"] = dependencies

        dev_dependencies = dict(payload.get("devDependencies") or {})
        dev_dependencies["concurrently"] = dev_dependencies.get("concurrently") or "^9.2.1"
        dev_dependencies["tsx"] = dev_dependencies.get("tsx") or "^4.20.6"
        payload["devDependencies"] = dev_dependencies

        return json.dumps(payload, ensure_ascii=True, indent=2) + "\n"

    def _export_vite_config(self) -> str:
        return """import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

const usePolling = process.env.__APPS_VITE_USE_POLLING === "1"
const pollingInterval = Number(process.env.__APPS_VITE_POLL_INTERVAL_MS || 250)
const devApiTarget = process.env.VITE_DEV_API_TARGET || "http://127.0.0.1:3001"
const isBuild = process.env.NODE_ENV === "production"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: isBuild ? "./" : "/",
  server:
    usePolling || devApiTarget
      ? {
          proxy: {
            "/api": {
              target: devApiTarget,
              changeOrigin: true,
            },
          },
          ...(usePolling
            ? {
                watch: {
                  usePolling: true,
                  interval: Number.isFinite(pollingInterval) ? pollingInterval : 250,
                },
              }
            : {}),
        }
      : undefined,
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
})
"""
