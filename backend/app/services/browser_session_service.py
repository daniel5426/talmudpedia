from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.identity import OrgMembership, Tenant, User
from app.db.postgres.models.workspace import BrowserSession, BrowserSessionStatus, Project, ProjectStatus


SESSION_COOKIE_NAME = "talmudpedia_session"
SESSION_TTL_DAYS = 30


class BrowserSessionError(Exception):
    pass


class BrowserSessionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @staticmethod
    def _generate_raw_token() -> str:
        return secrets.token_urlsafe(48)

    async def create_session(
        self,
        *,
        user: User,
        organization: Tenant,
        project: Project,
    ) -> tuple[BrowserSession, str]:
        raw_token = self._generate_raw_token()
        session = BrowserSession(
            user_id=user.id,
            organization_id=organization.id,
            project_id=project.id,
            token_hash=self._hash_token(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS),
            status=BrowserSessionStatus.active,
        )
        self.db.add(session)
        await self.db.flush()
        return session, raw_token

    async def resolve_session(self, raw_token: str) -> BrowserSession | None:
        token_hash = self._hash_token(raw_token)
        session = (
            await self.db.execute(
                select(BrowserSession).where(BrowserSession.token_hash == token_hash).limit(1)
            )
        ).scalar_one_or_none()
        if session is None:
            return None
        if session.status != BrowserSessionStatus.active:
            return None
        expiry = session.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= datetime.now(timezone.utc):
            return None
        session.last_seen_at = datetime.now(timezone.utc)
        await self.db.flush()
        return session

    async def revoke_session(self, raw_token: str) -> None:
        session = await self.resolve_session(raw_token)
        if session is None:
            return
        session.status = BrowserSessionStatus.revoked
        session.revoked_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def switch_organization(
        self,
        *,
        session: BrowserSession,
        organization_id: UUID,
    ) -> BrowserSession:
        membership = (
            await self.db.execute(
                select(OrgMembership).where(
                    and_(
                        OrgMembership.user_id == session.user_id,
                        OrgMembership.tenant_id == organization_id,
                    )
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise BrowserSessionError("User is not a member of this organization")

        project = await self._default_project_for_organization(organization_id)
        if project is None:
            raise BrowserSessionError("Organization has no active project")

        session.organization_id = organization_id
        session.project_id = project.id
        session.last_seen_at = datetime.now(timezone.utc)
        await self.db.flush()
        return session

    async def switch_project(
        self,
        *,
        session: BrowserSession,
        project_id: UUID,
    ) -> BrowserSession:
        project = (
            await self.db.execute(
                select(Project).where(
                    and_(
                        Project.id == project_id,
                        Project.organization_id == session.organization_id,
                    )
                )
            )
        ).scalar_one_or_none()
        if project is None:
            raise BrowserSessionError("Project not found in active organization")
        session.project_id = project.id
        session.last_seen_at = datetime.now(timezone.utc)
        await self.db.flush()
        return session

    async def _default_project_for_organization(self, organization_id: UUID) -> Project | None:
        project = (
            await self.db.execute(
                select(Project)
                .where(
                    and_(
                        Project.organization_id == organization_id,
                        Project.status == ProjectStatus.active,
                        Project.is_default == True,  # noqa: E712
                    )
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if project is not None:
            return project
        return (
            await self.db.execute(
                select(Project)
                .where(and_(Project.organization_id == organization_id, Project.status == ProjectStatus.active))
                .order_by(Project.created_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
