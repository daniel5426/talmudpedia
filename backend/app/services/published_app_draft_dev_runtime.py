from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_published_app_draft_dev_token
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppDraftDevSession,
    PublishedAppDraftDevSessionStatus,
    PublishedAppRevision,
)
from app.services.published_app_draft_dev_runtime_client import (
    PublishedAppDraftDevRuntimeClient,
    PublishedAppDraftDevRuntimeClientError,
)


LOCKFILE_PATHS = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock")


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

    def _expires_at(self, now: Optional[datetime] = None) -> datetime:
        base = now or self._now()
        return base + timedelta(seconds=self.settings.idle_timeout_seconds)

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
            )
        )

    @staticmethod
    def _mark_session_error(session: PublishedAppDraftDevSession, exc: Exception) -> PublishedAppDraftDevSession:
        session.status = PublishedAppDraftDevSessionStatus.error
        session.last_error = str(exc)
        return session

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
        session.status = PublishedAppDraftDevSessionStatus.starting
        session.last_error = None
        session.sandbox_id = str(session.id)
        token = create_published_app_draft_dev_token(
            subject=str(user_id),
            tenant_id=str(app.tenant_id),
            app_id=str(app.id),
            user_id=str(user_id),
            session_id=str(session.id),
        )
        started = await self.client.start_session(
            session_id=str(session.id),
            tenant_id=str(app.tenant_id),
            app_id=str(app.id),
            user_id=str(user_id),
            revision_id=str(revision.id),
            entry_file=entry_value,
            files=files_payload,
            idle_timeout_seconds=self.settings.idle_timeout_seconds,
            dependency_hash=dependency_hash,
            draft_dev_token=token,
        )
        session.sandbox_id = str(started.get("sandbox_id") or session.id)
        session.preview_url = str(started.get("preview_url") or "")
        session.status = PublishedAppDraftDevSessionStatus.running
        session.dependency_hash = dependency_hash
        session.last_error = None
        return session

    async def get_session(self, *, app_id: UUID, user_id: UUID) -> Optional[PublishedAppDraftDevSession]:
        result = await self.db.execute(
            select(PublishedAppDraftDevSession).where(
                and_(
                    PublishedAppDraftDevSession.published_app_id == app_id,
                    PublishedAppDraftDevSession.user_id == user_id,
                )
            ).limit(1)
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

        now = self._now()
        await self.expire_idle_sessions(app_id=app.id, user_id=user_id)
        files_payload = dict(files or revision.files or {})
        entry_value = entry_file or revision.entry_file
        dependency_hash = self._dependency_hash(files_payload)
        session = await self.get_session(app_id=app.id, user_id=user_id)
        must_start = session is None or session.status in {
            PublishedAppDraftDevSessionStatus.stopped,
            PublishedAppDraftDevSessionStatus.expired,
            PublishedAppDraftDevSessionStatus.error,
        }
        if session is not None and session.expires_at and session.expires_at <= now:
            must_start = True
            session.status = PublishedAppDraftDevSessionStatus.expired

        if session is None:
            session = PublishedAppDraftDevSession(
                id=uuid4(),
                published_app_id=app.id,
                user_id=user_id,
                revision_id=revision.id,
                status=PublishedAppDraftDevSessionStatus.starting,
                idle_timeout_seconds=self.settings.idle_timeout_seconds,
                last_activity_at=now,
                expires_at=self._expires_at(now),
                dependency_hash=dependency_hash,
            )
            self.db.add(session)
            await self.db.flush()

        session.revision_id = revision.id
        session.idle_timeout_seconds = self.settings.idle_timeout_seconds
        session.last_activity_at = now
        session.expires_at = self._expires_at(now)

        if must_start:
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
            await self.client.sync_session(
                sandbox_id=session.sandbox_id,
                entry_file=entry_value,
                files=files_payload,
                idle_timeout_seconds=self.settings.idle_timeout_seconds,
                dependency_hash=dependency_hash,
                install_dependencies=install_dependencies,
            )
        except PublishedAppDraftDevRuntimeClientError as exc:
            if not self._is_runtime_not_running_error(exc):
                return self._mark_session_error(session, exc)
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
                return self._mark_session_error(session, restart_exc)

        session.status = PublishedAppDraftDevSessionStatus.running
        session.dependency_hash = dependency_hash
        session.last_error = None
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
            }
            or not session.sandbox_id
        ):
            must_start = True

        if must_start:
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

        if session.sandbox_id:
            try:
                await self.client.heartbeat_session(
                    sandbox_id=session.sandbox_id,
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
                return self._mark_session_error(session, exc)

        session.status = PublishedAppDraftDevSessionStatus.running
        session.last_error = None
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
                session.status = PublishedAppDraftDevSessionStatus.error
                session.last_error = str(exc)
                return session
        session.status = PublishedAppDraftDevSessionStatus.running
        session.last_error = None
        return session

    async def stop_session(
        self,
        *,
        session: PublishedAppDraftDevSession,
        reason: PublishedAppDraftDevSessionStatus = PublishedAppDraftDevSessionStatus.stopped,
    ) -> PublishedAppDraftDevSession:
        if session.sandbox_id:
            try:
                await self.client.stop_session(sandbox_id=session.sandbox_id)
            except PublishedAppDraftDevRuntimeClientError as exc:
                session.status = PublishedAppDraftDevSessionStatus.error
                session.last_error = str(exc)
                return session
        session.status = reason
        session.expires_at = self._now()
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
                    PublishedAppDraftDevSessionStatus.running,
                    PublishedAppDraftDevSessionStatus.starting,
                ]
            )
        )
        if app_id:
            filters.append(PublishedAppDraftDevSession.published_app_id == app_id)
        if user_id:
            filters.append(PublishedAppDraftDevSession.user_id == user_id)

        result = await self.db.execute(select(PublishedAppDraftDevSession).where(and_(*filters)))
        rows = list(result.scalars().all())
        for row in rows:
            await self.stop_session(session=row, reason=PublishedAppDraftDevSessionStatus.expired)
        return len(rows)
