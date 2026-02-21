from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_published_app_draft_dev_token
from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppCodingRunSandboxSession,
    PublishedAppCodingRunSandboxStatus,
    PublishedAppRevision,
)
from app.services.published_app_draft_dev_runtime_client import (
    PublishedAppDraftDevRuntimeClient,
    PublishedAppDraftDevRuntimeClientError,
)


LOCKFILE_PATHS = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock")


@dataclass(frozen=True)
class CodingRunSandboxSettings:
    required: bool
    idle_timeout_seconds: int
    run_timeout_seconds: int


class PublishedAppCodingRunSandboxError(Exception):
    pass


class PublishedAppCodingRunSandboxService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = PublishedAppDraftDevRuntimeClient.from_env()
        self.settings = self._load_settings()

    @staticmethod
    def _load_settings() -> CodingRunSandboxSettings:
        required_raw = (os.getenv("APPS_CODING_AGENT_SANDBOX_REQUIRED") or "0").strip().lower()
        idle_raw = int((os.getenv("APPS_CODING_AGENT_SANDBOX_IDLE_TIMEOUT_SECONDS") or "180").strip())
        run_raw = int((os.getenv("APPS_CODING_AGENT_SANDBOX_RUN_TIMEOUT_SECONDS") or "1200").strip())
        return CodingRunSandboxSettings(
            required=required_raw in {"1", "true", "yes", "on"},
            idle_timeout_seconds=max(60, idle_raw),
            run_timeout_seconds=max(180, run_raw),
        )

    @property
    def is_controller_enabled(self) -> bool:
        return bool(self.client.is_remote_enabled)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def _expires_at(self, now: Optional[datetime] = None) -> datetime:
        return (now or self._now()) + timedelta(seconds=self.settings.idle_timeout_seconds)

    @staticmethod
    def _dependency_hash(files: dict[str, str]) -> str:
        dependency_files: dict[str, str] = {}
        package_json = files.get("package.json")
        if isinstance(package_json, str):
            dependency_files["package.json"] = package_json
        for lockfile_path in LOCKFILE_PATHS:
            lockfile = files.get(lockfile_path)
            if isinstance(lockfile, str):
                dependency_files[lockfile_path] = lockfile
        serialized = json.dumps(dependency_files, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    async def get_session_for_run(self, *, run_id: UUID) -> PublishedAppCodingRunSandboxSession | None:
        result = await self.db.execute(
            select(PublishedAppCodingRunSandboxSession)
            .where(PublishedAppCodingRunSandboxSession.run_id == run_id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def ensure_session(
        self,
        *,
        run: AgentRun,
        app: PublishedApp,
        revision: PublishedAppRevision,
        actor_id: UUID | None,
        controller_session_id: str | None = None,
    ) -> PublishedAppCodingRunSandboxSession:
        await self.reap_expired_sessions(limit=20)
        now = self._now()
        session = await self.get_session_for_run(run_id=run.id)
        effective_controller_session_id = str(controller_session_id or run.id).strip() or str(run.id)

        if session is None:
            session = PublishedAppCodingRunSandboxSession(
                id=uuid4(),
                run_id=run.id,
                tenant_id=app.tenant_id,
                published_app_id=app.id,
                revision_id=revision.id,
                user_id=actor_id,
                status=PublishedAppCodingRunSandboxStatus.starting,
                idle_timeout_seconds=self.settings.idle_timeout_seconds,
                run_timeout_seconds=self.settings.run_timeout_seconds,
                started_at=None,
                expires_at=self._expires_at(now),
                last_activity_at=now,
            )
            self.db.add(session)
            await self.db.flush()

        if (
            session.status == PublishedAppCodingRunSandboxStatus.running
            and session.sandbox_id
            and session.expires_at
            and session.expires_at > now
        ):
            try:
                await self.client.heartbeat_session(
                    sandbox_id=session.sandbox_id,
                    idle_timeout_seconds=self.settings.idle_timeout_seconds,
                )
            except PublishedAppDraftDevRuntimeClientError as exc:
                session.status = PublishedAppCodingRunSandboxStatus.error
                session.last_error = str(exc)
                return session
            session.last_activity_at = now
            session.expires_at = self._expires_at(now)
            session.last_error = None
            return session

        files_payload = dict(revision.files or {})
        entry_value = revision.entry_file
        dependency_hash = self._dependency_hash(files_payload)
        token = create_published_app_draft_dev_token(
            subject=str(actor_id or run.id),
            tenant_id=str(app.tenant_id),
            app_id=str(app.id),
            user_id=str(actor_id or run.id),
            session_id=effective_controller_session_id,
        )

        try:
            started = await self.client.start_session(
                session_id=effective_controller_session_id,
                tenant_id=str(app.tenant_id),
                app_id=str(app.id),
                user_id=str(actor_id or run.id),
                revision_id=str(revision.id),
                entry_file=entry_value,
                files=files_payload,
                idle_timeout_seconds=self.settings.idle_timeout_seconds,
                dependency_hash=dependency_hash,
                draft_dev_token=token,
            )
        except PublishedAppDraftDevRuntimeClientError as exc:
            session.status = PublishedAppCodingRunSandboxStatus.error
            session.last_error = str(exc)
            session.last_activity_at = now
            session.expires_at = now
            return session

        sandbox_id = str(started.get("sandbox_id") or effective_controller_session_id)
        session.status = PublishedAppCodingRunSandboxStatus.running
        session.sandbox_id = sandbox_id
        session.preview_url = str(started.get("preview_url") or "")
        session.revision_id = revision.id
        session.user_id = actor_id
        session.last_error = None
        session.started_at = session.started_at or now
        session.last_activity_at = now
        session.expires_at = self._expires_at(now)
        session.dependency_hash = dependency_hash
        session.stopped_at = None

        workspace_path = str(started.get("workspace_path") or "").strip()
        if not workspace_path:
            workspace_path = str(await self.client.resolve_local_workspace_path(sandbox_id=sandbox_id) or "").strip()
        session.workspace_path = workspace_path or session.workspace_path or "/workspace"
        return session

    async def keep_session_warm_for_run(
        self,
        *,
        run_id: UUID,
    ) -> PublishedAppCodingRunSandboxSession | None:
        session = await self.get_session_for_run(run_id=run_id)
        if session is None:
            return None
        now = self._now()
        if session.sandbox_id:
            try:
                await self.client.heartbeat_session(
                    sandbox_id=session.sandbox_id,
                    idle_timeout_seconds=self.settings.idle_timeout_seconds,
                )
            except PublishedAppDraftDevRuntimeClientError as exc:
                session.status = PublishedAppCodingRunSandboxStatus.error
                session.last_error = str(exc)
                session.last_activity_at = now
                session.expires_at = now
                return session
        session.status = PublishedAppCodingRunSandboxStatus.running
        session.stopped_at = None
        session.last_activity_at = now
        session.expires_at = self._expires_at(now)
        session.last_error = None
        return session

    async def reap_expired_sessions(self, *, limit: int = 20) -> int:
        now = self._now()
        result = await self.db.execute(
            select(PublishedAppCodingRunSandboxSession)
            .where(
                and_(
                    PublishedAppCodingRunSandboxSession.status == PublishedAppCodingRunSandboxStatus.running,
                    PublishedAppCodingRunSandboxSession.expires_at.is_not(None),
                    PublishedAppCodingRunSandboxSession.expires_at <= now,
                    PublishedAppCodingRunSandboxSession.sandbox_id.is_not(None),
                )
            )
            .order_by(PublishedAppCodingRunSandboxSession.expires_at.asc())
            .limit(max(1, int(limit)))
        )
        sessions = list(result.scalars().all())
        reaped = 0
        for session in sessions:
            if session.sandbox_id:
                try:
                    await self.client.stop_session(sandbox_id=session.sandbox_id)
                except PublishedAppDraftDevRuntimeClientError as exc:
                    session.status = PublishedAppCodingRunSandboxStatus.error
                    session.last_error = str(exc)
                    session.last_activity_at = now
                    session.expires_at = now
                    continue
            session.status = PublishedAppCodingRunSandboxStatus.expired
            session.stopped_at = now
            session.last_activity_at = now
            session.expires_at = now
            session.last_error = None
            reaped += 1
        return reaped

    async def stop_session_for_run(
        self,
        *,
        run_id: UUID,
        reason: PublishedAppCodingRunSandboxStatus = PublishedAppCodingRunSandboxStatus.stopped,
    ) -> PublishedAppCodingRunSandboxSession | None:
        session = await self.get_session_for_run(run_id=run_id)
        if session is None:
            return None
        now = self._now()
        if session.sandbox_id:
            try:
                await self.client.stop_session(sandbox_id=session.sandbox_id)
            except PublishedAppDraftDevRuntimeClientError as exc:
                session.status = PublishedAppCodingRunSandboxStatus.error
                session.last_error = str(exc)
                session.last_activity_at = now
                session.expires_at = now
                return session
        session.status = reason
        session.stopped_at = now
        session.last_activity_at = now
        session.expires_at = now
        session.last_error = None
        return session

    @staticmethod
    def serialize(session: PublishedAppCodingRunSandboxSession | None) -> dict[str, object]:
        if session is None:
            return {
                "sandbox_id": None,
                "sandbox_status": None,
                "sandbox_started_at": None,
                "sandbox_workspace_path": None,
            }
        status = session.status.value if hasattr(session.status, "value") else str(session.status)
        return {
            "sandbox_id": str(session.sandbox_id) if session.sandbox_id else None,
            "sandbox_status": status,
            "sandbox_started_at": session.started_at,
            "sandbox_workspace_path": session.workspace_path,
        }
