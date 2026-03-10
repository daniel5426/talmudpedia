from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, exists, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.core.security import create_published_app_draft_dev_token
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppDraftDevSession,
    PublishedAppDraftDevSessionStatus,
    PublishedAppDraftWorkspace,
    PublishedAppDraftWorkspaceStatus,
    PublishedAppPublishJob,
    PublishedAppPublishJobStatus,
    PublishedAppRevision,
)
from app.services.apps_builder_trace import apps_builder_trace
from app.services.published_app_draft_dev_runtime_client import (
    PublishedAppDraftDevRuntimeClient,
    PublishedAppDraftDevRuntimeClientError,
)
from app.services.published_app_templates import TemplateRuntimeContext, apply_runtime_bootstrap_overlay


LOCKFILE_PATHS = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock")


@dataclass(frozen=True)
class DraftDevRuntimeSettings:
    enabled: bool
    idle_timeout_seconds: int
    hard_max_lifetime_seconds: int
    workspace_retention_seconds: int


class PublishedAppDraftDevRuntimeError(Exception):
    pass


class PublishedAppDraftDevRuntimeDisabled(PublishedAppDraftDevRuntimeError):
    pass


class PublishedAppDraftDevRuntimeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = PublishedAppDraftDevRuntimeClient.from_env()
        self.settings = self._load_settings()

    @staticmethod
    def _load_settings() -> DraftDevRuntimeSettings:
        enabled_raw = os.getenv("APPS_BUILDER_DRAFT_DEV_ENABLED", "1")
        idle_raw = int(os.getenv("APPS_DRAFT_DEV_IDLE_TIMEOUT_SECONDS", "180"))
        hard_max_raw = int(os.getenv("APPS_DRAFT_DEV_HARD_MAX_LIFETIME_SECONDS", "1800"))
        retention_raw = int(os.getenv("APPS_SPRITE_RETENTION_SECONDS", "21600"))
        idle_timeout_seconds = min(max(idle_raw, 120), 300)
        hard_max_lifetime_seconds = max(hard_max_raw, idle_timeout_seconds)
        enabled = enabled_raw.strip().lower() not in {"0", "false", "off", "no"}
        return DraftDevRuntimeSettings(
            enabled=enabled,
            idle_timeout_seconds=idle_timeout_seconds,
            hard_max_lifetime_seconds=hard_max_lifetime_seconds,
            workspace_retention_seconds=max(retention_raw, idle_timeout_seconds),
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _normalize_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _dependency_hash(files: Dict[str, str]) -> str:
        dependency_files: Dict[str, str] = {}
        package_json = files.get("package.json")
        if isinstance(package_json, str):
            dependency_files["package.json"] = package_json
        for lockfile_path in LOCKFILE_PATHS:
            lockfile = files.get(lockfile_path)
            if isinstance(lockfile, str):
                dependency_files[lockfile_path] = lockfile
        serialized = json.dumps(dependency_files, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _scope_error() -> PublishedAppDraftDevRuntimeError:
        return PublishedAppDraftDevRuntimeError("Draft dev mode requires an authenticated user scope")

    @staticmethod
    def _is_runtime_not_running_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return any(
            token in message
            for token in (
                "sandbox is not running",
                "draft dev sandbox is not running",
                "session not found",
                "sandbox wasn't found",
                "sandbox was not found",
                "sprite request failed (404)",
            )
        )

    @staticmethod
    def _is_timeout_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "readtimeout" in message or "timed out" in message

    @classmethod
    def _is_transient_remote_error(cls, exc: Exception) -> bool:
        message = str(exc).lower()
        return cls._is_timeout_error(exc) or any(
            token in message
            for token in ("connecttimeout", "temporarily unavailable", "connection reset", "502", "503", "504")
        )

    @staticmethod
    def _active_session_statuses() -> tuple[PublishedAppDraftDevSessionStatus, ...]:
        return (
            PublishedAppDraftDevSessionStatus.starting,
            PublishedAppDraftDevSessionStatus.building,
            PublishedAppDraftDevSessionStatus.serving,
            PublishedAppDraftDevSessionStatus.degraded,
            PublishedAppDraftDevSessionStatus.running,
            PublishedAppDraftDevSessionStatus.stopping,
        )

    @staticmethod
    def _workspace_active_statuses() -> tuple[str, ...]:
        return (
            PublishedAppDraftWorkspaceStatus.starting.value,
            PublishedAppDraftWorkspaceStatus.syncing.value,
            PublishedAppDraftWorkspaceStatus.serving.value,
            PublishedAppDraftWorkspaceStatus.degraded.value,
        )

    @staticmethod
    def _is_session_serving_status(status: PublishedAppDraftDevSessionStatus | str | None) -> bool:
        value = str(getattr(status, "value", status) or "").strip().lower()
        return value in {
            PublishedAppDraftDevSessionStatus.serving.value,
            PublishedAppDraftDevSessionStatus.running.value,
        }

    @staticmethod
    def _runtime_generation_value(entity: object) -> int:
        try:
            return int(getattr(entity, "runtime_generation", 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _normalize_runtime_sandbox_id(raw: object) -> str | None:
        value = str(raw or "").strip()
        return value or None

    @staticmethod
    def _merge_backend_metadata(
        *,
        existing_metadata: object,
        refreshed_metadata: object,
        preview_base_path: str | None = None,
    ) -> dict[str, Any]:
        existing = dict(existing_metadata or {}) if isinstance(existing_metadata, dict) else {}
        refreshed = dict(refreshed_metadata or {}) if isinstance(refreshed_metadata, dict) else {}
        if not refreshed:
            return existing
        existing_preview = existing.get("preview") if isinstance(existing.get("preview"), dict) else {}
        refreshed_preview = dict(refreshed.get("preview") or {}) if isinstance(refreshed.get("preview"), dict) else {}
        preserved_base_path = str(preview_base_path or refreshed_preview.get("base_path") or existing_preview.get("base_path") or "").strip()
        if preserved_base_path:
            refreshed_preview["base_path"] = preserved_base_path
        if refreshed_preview:
            refreshed["preview"] = refreshed_preview
        return refreshed

    @staticmethod
    def _preview_build_current_available(preview_build: object) -> bool:
        payload = preview_build if isinstance(preview_build, dict) else {}
        current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
        current_build_id = str(current.get("build_id") or "").strip()
        return bool(current_build_id)

    @staticmethod
    def _session_load_options():
        return load_only(
            PublishedAppDraftDevSession.id,
            PublishedAppDraftDevSession.published_app_id,
            PublishedAppDraftDevSession.user_id,
            PublishedAppDraftDevSession.revision_id,
            PublishedAppDraftDevSession.draft_workspace_id,
            PublishedAppDraftDevSession.status,
            PublishedAppDraftDevSession.sandbox_id,
            PublishedAppDraftDevSession.runtime_generation,
            PublishedAppDraftDevSession.runtime_backend,
            PublishedAppDraftDevSession.backend_metadata,
            PublishedAppDraftDevSession.preview_url,
            PublishedAppDraftDevSession.idle_timeout_seconds,
            PublishedAppDraftDevSession.expires_at,
            PublishedAppDraftDevSession.last_activity_at,
            PublishedAppDraftDevSession.dependency_hash,
            PublishedAppDraftDevSession.last_error,
            PublishedAppDraftDevSession.created_at,
            PublishedAppDraftDevSession.updated_at,
        )

    @staticmethod
    def _workspace_load_options():
        return load_only(
            PublishedAppDraftWorkspace.id,
            PublishedAppDraftWorkspace.published_app_id,
            PublishedAppDraftWorkspace.revision_id,
            PublishedAppDraftWorkspace.status,
            PublishedAppDraftWorkspace.sprite_name,
            PublishedAppDraftWorkspace.sandbox_id,
            PublishedAppDraftWorkspace.runtime_generation,
            PublishedAppDraftWorkspace.runtime_backend,
            PublishedAppDraftWorkspace.backend_metadata,
            PublishedAppDraftWorkspace.preview_url,
            PublishedAppDraftWorkspace.live_workspace_path,
            PublishedAppDraftWorkspace.stage_workspace_path,
            PublishedAppDraftWorkspace.publish_workspace_path,
            PublishedAppDraftWorkspace.preview_service_name,
            PublishedAppDraftWorkspace.opencode_service_name,
            PublishedAppDraftWorkspace.dependency_hash,
            PublishedAppDraftWorkspace.last_activity_at,
            PublishedAppDraftWorkspace.detached_at,
            PublishedAppDraftWorkspace.last_error,
            PublishedAppDraftWorkspace.created_at,
            PublishedAppDraftWorkspace.updated_at,
        )

    @staticmethod
    def _workspace_lock_key(*, app_id: UUID) -> int:
        digest = hashlib.sha256(f"draft-workspace:{app_id}".encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF

    async def _acquire_scope_lock(self, *, app_id: UUID, user_id: UUID) -> None:
        _ = user_id
        bind = self.db.get_bind()
        dialect_name = str(getattr(getattr(bind, "dialect", None), "name", "") or "").lower()
        if dialect_name == "sqlite":
            return
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": self._workspace_lock_key(app_id=app_id)},
        )

    def _session_expires_at(self, now: Optional[datetime] = None) -> datetime:
        base = now or self._now()
        return base + timedelta(seconds=self.settings.idle_timeout_seconds)

    async def get_session(self, *, app_id: UUID, user_id: UUID) -> Optional[PublishedAppDraftDevSession]:
        result = await self.db.execute(
            select(PublishedAppDraftDevSession)
            .options(self._session_load_options())
            .where(
                and_(
                    PublishedAppDraftDevSession.published_app_id == app_id,
                    PublishedAppDraftDevSession.user_id == user_id,
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_workspace(self, *, app_id: UUID) -> Optional[PublishedAppDraftWorkspace]:
        result = await self.db.execute(
            select(PublishedAppDraftWorkspace)
            .options(self._workspace_load_options())
            .where(PublishedAppDraftWorkspace.published_app_id == app_id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_or_create_workspace(self, *, app: PublishedApp) -> PublishedAppDraftWorkspace:
        workspace = await self.get_workspace(app_id=app.id)
        if workspace is not None:
            return workspace
        candidate = PublishedAppDraftWorkspace(
            id=uuid4(),
            published_app_id=app.id,
            sprite_name="",
            status=PublishedAppDraftWorkspaceStatus.stopped,
            runtime_backend=self.client.backend_name,
            backend_metadata={},
        )
        candidate.sprite_name = self.client.expected_sandbox_id_for_app(app_id=str(app.id)) or str(app.id)
        try:
            async with self.db.begin_nested():
                self.db.add(candidate)
                await self.db.flush()
            return candidate
        except IntegrityError:
            workspace = await self.get_workspace(app_id=app.id)
            if workspace is None:
                raise
            return workspace

    async def _get_or_create_session(
        self,
        *,
        app: PublishedApp,
        user_id: UUID,
        revision: PublishedAppRevision,
        dependency_hash: str,
        now: datetime,
    ) -> PublishedAppDraftDevSession:
        session = await self.get_session(app_id=app.id, user_id=user_id)
        if session is not None:
            return session
        candidate = PublishedAppDraftDevSession(
            id=uuid4(),
            published_app_id=app.id,
            user_id=user_id,
            revision_id=revision.id,
            status=PublishedAppDraftDevSessionStatus.starting,
            runtime_backend=self.client.backend_name,
            backend_metadata={},
            idle_timeout_seconds=self.settings.idle_timeout_seconds,
            last_activity_at=now,
            expires_at=self._session_expires_at(now),
            dependency_hash=dependency_hash,
            runtime_generation=0,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(candidate)
                await self.db.flush()
            return candidate
        except IntegrityError:
            session = await self.get_session(app_id=app.id, user_id=user_id)
            if session is None:
                raise
            return session

    def _mark_workspace_error(self, workspace: PublishedAppDraftWorkspace, exc: Exception) -> None:
        workspace.status = PublishedAppDraftWorkspaceStatus.error
        workspace.last_error = str(exc)

    def _mark_workspace_degraded(self, workspace: PublishedAppDraftWorkspace, exc: Exception) -> None:
        workspace.status = PublishedAppDraftWorkspaceStatus.degraded
        workspace.last_error = str(exc)

    def _mark_session_error(self, session: PublishedAppDraftDevSession, exc: Exception) -> PublishedAppDraftDevSession:
        session.status = PublishedAppDraftDevSessionStatus.error
        session.last_error = str(exc)
        return session

    def _mark_session_degraded(self, session: PublishedAppDraftDevSession, exc: Exception) -> PublishedAppDraftDevSession:
        session.status = PublishedAppDraftDevSessionStatus.degraded
        session.last_error = str(exc)
        return session

    async def _reconcile_remote_workspace_best_effort(self, *, workspace: PublishedAppDraftWorkspace) -> None:
        if not bool(getattr(self.client, "is_remote_enabled", False)):
            return
        workspace_id = str(getattr(workspace, "id", "") or "").strip()
        if not workspace_id:
            return
        try:
            await self.client.reconcile_session_scope(
                session_id=workspace_id,
                expected_sandbox_id=self._normalize_runtime_sandbox_id(workspace.sandbox_id),
                runtime_generation=self._runtime_generation_value(workspace),
            )
        except PublishedAppDraftDevRuntimeClientError:
            return

    async def _sweep_remote_workspaces_best_effort(self) -> None:
        if not bool(getattr(self.client, "is_remote_enabled", False)):
            return
        result = await self.db.execute(
            select(PublishedAppDraftWorkspace)
            .options(self._workspace_load_options())
            .where(
                and_(
                    PublishedAppDraftWorkspace.runtime_backend == self.client.backend_name,
                    PublishedAppDraftWorkspace.status.in_(list(self._workspace_active_statuses())),
                )
            )
        )
        active_workspaces: dict[str, dict[str, object]] = {}
        for row in result.scalars().all():
            workspace_id = str(getattr(row, "id", "") or "").strip()
            sandbox_id = self._normalize_runtime_sandbox_id(row.sandbox_id)
            if not workspace_id or not sandbox_id:
                continue
            active_workspaces[workspace_id] = {
                "sandbox_id": sandbox_id,
                "runtime_generation": self._runtime_generation_value(row),
            }
        try:
            await self.client.sweep_remote_sessions(active_sessions=active_workspaces)
        except PublishedAppDraftDevRuntimeClientError:
            return

    async def _finalize_preview_runs_best_effort(
        self,
        *,
        app: PublishedApp,
        workspace: PublishedAppDraftWorkspace | None,
    ) -> None:
        if workspace is None:
            return
        try:
            from app.services.published_app_preview_builds import PublishedAppPreviewBuildService

            preview_builds = PublishedAppPreviewBuildService(self.db)
            snapshot = preview_builds.snapshot_from_workspace(workspace)
            if snapshot is None:
                return
            await preview_builds.finalize_waiting_runs_for_build(
                app=app,
                workspace=workspace,
                snapshot=snapshot,
            )
        except Exception:
            return

    def _attach_session(
        self,
        *,
        session: PublishedAppDraftDevSession,
        workspace: PublishedAppDraftWorkspace,
        revision: PublishedAppRevision,
        dependency_hash: str,
        now: datetime,
    ) -> PublishedAppDraftDevSession:
        session.revision_id = revision.id
        session.draft_workspace_id = workspace.id
        session.idle_timeout_seconds = self.settings.idle_timeout_seconds
        session.last_activity_at = now
        session.expires_at = self._session_expires_at(now)
        session.preview_url = self.client.build_preview_proxy_path(str(session.id))
        session.sandbox_id = self._normalize_runtime_sandbox_id(workspace.sandbox_id)
        session.runtime_generation = self._runtime_generation_value(workspace)
        session.runtime_backend = str(workspace.runtime_backend or self.client.backend_name)
        session.backend_metadata = dict(workspace.backend_metadata or {})
        session.dependency_hash = dependency_hash
        preview_build = workspace.backend_metadata.get("preview_build") if isinstance(workspace.backend_metadata, dict) else {}
        preview_build_error = (
            str(preview_build.get("last_error") or "").strip()
            if isinstance(preview_build, dict)
            else ""
        )
        session.last_error = (
            workspace.last_error
            if workspace.status == PublishedAppDraftWorkspaceStatus.degraded
            else (preview_build_error or None) if not self._preview_build_current_available(preview_build) else None
        )
        session.status = (
            PublishedAppDraftDevSessionStatus.degraded
            if workspace.status == PublishedAppDraftWorkspaceStatus.degraded
            else PublishedAppDraftDevSessionStatus.serving
        )
        return session

    async def _start_or_sync_workspace(
        self,
        *,
        app: PublishedApp,
        revision: PublishedAppRevision,
        user_id: UUID,
        workspace: PublishedAppDraftWorkspace,
        files_payload: Dict[str, str],
        entry_value: str,
        dependency_hash: str,
        preview_base_path: str,
        now: datetime,
    ) -> PublishedAppDraftWorkspace:
        must_start = workspace.status in {
            PublishedAppDraftWorkspaceStatus.stopped,
            PublishedAppDraftWorkspaceStatus.error,
            PublishedAppDraftWorkspaceStatus.stopping,
        } or not str(workspace.sandbox_id or "").strip()
        workspace.last_activity_at = now
        workspace.detached_at = None
        workspace.revision_id = revision.id
        workspace.preview_url = preview_base_path
        if must_start:
            workspace.runtime_generation = self._runtime_generation_value(workspace) + 1
            workspace.status = PublishedAppDraftWorkspaceStatus.syncing
            workspace.last_error = None
            started = await self.client.start_session(
                session_id=str(workspace.id),
                runtime_generation=workspace.runtime_generation,
                tenant_id=str(app.tenant_id),
                app_id=str(app.id),
                user_id=str(user_id),
                revision_id=str(revision.id),
                entry_file=entry_value,
                files=files_payload,
                idle_timeout_seconds=self.settings.idle_timeout_seconds,
                dependency_hash=dependency_hash,
                draft_dev_token=create_published_app_draft_dev_token(
                    subject=str(user_id),
                    tenant_id=str(app.tenant_id),
                    app_id=str(app.id),
                    user_id=str(user_id),
                    session_id=str(workspace.id),
                ),
                preview_base_path=preview_base_path,
            )
            workspace.sandbox_id = self._normalize_runtime_sandbox_id(started.get("sandbox_id")) or workspace.sprite_name
            workspace.runtime_backend = str(started.get("runtime_backend") or self.client.backend_name)
            workspace.backend_metadata = dict(started.get("backend_metadata") or {})
            metadata_workspace = workspace.backend_metadata.get("workspace") if isinstance(workspace.backend_metadata.get("workspace"), dict) else {}
            services = workspace.backend_metadata.get("services") if isinstance(workspace.backend_metadata.get("services"), dict) else {}
            workspace.live_workspace_path = str(started.get("live_workspace_path") or metadata_workspace.get("live_workspace_path") or "")
            workspace.stage_workspace_path = str(started.get("stage_workspace_path") or metadata_workspace.get("stage_workspace_path") or "")
            workspace.publish_workspace_path = str(started.get("publish_workspace_path") or metadata_workspace.get("publish_workspace_path") or "")
            workspace.preview_service_name = str(started.get("preview_service_name") or services.get("preview_service_name") or "")
            workspace.opencode_service_name = str(started.get("opencode_service_name") or services.get("opencode_service_name") or "")
            workspace.dependency_hash = dependency_hash
            workspace.status = PublishedAppDraftWorkspaceStatus.serving
            workspace.last_error = None
            await self._reconcile_remote_workspace_best_effort(workspace=workspace)
            return workspace

        install_dependencies = dependency_hash != str(workspace.dependency_hash or "")
        workspace.status = PublishedAppDraftWorkspaceStatus.syncing
        sync_result = await self.client.sync_session(
            sandbox_id=str(workspace.sandbox_id),
            entry_file=entry_value,
            files=files_payload,
            idle_timeout_seconds=self.settings.idle_timeout_seconds,
            dependency_hash=dependency_hash,
            install_dependencies=install_dependencies,
            preview_base_path=preview_base_path,
        )
        workspace.runtime_backend = str(sync_result.get("runtime_backend") or workspace.runtime_backend or self.client.backend_name)
        if isinstance(sync_result.get("backend_metadata"), dict):
            workspace.backend_metadata = dict(sync_result.get("backend_metadata") or {})
        workspace.dependency_hash = dependency_hash
        workspace.status = PublishedAppDraftWorkspaceStatus.serving
        workspace.last_error = None
        await self._reconcile_remote_workspace_best_effort(workspace=workspace)
        return workspace

    async def ensure_session(
        self,
        *,
        app: PublishedApp,
        revision: PublishedAppRevision,
        user_id: UUID,
        files: Optional[Dict[str, str]] = None,
        entry_file: Optional[str] = None,
    ) -> PublishedAppDraftDevSession:
        if not self.settings.enabled:
            raise PublishedAppDraftDevRuntimeDisabled("Draft dev mode is disabled (`APPS_BUILDER_DRAFT_DEV_ENABLED=0`).")
        if not user_id:
            raise self._scope_error()

        await self._acquire_scope_lock(app_id=app.id, user_id=user_id)
        now = self._now()
        await self.expire_idle_sessions(app_id=app.id)
        await self.sweep_dormant_workspaces(app_id=app.id)
        await self._sweep_remote_workspaces_best_effort()

        runtime_context = TemplateRuntimeContext(
            app_id=str(app.id),
            app_slug=str(app.slug or ""),
            agent_id=str(app.agent_id or ""),
        )
        files_payload = apply_runtime_bootstrap_overlay(
            dict(files or revision.files or {}),
            runtime_context=runtime_context,
        )
        entry_value = entry_file or revision.entry_file
        dependency_hash = self._dependency_hash(files_payload)

        workspace = await self._get_or_create_workspace(app=app)
        session = await self._get_or_create_session(
            app=app,
            user_id=user_id,
            revision=revision,
            dependency_hash=dependency_hash,
            now=now,
        )
        preview_base_path = self.client.build_preview_proxy_path(str(session.id))

        apps_builder_trace(
            "workspace.ensure.requested",
            domain="draft_dev.runtime",
            app_id=str(app.id),
            revision_id=str(revision.id),
            user_id=str(user_id),
            session_id=str(session.id),
            workspace_id=str(workspace.id),
            existing_sandbox_id=str(workspace.sandbox_id or "") or None,
            existing_workspace_status=str(getattr(workspace.status, "value", workspace.status) or ""),
            dependency_hash=dependency_hash,
            backend_name=self.client.backend_name,
        )

        try:
            await self._start_or_sync_workspace(
                app=app,
                revision=revision,
                user_id=user_id,
                workspace=workspace,
                files_payload=files_payload,
                entry_value=entry_value,
                dependency_hash=dependency_hash,
                preview_base_path=preview_base_path,
                now=now,
            )
        except PublishedAppDraftDevRuntimeClientError as exc:
            if not must_restartable_error(exc):
                self._mark_workspace_degraded(workspace, exc)
                return self._mark_session_degraded(session, exc)
            self._mark_workspace_error(workspace, exc)
            return self._mark_session_error(session, exc)

        attached = self._attach_session(
            session=session,
            workspace=workspace,
            revision=revision,
            dependency_hash=dependency_hash,
            now=now,
        )
        await self._finalize_preview_runs_best_effort(app=app, workspace=workspace)
        return attached

    async def ensure_active_session(
        self,
        *,
        app: PublishedApp,
        revision: PublishedAppRevision,
        user_id: UUID,
    ) -> PublishedAppDraftDevSession:
        if not self.settings.enabled:
            raise PublishedAppDraftDevRuntimeDisabled("Draft dev mode is disabled (`APPS_BUILDER_DRAFT_DEV_ENABLED=0`).")
        if not user_id:
            raise self._scope_error()

        now = self._now()
        await self.expire_idle_sessions(app_id=app.id)
        session = await self.get_session(app_id=app.id, user_id=user_id)
        workspace = await self.get_workspace(app_id=app.id)
        if (
            session is None
            or workspace is None
            or session.draft_workspace_id != workspace.id
            or session.revision_id != revision.id
            or not str(workspace.sandbox_id or "").strip()
            or str(getattr(workspace.status, "value", workspace.status) or "").strip().lower()
            not in self._workspace_active_statuses()
        ):
            return await self.ensure_session(
                app=app,
                revision=revision,
                user_id=user_id,
                files=dict(revision.files or {}),
                entry_file=revision.entry_file,
            )

        session.last_activity_at = now
        session.expires_at = self._session_expires_at(now)
        workspace.last_activity_at = now
        workspace.detached_at = None
        try:
            heartbeat_result = await self.client.heartbeat_session(
                sandbox_id=str(workspace.sandbox_id),
                idle_timeout_seconds=self.settings.idle_timeout_seconds,
            )
        except PublishedAppDraftDevRuntimeClientError as exc:
            if self._is_runtime_not_running_error(exc):
                return await self.ensure_session(
                    app=app,
                    revision=revision,
                    user_id=user_id,
                    files=dict(revision.files or {}),
                    entry_file=revision.entry_file,
                )
            if self._is_transient_remote_error(exc):
                self._mark_workspace_degraded(workspace, exc)
                return self._mark_session_degraded(session, exc)
            self._mark_workspace_error(workspace, exc)
            return self._mark_session_error(session, exc)

        attached = self._attach_session(
            session=session,
            workspace=workspace,
            revision=revision,
            dependency_hash=str(workspace.dependency_hash or session.dependency_hash or ""),
            now=now,
        )
        await self._finalize_preview_runs_best_effort(app=app, workspace=workspace)
        return attached

    async def sync_session(
        self,
        *,
        app: PublishedApp,
        revision: PublishedAppRevision,
        user_id: UUID,
        files: Dict[str, str],
        entry_file: str,
    ) -> PublishedAppDraftDevSession:
        return await self.ensure_session(
            app=app,
            revision=revision,
            user_id=user_id,
            files=files,
            entry_file=entry_file,
        )

    async def heartbeat_session(self, *, session: PublishedAppDraftDevSession) -> PublishedAppDraftDevSession:
        if not self.settings.enabled:
            raise PublishedAppDraftDevRuntimeDisabled("Draft dev mode is disabled (`APPS_BUILDER_DRAFT_DEV_ENABLED=0`).")
        if session.draft_workspace_id is None:
            session.status = PublishedAppDraftDevSessionStatus.error
            session.last_error = "Draft dev session is detached from the shared workspace."
            return session

        workspace = await self.db.get(PublishedAppDraftWorkspace, session.draft_workspace_id)
        if workspace is None or not str(workspace.sandbox_id or "").strip():
            session.status = PublishedAppDraftDevSessionStatus.error
            session.last_error = "Shared draft workspace is unavailable."
            return session

        now = self._now()
        session.last_activity_at = now
        session.expires_at = self._session_expires_at(now)
        workspace.last_activity_at = now
        workspace.detached_at = None
        try:
            heartbeat_result = await self.client.heartbeat_session(
                sandbox_id=str(workspace.sandbox_id),
                idle_timeout_seconds=self.settings.idle_timeout_seconds,
            )
        except PublishedAppDraftDevRuntimeClientError as exc:
            if self._is_runtime_not_running_error(exc):
                self._mark_workspace_error(workspace, exc)
                return self._mark_session_error(session, exc)
            if self._is_transient_remote_error(exc):
                self._mark_workspace_degraded(workspace, exc)
                return self._mark_session_degraded(session, exc)
            self._mark_workspace_error(workspace, exc)
            return self._mark_session_error(session, exc)

        if isinstance(heartbeat_result.get("backend_metadata"), dict):
            workspace.backend_metadata = self._merge_backend_metadata(
                existing_metadata=workspace.backend_metadata,
                refreshed_metadata=heartbeat_result.get("backend_metadata"),
                preview_base_path=(
                    str(workspace.preview_url or "").strip()
                    or str(session.preview_url or "").strip()
                ),
            )
        session.status = PublishedAppDraftDevSessionStatus.serving
        session.sandbox_id = self._normalize_runtime_sandbox_id(workspace.sandbox_id)
        session.backend_metadata = dict(workspace.backend_metadata or {})
        preview_build = workspace.backend_metadata.get("preview_build") if isinstance(workspace.backend_metadata, dict) else {}
        session.last_error = (
            (str(preview_build.get("last_error") or "").strip() or None)
            if isinstance(preview_build, dict) and not self._preview_build_current_available(preview_build)
            else None
        )
        app = await self.db.get(PublishedApp, session.published_app_id)
        if app is not None:
            await self._finalize_preview_runs_best_effort(app=app, workspace=workspace)
        return session

    async def get_publish_ready_session(
        self,
        *,
        app_id: UUID,
        user_id: UUID,
    ) -> Optional[PublishedAppDraftDevSession]:
        await self.expire_idle_sessions(app_id=app_id)
        session = await self.get_session(app_id=app_id, user_id=user_id)
        if session is None or not self._is_session_serving_status(session.status):
            return None
        if not str(session.sandbox_id or "").strip():
            return None
        return session

    async def stop_session(
        self,
        *,
        session: PublishedAppDraftDevSession,
        reason: PublishedAppDraftDevSessionStatus = PublishedAppDraftDevSessionStatus.stopped,
    ) -> PublishedAppDraftDevSession:
        apps_builder_trace(
            "session.detach.requested",
            domain="draft_dev.runtime",
            app_id=str(session.published_app_id),
            session_id=str(session.id),
            user_id=str(session.user_id),
            workspace_id=str(session.draft_workspace_id or ""),
            sandbox_id=str(session.sandbox_id or ""),
            reason=str(reason.value if hasattr(reason, "value") else reason),
        )
        workspace_id = session.draft_workspace_id
        session.status = reason
        session.draft_workspace_id = None
        session.sandbox_id = None
        session.backend_metadata = {}
        session.preview_url = None
        session.expires_at = self._now()
        session.last_error = None

        if workspace_id is not None:
            workspace = await self.db.get(PublishedAppDraftWorkspace, workspace_id)
            if workspace is not None:
                active_attachment_result = await self.db.execute(
                    select(func.count(PublishedAppDraftDevSession.id)).where(
                        and_(
                            PublishedAppDraftDevSession.draft_workspace_id == workspace_id,
                            PublishedAppDraftDevSession.status.in_(list(self._active_session_statuses())),
                        )
                    )
                )
                if int(active_attachment_result.scalar() or 0) <= 0:
                    workspace.detached_at = self._now()
        return session

    async def expire_idle_sessions(
        self,
        *,
        app_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> int:
        now = self._now()
        filters = [
            PublishedAppDraftDevSession.expires_at.is_not(None),
            PublishedAppDraftDevSession.expires_at <= now,
            PublishedAppDraftDevSession.status.in_(
                [
                    PublishedAppDraftDevSessionStatus.starting,
                    PublishedAppDraftDevSessionStatus.building,
                    PublishedAppDraftDevSessionStatus.serving,
                    PublishedAppDraftDevSessionStatus.degraded,
                    PublishedAppDraftDevSessionStatus.running,
                ]
            ),
        ]
        if app_id:
            filters.append(PublishedAppDraftDevSession.published_app_id == app_id)
        if user_id:
            filters.append(PublishedAppDraftDevSession.user_id == user_id)

        result = await self.db.execute(
            select(PublishedAppDraftDevSession).options(self._session_load_options()).where(and_(*filters))
        )
        rows = list(result.scalars().all())
        expired_count = 0
        for row in rows:
            active_publish_result = await self.db.execute(
                select(func.count(PublishedAppPublishJob.id)).where(
                    and_(
                        PublishedAppPublishJob.published_app_id == row.published_app_id,
                        PublishedAppPublishJob.status.in_(
                            [PublishedAppPublishJobStatus.queued, PublishedAppPublishJobStatus.running]
                        ),
                    )
                )
            )
            if int(active_publish_result.scalar() or 0) > 0:
                continue
            await self.stop_session(session=row, reason=PublishedAppDraftDevSessionStatus.expired)
            expired_count += 1
        return expired_count

    async def sweep_dormant_workspaces(self, *, app_id: UUID | None = None) -> int:
        now = self._now()
        cutoff = now - timedelta(seconds=self.settings.workspace_retention_seconds)
        attachment_exists = exists().where(
            and_(
                PublishedAppDraftDevSession.draft_workspace_id == PublishedAppDraftWorkspace.id,
                PublishedAppDraftDevSession.status.in_(list(self._active_session_statuses())),
            )
        )
        filters = [
            PublishedAppDraftWorkspace.detached_at.is_not(None),
            PublishedAppDraftWorkspace.detached_at <= cutoff,
            ~attachment_exists,
        ]
        if app_id is not None:
            filters.append(PublishedAppDraftWorkspace.published_app_id == app_id)
        result = await self.db.execute(
            select(PublishedAppDraftWorkspace).options(self._workspace_load_options()).where(and_(*filters))
        )
        removed = 0
        for workspace in result.scalars().all():
            publish_result = await self.db.execute(
                select(func.count(PublishedAppPublishJob.id)).where(
                    and_(
                        PublishedAppPublishJob.published_app_id == workspace.published_app_id,
                        PublishedAppPublishJob.status.in_(
                            [PublishedAppPublishJobStatus.queued, PublishedAppPublishJobStatus.running]
                        ),
                    )
                )
            )
            if int(publish_result.scalar() or 0) > 0:
                continue
            if str(workspace.sandbox_id or "").strip():
                try:
                    await self.client.stop_session(sandbox_id=str(workspace.sandbox_id))
                except PublishedAppDraftDevRuntimeClientError:
                    pass
            workspace.status = PublishedAppDraftWorkspaceStatus.stopped
            workspace.sandbox_id = None
            workspace.backend_metadata = {}
            workspace.preview_url = None
            workspace.last_error = None
            removed += 1
        return removed

    async def destroy_workspace_for_app(self, *, app_id: UUID) -> bool:
        workspace = await self.get_workspace(app_id=app_id)
        if workspace is None:
            return False
        if str(workspace.sandbox_id or "").strip():
            try:
                await self.client.stop_session(sandbox_id=str(workspace.sandbox_id))
            except PublishedAppDraftDevRuntimeClientError as exc:
                self._mark_workspace_degraded(workspace, exc)
        await self.db.delete(workspace)
        return True


def must_restartable_error(exc: Exception) -> bool:
    return PublishedAppDraftDevRuntimeService._is_runtime_not_running_error(exc)
