from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import Agent
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.db.postgres.models.workspace import Project
from app.services.security_bootstrap_service import SecurityBootstrapService


class OrganizationBootstrapService:
    _ORG_DEFAULT_AGENT_SLUGS = ("platform-architect",)
    _PROJECT_DEFAULT_AGENT_SLUGS = ("artifact-coding-agent", "published-app-coding-agent")

    def __init__(self, db: AsyncSession):
        self.db = db
        self.security = SecurityBootstrapService(db)

    async def _missing_agent_slugs(
        self,
        *,
        organization_id: UUID,
        expected_slugs: tuple[str, ...],
    ) -> set[str]:
        rows = await self.db.execute(
            select(Agent.slug).where(
                Agent.tenant_id == organization_id,
                Agent.slug.in_(expected_slugs),
            )
        )
        existing = {str(slug) for slug in rows.scalars().all()}
        return {slug for slug in expected_slugs if slug not in existing}

    async def create_organization_with_default_project(
        self,
        *,
        owner: User,
        name: str,
        slug: str,
        project_name: str = "Default Project",
        project_slug: str = "default",
        workos_organization_id: str | None = None,
        workos_membership_id: str | None = None,
    ) -> tuple[Tenant, Project]:
        organization = Tenant(name=name, slug=slug, workos_organization_id=workos_organization_id)
        self.db.add(organization)
        await self.db.flush()

        root_unit = OrgUnit(
            tenant_id=organization.id,
            name=name,
            slug="root",
            type=OrgUnitType.org,
        )
        self.db.add(root_unit)
        await self.db.flush()

        membership = OrgMembership(
            tenant_id=organization.id,
            user_id=owner.id,
            org_unit_id=root_unit.id,
            workos_membership_id=workos_membership_id,
            role=OrgRole.owner,
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
            slug=project_slug,
            is_default=True,
            owner_user_id=owner.id,
        )
        await self.ensure_organization_default_agents(
            organization_id=organization.id,
            actor_user_id=owner.id,
        )
        await self.db.flush()
        return organization, project

    async def create_project(
        self,
        *,
        organization: Tenant,
        created_by: UUID | None,
        name: str,
        slug: str,
        description: str | None = None,
        is_default: bool = False,
        owner_user_id: UUID | None = None,
    ) -> Project:
        project = Project(
            organization_id=organization.id,
            name=name,
            slug=slug,
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
        from app.services.registry_seeding import ensure_platform_architect_agent

        await ensure_platform_architect_agent(
            self.db,
            organization_id,
            actor_user_id=actor_user_id,
        )

    async def ensure_organization_default_agents_if_missing(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID | None = None,
    ) -> bool:
        missing = await self._missing_agent_slugs(
            organization_id=organization_id,
            expected_slugs=self._ORG_DEFAULT_AGENT_SLUGS,
        )
        if not missing:
            return False
        await self.ensure_organization_default_agents(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
        )
        return True

    async def ensure_project_default_agents(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        actor_user_id: UUID | None = None,
    ) -> None:
        from app.services.artifact_coding_agent_profile import ensure_artifact_coding_agent_profile
        from app.services.published_app_coding_agent_profile import ensure_coding_agent_profile

        _ = project_id
        await ensure_artifact_coding_agent_profile(
            self.db,
            organization_id,
            actor_user_id=actor_user_id,
        )
        await ensure_coding_agent_profile(
            self.db,
            organization_id,
            actor_user_id=actor_user_id,
        )

    async def ensure_project_default_agents_if_missing(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        actor_user_id: UUID | None = None,
    ) -> bool:
        _ = project_id
        missing = await self._missing_agent_slugs(
            organization_id=organization_id,
            expected_slugs=self._PROJECT_DEFAULT_AGENT_SLUGS,
        )
        if not missing:
            return False
        await self.ensure_project_default_agents(
            organization_id=organization_id,
            project_id=project_id,
            actor_user_id=actor_user_id,
        )
        return True
