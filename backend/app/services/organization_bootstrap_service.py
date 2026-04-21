from __future__ import annotations

from uuid import UUID
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import Agent
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgUnit, OrgUnitType, Organization, User
from app.db.postgres.models.workspace import Project
from app.services.security_bootstrap_service import SecurityBootstrapService


class OrganizationBootstrapService:
    _ORG_DEFAULT_AGENT_SYSTEM_KEYS: tuple[str, ...] = ()
    _PROJECT_DEFAULT_AGENT_SYSTEM_KEYS = (
        "platform_architect",
        "artifact_coding_agent",
        "published_app_coding_agent",
    )

    def __init__(self, db: AsyncSession):
        self.db = db
        self.security = SecurityBootstrapService(db)

    @staticmethod
    def _internal_row_key(prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:20]}"

    async def _missing_agent_system_keys(
        self,
        *,
        organization_id: UUID,
        expected_system_keys: tuple[str, ...],
        project_id: UUID | None = None,
    ) -> set[str]:
        rows = await self.db.execute(
            select(Agent.system_key).where(
                Agent.organization_id == organization_id,
                Agent.project_id == project_id,
                Agent.system_key.in_(expected_system_keys),
            )
        )
        existing = {str(system_key) for system_key in rows.scalars().all() if system_key}
        return {system_key for system_key in expected_system_keys if system_key not in existing}

    async def create_organization_with_default_project(
        self,
        *,
        owner: User,
        name: str,
        project_name: str = "Default Project",
        workos_organization_id: str | None = None,
        workos_membership_id: str | None = None,
    ) -> tuple[Organization, Project]:
        organization = Organization(
            name=name,
            slug=self._internal_row_key("organization"),
            workos_organization_id=workos_organization_id,
        )
        self.db.add(organization)
        await self.db.flush()

        root_unit = OrgUnit(
            organization_id=organization.id,
            name=name,
            slug="root",
            system_key="root",
            type=OrgUnitType.org,
        )
        self.db.add(root_unit)
        await self.db.flush()

        membership = OrgMembership(
            organization_id=organization.id,
            user_id=owner.id,
            org_unit_id=root_unit.id,
            workos_membership_id=workos_membership_id,
            status=MembershipStatus.active,
        )
        self.db.add(membership)

        await self.security.ensure_default_roles(organization.id)
        await self.security.ensure_organization_owner_assignment(
            organization_id=organization.id,
            user_id=owner.id,
            assigned_by=owner.id,
        )
        project = await self.create_project(
            organization=organization,
            created_by=owner.id,
            name=project_name,
            is_default=True,
            owner_user_id=owner.id,
        )
        await self.db.flush()
        return organization, project

    async def create_project(
        self,
        *,
        organization: Organization,
        created_by: UUID | None,
        name: str,
        description: str | None = None,
        is_default: bool = False,
        owner_user_id: UUID | None = None,
    ) -> Project:
        project = Project(
            organization_id=organization.id,
            name=name,
            slug=self._internal_row_key("project"),
            description=description,
            is_default=is_default,
            created_by=created_by,
        )
        self.db.add(project)
        await self.db.flush()

        if owner_user_id is not None:
            await self.security.ensure_project_owner_assignment(
                organization_id=organization.id,
                project_id=project.id,
                user_id=owner_user_id,
                assigned_by=created_by or owner_user_id,
            )
        await self.ensure_project_default_agents(
            organization_id=organization.id,
            project_id=project.id,
            actor_user_id=created_by or owner_user_id,
        )
        await self.db.flush()
        return project

    async def ensure_organization_default_agents(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID | None = None,
    ) -> None:
        _ = organization_id, actor_user_id
        return None

    async def ensure_organization_default_agents_if_missing(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID | None = None,
    ) -> bool:
        _ = organization_id, actor_user_id
        return False

    async def ensure_project_default_agents(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        actor_user_id: UUID | None = None,
    ) -> None:
        from app.services.artifact_coding_agent_profile import ensure_artifact_coding_agent_profile
        from app.services.published_app_coding_agent_profile import ensure_coding_agent_profile
        from app.services.registry_seeding import ensure_platform_architect_agent

        await ensure_platform_architect_agent(
            self.db,
            organization_id,
            project_id=project_id,
            actor_user_id=actor_user_id,
        )
        await ensure_artifact_coding_agent_profile(
            self.db,
            organization_id,
            project_id=project_id,
            actor_user_id=actor_user_id,
        )
        await ensure_coding_agent_profile(
            self.db,
            organization_id,
            project_id=project_id,
            actor_user_id=actor_user_id,
        )

    async def ensure_project_default_agents_if_missing(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        actor_user_id: UUID | None = None,
    ) -> bool:
        missing = await self._missing_agent_system_keys(
            organization_id=organization_id,
            expected_system_keys=self._PROJECT_DEFAULT_AGENT_SYSTEM_KEYS,
            project_id=project_id,
        )
        if not missing:
            return False
        await self.ensure_project_default_agents(
            organization_id=organization_id,
            project_id=project_id,
            actor_user_id=actor_user_id,
        )
        return True
