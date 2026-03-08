from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.core.security import create_published_app_draft_dev_token
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppDraftDevSession,
    PublishedAppDraftDevSessionStatus,
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
_REMOTE_SWEEP_INTERVAL_SECONDS = max(30, int(os.getenv("APPS_DRAFT_DEV_REMOTE_SWEEP_INTERVAL_SECONDS", "120")))
_LAST_REMOTE_SWEEP_MONOTONIC = 0.0


@dataclass(frozen=True)
class DraftDevRuntimeSettings:
    enabled: bool
    idle_timeout_seconds: int
    hard_max_lifetime_seconds: int


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
        idle_timeout_seconds = min(max(idle_raw, 120), 300)
        hard_max_lifetime_seconds = max(hard_max_raw, idle_timeout_seconds)
        enabled = enabled_raw.strip().lower() not in {"0", "false", "off", "no"}
        return DraftDevRuntimeSettings(
            enabled=enabled,
            idle_timeout_seconds=idle_timeout_seconds,
            hard_max_lifetime_seconds=hard_max_lifetime_seconds,
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

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
    def _scope_lock_key(*, app_id: UUID, user_id: UUID) -> int:
        digest = hashlib.sha256(f"draft-dev:{app_id}:{user_id}".encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF

    async def _acquire_scope_lock(self, *, app_id: UUID, user_id: UUID) -> None:
        bind = self.db.get_bind()
        dialect_name = str(getattr(getattr(bind, "dialect", None), "name", "") or "").lower()
        if dialect_name == "sqlite":
            return
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": self._scope_lock_key(app_id=app_id, user_id=user_id)},
        )

    def _expires_at(self, now: Optional[datetime] = None) -> datetime:
        base = now or self._now()
        return base + timedelta(seconds=self.settings.idle_timeout_seconds)

    @staticmethod
    def _normalize_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

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
                "failed to connect to e2b sandbox",
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
            for token in (
                "connecttimeout",
                "temporarily unavailable",
                "connection reset",
                "connection aborted",
                "server disconnected",
                "502",
                "503",
                "504",
            )
        )

    @staticmethod
    def _mark_session_error(session: PublishedAppDraftDevSession, exc: Exception) -> PublishedAppDraftDevSession:
        session.status = PublishedAppDraftDevSessionStatus.error
        session.last_error = str(exc)
        return session

    @staticmethod
    def _mark_session_degraded(session: PublishedAppDraftDevSession, exc: Exception) -> PublishedAppDraftDevSession:
        session.status = PublishedAppDraftDevSessionStatus.degraded
        session.last_error = str(exc)
        return session

    @staticmethod
    def _is_session_serving_status(status: PublishedAppDraftDevSessionStatus | str | None) -> bool:
        value = str(getattr(status, "value", status) or "").strip().lower()
        return value in {
            PublishedAppDraftDevSessionStatus.serving.value,
            PublishedAppDraftDevSessionStatus.running.value,
        }

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
    def _runtime_generation_value(session: PublishedAppDraftDevSession) -> int:
        try:
            return int(getattr(session, "runtime_generation", 0) or 0)
        except Exception:
            return 0

    @staticmethod
    def _normalize_runtime_sandbox_id(raw: object) -> str | None:
        value = str(raw or "").strip()
        return value or None

    @staticmethod
    def _draft_session_load_only_options():
        return load_only(
            PublishedAppDraftDevSession.id,
            PublishedAppDraftDevSession.published_app_id,
            PublishedAppDraftDevSession.user_id,
            PublishedAppDraftDevSession.revision_id,
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

    async def _reconcile_remote_scope_best_effort(self, *, session: PublishedAppDraftDevSession) -> None:
        session_id = str(getattr(session, "id", "") or "").strip()
        if not session_id:
            return
        try:
            await self.client.reconcile_session_scope(
                session_id=session_id,
                expected_sandbox_id=self._normalize_runtime_sandbox_id(session.sandbox_id),
                runtime_generation=self._runtime_generation_value(session),
            )
        except PublishedAppDraftDevRuntimeClientError:
            return

    async def _build_active_remote_session_map(self) -> dict[str, dict[str, object]]:
        result = await self.db.execute(
            select(PublishedAppDraftDevSession)
            .options(
                load_only(
                    PublishedAppDraftDevSession.id,
                    PublishedAppDraftDevSession.sandbox_id,
                    PublishedAppDraftDevSession.runtime_generation,
                    PublishedAppDraftDevSession.runtime_backend,
                    PublishedAppDraftDevSession.status,
                )
            )
            .where(
                and_(
                    PublishedAppDraftDevSession.runtime_backend == self.client.backend_name,
                    PublishedAppDraftDevSession.status.in_(list(self._active_session_statuses())),
                )
            )
        )
        active_sessions: dict[str, dict[str, object]] = {}
        for row in result.scalars().all():
            session_id = str(getattr(row, "id", "") or "").strip()
            sandbox_id = self._normalize_runtime_sandbox_id(row.sandbox_id)
            if not session_id or not sandbox_id:
                continue
            active_sessions[session_id] = {
                "sandbox_id": sandbox_id,
                "runtime_generation": self._runtime_generation_value(row),
            }
        return active_sessions

    async def _sweep_remote_sessions_best_effort(self, *, force: bool = False) -> None:
        global _LAST_REMOTE_SWEEP_MONOTONIC
        if not bool(getattr(self.client, "is_remote_enabled", False)):
            return
        now_monotonic = time.monotonic()
        if not force and (now_monotonic - _LAST_REMOTE_SWEEP_MONOTONIC) < _REMOTE_SWEEP_INTERVAL_SECONDS:
            return
        _LAST_REMOTE_SWEEP_MONOTONIC = now_monotonic
        try:
            active_sessions = await self._build_active_remote_session_map()
            result = await self.client.sweep_remote_sessions(active_sessions=active_sessions)
            apps_builder_trace(
                "sandbox.remote_sweep",
                domain="draft_dev.runtime",
                force=bool(force),
                active_session_count=len(active_sessions),
                result=result,
                backend_name=self.client.backend_name,
            )
        except PublishedAppDraftDevRuntimeClientError:
            return

    async def _start_session_runtime(
        self,
        *,
        app: PublishedApp,
        revision: PublishedAppRevision,
        session: PublishedAppDraftDevSession,
        user_id: UUID,
        files_payload: Dict[str, str],
        entry_value: str,
        dependency_hash: str,
    ) -> PublishedAppDraftDevSession:
        apps_builder_trace(
            "sandbox.start.requested",
            domain="draft_dev.runtime",
            app_id=str(app.id),
            revision_id=str(revision.id),
            session_id=str(session.id),
            user_id=str(user_id),
            runtime_generation=self._runtime_generation_value(session) + 1,
            backend_name=self.client.backend_name,
            file_count=len(files_payload),
            dependency_hash=dependency_hash,
        )
        session.runtime_generation = self._runtime_generation_value(session) + 1
        session.status = PublishedAppDraftDevSessionStatus.building
        session.last_error = None
        session.sandbox_id = None
        session.backend_metadata = {}
        session.runtime_backend = self.client.backend_name
        token = create_published_app_draft_dev_token(
            subject=str(user_id),
            tenant_id=str(app.tenant_id),
            app_id=str(app.id),
            user_id=str(user_id),
            session_id=str(session.id),
        )
        preview_base_path = self.client.build_preview_proxy_path(str(session.id))
        last_exc: PublishedAppDraftDevRuntimeClientError | None = None
        started: dict[str, object] | None = None
        for attempt in range(2):
            try:
                started = await self.client.start_session(
                    session_id=str(session.id),
                    runtime_generation=self._runtime_generation_value(session),
                    tenant_id=str(app.tenant_id),
                    app_id=str(app.id),
                    user_id=str(user_id),
                    revision_id=str(revision.id),
                    entry_file=entry_value,
                    files=files_payload,
                    idle_timeout_seconds=self.settings.idle_timeout_seconds,
                    dependency_hash=dependency_hash,
                    draft_dev_token=token,
                    preview_base_path=preview_base_path,
                )
                break
            except PublishedAppDraftDevRuntimeClientError as exc:
                last_exc = exc
                if attempt == 0 and self._is_timeout_error(exc):
                    await asyncio.sleep(0.25)
                    continue
                raise
        if started is None:
            if last_exc is not None:
                raise last_exc
            raise PublishedAppDraftDevRuntimeClientError("Failed to start draft dev session")
        session.sandbox_id = self._normalize_runtime_sandbox_id(started.get("sandbox_id"))
        if not session.sandbox_id:
            raise PublishedAppDraftDevRuntimeClientError(
                "Draft dev runtime start returned without a sandbox id."
            )
        session.runtime_backend = str(started.get("runtime_backend") or self.client.backend_name)
        session.backend_metadata = dict(started.get("backend_metadata") or {})
        session.preview_url = preview_base_path
        session.status = PublishedAppDraftDevSessionStatus.serving
        session.dependency_hash = dependency_hash
        session.last_error = None
        apps_builder_trace(
            "sandbox.start.confirmed",
            domain="draft_dev.runtime",
            app_id=str(app.id),
            revision_id=str(revision.id),
            session_id=str(session.id),
            user_id=str(user_id),
            sandbox_id=str(session.sandbox_id or ""),
            runtime_generation=self._runtime_generation_value(session),
            backend_name=session.runtime_backend,
            status=str(session.status.value if hasattr(session.status, "value") else session.status),
            backend_metadata=session.backend_metadata,
        )
        await self._reconcile_remote_scope_best_effort(session=session)
        return session

    async def get_session(self, *, app_id: UUID, user_id: UUID) -> Optional[PublishedAppDraftDevSession]:
        result = await self.db.execute(
            select(PublishedAppDraftDevSession)
            .options(self._draft_session_load_only_options())
            .where(
                and_(
                    PublishedAppDraftDevSession.published_app_id == app_id,
                    PublishedAppDraftDevSession.user_id == user_id,
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

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
        await self._sweep_remote_sessions_best_effort()
        await self.expire_idle_sessions(app_id=app.id, user_id=user_id)
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
        session = await self.get_session(app_id=app.id, user_id=user_id)
        apps_builder_trace(
            "session.ensure.requested",
            domain="draft_dev.runtime",
            app_id=str(app.id),
            revision_id=str(revision.id),
            user_id=str(user_id),
            existing_session_id=str(getattr(session, "id", "") or "") or None,
            existing_sandbox_id=str(getattr(session, "sandbox_id", "") or "") or None,
            existing_status=(
                str(getattr(getattr(session, "status", None), "value", getattr(session, "status", None)) or "")
                or None
            ),
            backend_name=self.client.backend_name,
            dependency_hash=dependency_hash,
            file_count=len(files_payload),
        )

        if session is None:
            candidate_session = PublishedAppDraftDevSession(
                id=uuid4(),
                published_app_id=app.id,
                user_id=user_id,
                revision_id=revision.id,
                status=PublishedAppDraftDevSessionStatus.starting,
                runtime_backend=self.client.backend_name,
                backend_metadata={},
                idle_timeout_seconds=self.settings.idle_timeout_seconds,
                last_activity_at=now,
                expires_at=self._expires_at(now),
                dependency_hash=dependency_hash,
                runtime_generation=0,
            )
            try:
                # Another request can concurrently ensure the same (app_id, user_id)
                # scope; preserve API stability by reusing the winning row.
                async with self.db.begin_nested():
                    self.db.add(candidate_session)
                    await self.db.flush()
                session = candidate_session
                apps_builder_trace(
                    "session.ensure.created_row",
                    domain="draft_dev.runtime",
                    app_id=str(app.id),
                    revision_id=str(revision.id),
                    user_id=str(user_id),
                    session_id=str(candidate_session.id),
                    backend_name=self.client.backend_name,
                )
            except IntegrityError:
                session = await self.get_session(app_id=app.id, user_id=user_id)
                if session is None:
                    raise

        must_start = session.status in {
            PublishedAppDraftDevSessionStatus.stopped,
            PublishedAppDraftDevSessionStatus.expired,
            PublishedAppDraftDevSessionStatus.error,
            PublishedAppDraftDevSessionStatus.stopping,
            PublishedAppDraftDevSessionStatus.degraded,
        }
        session_expires_at = self._normalize_utc(session.expires_at)
        if session_expires_at and session_expires_at <= now:
            must_start = True
            session.status = PublishedAppDraftDevSessionStatus.expired

        session.revision_id = revision.id
        session.idle_timeout_seconds = self.settings.idle_timeout_seconds
        session.last_activity_at = now
        session.expires_at = self._expires_at(now)
        session.preview_url = self.client.build_preview_proxy_path(str(session.id))

        if must_start:
            apps_builder_trace(
                "session.ensure.start_required",
                domain="draft_dev.runtime",
                app_id=str(app.id),
                revision_id=str(revision.id),
                session_id=str(session.id),
                user_id=str(user_id),
                existing_sandbox_id=str(session.sandbox_id or ""),
                existing_status=str(getattr(session.status, "value", session.status) or ""),
            )
            try:
                return await self._start_session_runtime(
                    app=app,
                    revision=revision,
                    session=session,
                    user_id=user_id,
                    files_payload=files_payload,
                    entry_value=entry_value,
                    dependency_hash=dependency_hash,
                )
            except PublishedAppDraftDevRuntimeClientError as exc:
                apps_builder_trace(
                    "session.ensure.start_failed",
                    domain="draft_dev.runtime",
                    app_id=str(app.id),
                    revision_id=str(revision.id),
                    session_id=str(session.id),
                    user_id=str(user_id),
                    error=str(exc),
                )
                return self._mark_session_error(session, exc)

        install_dependencies = dependency_hash != (session.dependency_hash or "")
        if not session.sandbox_id:
            try:
                return await self._start_session_runtime(
                    app=app,
                    revision=revision,
                    session=session,
                    user_id=user_id,
                    files_payload=files_payload,
                    entry_value=entry_value,
                    dependency_hash=dependency_hash,
                )
            except PublishedAppDraftDevRuntimeClientError as exc:
                return self._mark_session_error(session, exc)

        try:
            session.status = (
                PublishedAppDraftDevSessionStatus.building
                if install_dependencies
                else PublishedAppDraftDevSessionStatus.starting
            )
            sync_result = await self.client.sync_session(
                sandbox_id=session.sandbox_id,
                entry_file=entry_value,
                files=files_payload,
                idle_timeout_seconds=self.settings.idle_timeout_seconds,
                dependency_hash=dependency_hash,
                install_dependencies=install_dependencies,
                preview_base_path=session.preview_url or self.client.build_preview_proxy_path(str(session.id)),
            )
        except PublishedAppDraftDevRuntimeClientError as exc:
            if not self._is_runtime_not_running_error(exc):
                apps_builder_trace(
                    "session.ensure.sync_degraded",
                    domain="draft_dev.runtime",
                    app_id=str(app.id),
                    revision_id=str(revision.id),
                    session_id=str(session.id),
                    user_id=str(user_id),
                    sandbox_id=str(session.sandbox_id or ""),
                    error=str(exc),
                )
                return self._mark_session_degraded(session, exc)
            try:
                return await self._start_session_runtime(
                    app=app,
                    revision=revision,
                    session=session,
                    user_id=user_id,
                    files_payload=files_payload,
                    entry_value=entry_value,
                    dependency_hash=dependency_hash,
                )
            except PublishedAppDraftDevRuntimeClientError as restart_exc:
                apps_builder_trace(
                    "session.ensure.restart_failed",
                    domain="draft_dev.runtime",
                    app_id=str(app.id),
                    revision_id=str(revision.id),
                    session_id=str(session.id),
                    user_id=str(user_id),
                    sandbox_id=str(session.sandbox_id or ""),
                    error=str(restart_exc),
                )
                return self._mark_session_error(session, restart_exc)

        session.status = PublishedAppDraftDevSessionStatus.serving
        session.runtime_backend = str(sync_result.get("runtime_backend") or session.runtime_backend or self.client.backend_name)
        if isinstance(sync_result.get("backend_metadata"), dict):
            session.backend_metadata = dict(sync_result.get("backend_metadata") or {})
        session.dependency_hash = dependency_hash
        session.last_error = None
        apps_builder_trace(
            "session.ensure.synced",
            domain="draft_dev.runtime",
            app_id=str(app.id),
            revision_id=str(revision.id),
            session_id=str(session.id),
            user_id=str(user_id),
            sandbox_id=str(session.sandbox_id or ""),
            backend_name=session.runtime_backend,
            install_dependencies=bool(install_dependencies),
            sync_result=sync_result,
        )
        await self._reconcile_remote_scope_best_effort(session=session)
        return session

    async def ensure_active_session(
        self,
        *,
        app: PublishedApp,
        revision: PublishedAppRevision,
        user_id: UUID,
    ) -> PublishedAppDraftDevSession:
        """
        Ensure an active sandbox session for tool execution without force-syncing
        files from DB on every call.
        """
        if not self.settings.enabled:
            raise PublishedAppDraftDevRuntimeDisabled("Draft dev mode is disabled (`APPS_BUILDER_DRAFT_DEV_ENABLED=0`).")
        if not user_id:
            raise self._scope_error()

        now = self._now()
        await self.expire_idle_sessions(app_id=app.id, user_id=user_id)
        session = await self.get_session(app_id=app.id, user_id=user_id)
        must_start = session is None

        if session is not None and session.expires_at and session.expires_at <= now:
            must_start = True
            session.status = PublishedAppDraftDevSessionStatus.expired

        if session is not None and (
            session.status in {
                PublishedAppDraftDevSessionStatus.stopped,
                PublishedAppDraftDevSessionStatus.expired,
                PublishedAppDraftDevSessionStatus.error,
                PublishedAppDraftDevSessionStatus.degraded,
                PublishedAppDraftDevSessionStatus.stopping,
            }
            or not session.sandbox_id
        ):
            must_start = True

        if must_start:
            apps_builder_trace(
                "session.ensure_active.restart_required",
                domain="draft_dev.runtime",
                app_id=str(app.id),
                revision_id=str(revision.id),
                user_id=str(user_id),
                existing_session_id=str(getattr(session, "id", "") or "") or None,
                existing_sandbox_id=str(getattr(session, "sandbox_id", "") or "") or None,
            )
            return await self.ensure_session(
                app=app,
                revision=revision,
                user_id=user_id,
                files=dict(revision.files or {}),
                entry_file=revision.entry_file,
            )

        session.revision_id = revision.id
        session.idle_timeout_seconds = self.settings.idle_timeout_seconds
        session.last_activity_at = now
        session.expires_at = self._expires_at(now)
        session.preview_url = self.client.build_preview_proxy_path(str(session.id))

        if session.sandbox_id:
            try:
                await self.client.heartbeat_session(
                    sandbox_id=session.sandbox_id,
                    idle_timeout_seconds=self.settings.idle_timeout_seconds,
                )
            except PublishedAppDraftDevRuntimeClientError as exc:
                if self._is_runtime_not_running_error(exc):
                    apps_builder_trace(
                        "session.ensure_active.heartbeat_restart",
                        domain="draft_dev.runtime",
                        app_id=str(app.id),
                        revision_id=str(revision.id),
                        session_id=str(session.id),
                        user_id=str(user_id),
                        sandbox_id=str(session.sandbox_id or ""),
                        error=str(exc),
                    )
                    return await self.ensure_session(
                        app=app,
                        revision=revision,
                        user_id=user_id,
                        files=dict(revision.files or {}),
                        entry_file=revision.entry_file,
                    )
                apps_builder_trace(
                    "session.ensure_active.heartbeat_degraded",
                    domain="draft_dev.runtime",
                    app_id=str(app.id),
                    revision_id=str(revision.id),
                    session_id=str(session.id),
                    user_id=str(user_id),
                    sandbox_id=str(session.sandbox_id or ""),
                    error=str(exc),
                )
                return self._mark_session_degraded(session, exc)

        if not session.sandbox_id:
            session.status = PublishedAppDraftDevSessionStatus.error
            session.last_error = "Draft dev session is missing a sandbox id."
            return session

        session.status = PublishedAppDraftDevSessionStatus.serving
        session.last_error = None
        apps_builder_trace(
            "session.ensure_active.ready",
            domain="draft_dev.runtime",
            app_id=str(app.id),
            revision_id=str(revision.id),
            session_id=str(session.id),
            user_id=str(user_id),
            sandbox_id=str(session.sandbox_id or ""),
            backend_name=session.runtime_backend,
            status=str(session.status.value if hasattr(session.status, "value") else session.status),
        )
        await self._reconcile_remote_scope_best_effort(session=session)
        return session

    async def sync_session(
        self,
        *,
        app: PublishedApp,
        revision: PublishedAppRevision,
        user_id: UUID,
        files: Dict[str, str],
        entry_file: str,
    ) -> PublishedAppDraftDevSession:
        session = await self.ensure_session(
            app=app,
            revision=revision,
            user_id=user_id,
            files=files,
            entry_file=entry_file,
        )
        return session

    async def heartbeat_session(self, *, session: PublishedAppDraftDevSession) -> PublishedAppDraftDevSession:
        if not self.settings.enabled:
            raise PublishedAppDraftDevRuntimeDisabled("Draft dev mode is disabled (`APPS_BUILDER_DRAFT_DEV_ENABLED=0`).")
        now = self._now()
        session.last_activity_at = now
        session.expires_at = self._expires_at(now)
        if session.sandbox_id:
            try:
                await self.client.heartbeat_session(
                    sandbox_id=session.sandbox_id,
                    idle_timeout_seconds=self.settings.idle_timeout_seconds,
                )
            except PublishedAppDraftDevRuntimeClientError as exc:
                if self._is_runtime_not_running_error(exc):
                    session.status = PublishedAppDraftDevSessionStatus.error
                    session.last_error = str(exc)
                    return session
                if self._is_transient_remote_error(exc):
                    apps_builder_trace(
                        "session.heartbeat.transient_error_ignored",
                        domain="draft_dev.runtime",
                        app_id=str(session.published_app_id),
                        revision_id=str(session.revision_id or ""),
                        session_id=str(session.id),
                        sandbox_id=str(session.sandbox_id or ""),
                        error=str(exc),
                    )
                    session.status = PublishedAppDraftDevSessionStatus.serving
                    session.last_error = str(exc)
                    return session
                return self._mark_session_degraded(session, exc)
        if not session.sandbox_id:
            session.status = PublishedAppDraftDevSessionStatus.error
            session.last_error = "Draft dev session is missing a sandbox id."
            return session

        session.status = PublishedAppDraftDevSessionStatus.serving
        session.last_error = None
        await self._reconcile_remote_scope_best_effort(session=session)
        return session

    async def get_publish_ready_session(
        self,
        *,
        app_id: UUID,
        user_id: UUID,
    ) -> Optional[PublishedAppDraftDevSession]:
        await self.expire_idle_sessions(app_id=app_id, user_id=user_id)
        session = await self.get_session(app_id=app_id, user_id=user_id)
        if session is None:
            return None
        if not self._is_session_serving_status(session.status):
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
            "session.stop.requested",
            domain="draft_dev.runtime",
            app_id=str(session.published_app_id),
            session_id=str(session.id),
            user_id=str(session.user_id),
            sandbox_id=str(session.sandbox_id or ""),
            reason=str(reason.value if hasattr(reason, "value") else reason),
            backend_name=str(session.runtime_backend or self.client.backend_name),
        )
        session.status = PublishedAppDraftDevSessionStatus.stopping
        if session.sandbox_id:
            try:
                await self.client.stop_session(sandbox_id=session.sandbox_id)
            except PublishedAppDraftDevRuntimeClientError as exc:
                session.status = PublishedAppDraftDevSessionStatus.error
                session.last_error = str(exc)
                apps_builder_trace(
                    "session.stop.failed",
                    domain="draft_dev.runtime",
                    app_id=str(session.published_app_id),
                    session_id=str(session.id),
                    user_id=str(session.user_id),
                    sandbox_id=str(session.sandbox_id or ""),
                    error=str(exc),
                )
                return session
        session.sandbox_id = None
        session.backend_metadata = {}
        session.status = reason
        session.expires_at = self._now()
        apps_builder_trace(
            "session.stop.completed",
            domain="draft_dev.runtime",
            app_id=str(session.published_app_id),
            session_id=str(session.id),
            user_id=str(session.user_id),
            reason=str(reason.value if hasattr(reason, "value") else reason),
        )
        await self._reconcile_remote_scope_best_effort(session=session)
        return session

    async def expire_idle_sessions(
        self,
        *,
        app_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
    ) -> int:
        now = self._now()
        filters = [PublishedAppDraftDevSession.expires_at.is_not(None)]
        filters.append(PublishedAppDraftDevSession.expires_at <= now)
        filters.append(
            PublishedAppDraftDevSession.status.in_(
                [
                    PublishedAppDraftDevSessionStatus.starting,
                    PublishedAppDraftDevSessionStatus.building,
                    PublishedAppDraftDevSessionStatus.serving,
                    PublishedAppDraftDevSessionStatus.degraded,
                    PublishedAppDraftDevSessionStatus.running,
                ]
            )
        )
        if app_id:
            filters.append(PublishedAppDraftDevSession.published_app_id == app_id)
        if user_id:
            filters.append(PublishedAppDraftDevSession.user_id == user_id)

        result = await self.db.execute(
            select(PublishedAppDraftDevSession)
            .options(self._draft_session_load_only_options())
            .where(and_(*filters))
        )
        rows = list(result.scalars().all())
        expired_count = 0
        for row in rows:
            active_publish_result = await self.db.execute(
                select(func.count(PublishedAppPublishJob.id)).where(
                    and_(
                        PublishedAppPublishJob.published_app_id == row.published_app_id,
                        PublishedAppPublishJob.status.in_(
                            [
                                PublishedAppPublishJobStatus.queued,
                                PublishedAppPublishJobStatus.running,
                            ]
                        ),
                    )
                )
            )
            if int(active_publish_result.scalar() or 0) > 0:
                continue
            await self.stop_session(session=row, reason=PublishedAppDraftDevSessionStatus.expired)
            expired_count += 1
        if expired_count:
            apps_builder_trace(
                "session.expire.completed",
                domain="draft_dev.runtime",
                app_id=str(app_id) if app_id else None,
                user_id=str(user_id) if user_id else None,
                expired_count=expired_count,
            )
        return expired_count
