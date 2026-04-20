from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.postgres.models.agents import Agent
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.db.postgres.models.registry import ModelCapabilityType, ModelRegistry, ModelStatus
from app.db.postgres.models.workspace import Project
from app.services.organization_bootstrap_service import OrganizationBootstrapService


async def _seed_owner_and_default_chat_model(db_session):
    suffix = uuid4().hex[:8]
    owner = User(
        email=f"bootstrap-owner-{suffix}@example.com",
        full_name="Bootstrap Owner",
        role="admin",
    )
    existing_defaults = (
        await db_session.execute(
            select(ModelRegistry).where(
                ModelRegistry.tenant_id.is_(None),
                ModelRegistry.capability_type == ModelCapabilityType.CHAT,
                ModelRegistry.is_default.is_(True),
            )
        )
    ).scalars().all()
    for item in existing_defaults:
        item.is_default = False

    model = ModelRegistry(
        tenant_id=None,
        name="Bootstrap Chat Model",
        capability_type=ModelCapabilityType.CHAT,
        status=ModelStatus.ACTIVE,
        is_active=True,
        is_default=True,
    )
    db_session.add_all([owner, model])
    await db_session.commit()
    await db_session.refresh(owner)
    return owner


@pytest.mark.asyncio
async def test_create_organization_with_default_project_materializes_default_agent_profiles(db_session):
    owner = await _seed_owner_and_default_chat_model(db_session)

    organization, project = await OrganizationBootstrapService(db_session).create_organization_with_default_project(
        owner=owner,
        name="Bootstrap Org",
        slug=f"bootstrap-org-{uuid4().hex[:8]}",
    )
    await db_session.commit()

    assert organization.id is not None
    assert project.id is not None

    agents = (
        await db_session.execute(
            select(Agent).where(Agent.tenant_id == organization.id).order_by(Agent.slug.asc())
        )
    ).scalars().all()
    slugs = [agent.slug for agent in agents]
    assert "platform-architect" in slugs
    assert "artifact-coding-agent" in slugs
    assert "published-app-coding-agent" in slugs


@pytest.mark.asyncio
async def test_create_project_bootstrap_keeps_default_agent_profiles_idempotent(db_session):
    owner = await _seed_owner_and_default_chat_model(db_session)
    service = OrganizationBootstrapService(db_session)

    organization, _default_project = await service.create_organization_with_default_project(
        owner=owner,
        name="Idempotent Org",
        slug=f"idempotent-org-{uuid4().hex[:8]}",
    )
    second_project = await service.create_project(
        organization=organization,
        created_by=owner.id,
        name="Second Project",
        slug="second-project",
        owner_user_id=owner.id,
    )
    await db_session.commit()

    assert isinstance(second_project, Project)

    agents = (
        await db_session.execute(
            select(Agent).where(Agent.tenant_id == organization.id).order_by(Agent.slug.asc())
        )
    ).scalars().all()
    counts: dict[str, int] = {}
    for agent in agents:
        counts[agent.slug] = counts.get(agent.slug, 0) + 1

    assert counts["platform-architect"] == 1
    assert counts["artifact-coding-agent"] == 1
    assert counts["published-app-coding-agent"] == 1


@pytest.mark.asyncio
async def test_backfill_helpers_materialize_profiles_for_existing_org_without_startup_scan(db_session):
    owner = await _seed_owner_and_default_chat_model(db_session)
    organization = Tenant(name="Backfill Org", slug=f"backfill-org-{uuid4().hex[:8]}")
    project = Project(
        organization_id=organization.id,
        name="Default Project",
        slug="default",
        is_default=True,
        created_by=owner.id,
    )
    db_session.add(organization)
    await db_session.flush()
    project.organization_id = organization.id
    db_session.add(project)
    await db_session.flush()

    service = OrganizationBootstrapService(db_session)
    await service.ensure_organization_default_agents(
        organization_id=organization.id,
        actor_user_id=owner.id,
    )
    await service.ensure_project_default_agents(
        organization_id=organization.id,
        project_id=project.id,
        actor_user_id=owner.id,
    )
    await db_session.commit()

    agents = (
        await db_session.execute(
            select(Agent.slug).where(Agent.tenant_id == organization.id).order_by(Agent.slug.asc())
        )
    ).scalars().all()
    assert list(agents) == [
        "artifact-coding-agent",
        "platform-architect",
        "published-app-coding-agent",
    ]


@pytest.mark.asyncio
async def test_agents_list_backfill_persists_seeded_profiles_across_requests(db_session):
    from app.api.routers.agents import list_agents

    owner = await _seed_owner_and_default_chat_model(db_session)
    organization = Tenant(name="Router Backfill Org", slug=f"router-backfill-org-{uuid4().hex[:8]}")
    db_session.add(organization)
    await db_session.flush()

    root_unit = OrgUnit(
        tenant_id=organization.id,
        name=organization.name,
        slug="root",
        type=OrgUnitType.org,
    )
    db_session.add(root_unit)
    await db_session.flush()

    db_session.add(
        OrgMembership(
            tenant_id=organization.id,
            user_id=owner.id,
            org_unit_id=root_unit.id,
            role=OrgRole.owner,
            status=MembershipStatus.active,
        )
    )

    project = Project(
        organization_id=organization.id,
        name="Default Project",
        slug="default",
        is_default=True,
        created_by=owner.id,
    )
    db_session.add(project)
    await db_session.commit()

    response = await list_agents(
        status=None,
        skip=0,
        limit=50,
        view="full",
        context={
            "tenant_id": organization.id,
            "project_id": project.id,
            "user": owner,
        },
        db=db_session,
    )

    response_slugs = sorted(item["slug"] for item in response["items"])
    assert response_slugs == [
        "artifact-coding-agent",
        "platform-architect",
        "published-app-coding-agent",
    ]

    verify_session_factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    async with verify_session_factory() as verify_session:
        persisted_slugs = (
            await verify_session.execute(
                select(Agent.slug).where(Agent.tenant_id == organization.id).order_by(Agent.slug.asc())
            )
        ).scalars().all()

    assert list(persisted_slugs) == response_slugs


@pytest.mark.asyncio
async def test_agents_list_skips_backfill_when_default_profiles_already_exist(db_session, monkeypatch):
    from app.api.routers.agents import list_agents

    owner = await _seed_owner_and_default_chat_model(db_session)
    service = OrganizationBootstrapService(db_session)
    organization, project = await service.create_organization_with_default_project(
        owner=owner,
        name="No Rebootstrap Org",
        slug=f"no-rebootstrap-org-{uuid4().hex[:8]}",
    )
    await db_session.commit()

    org_calls = {"count": 0}
    project_calls = {"count": 0}

    async def _fail_org_ensure(self, *, organization_id, actor_user_id=None):
        _ = self, organization_id, actor_user_id
        org_calls["count"] += 1
        raise AssertionError("organization backfill should not run for an already-bootstrapped tenant")

    async def _fail_project_ensure(self, *, organization_id, project_id, actor_user_id=None):
        _ = self, organization_id, project_id, actor_user_id
        project_calls["count"] += 1
        raise AssertionError("project backfill should not run for an already-bootstrapped tenant")

    monkeypatch.setattr(OrganizationBootstrapService, "ensure_organization_default_agents", _fail_org_ensure)
    monkeypatch.setattr(OrganizationBootstrapService, "ensure_project_default_agents", _fail_project_ensure)

    response = await list_agents(
        status=None,
        skip=0,
        limit=50,
        view="full",
        context={
            "tenant_id": organization.id,
            "project_id": project.id,
            "user": owner,
        },
        db=db_session,
    )

    assert sorted(item["slug"] for item in response["items"]) == [
        "artifact-coding-agent",
        "platform-architect",
        "published-app-coding-agent",
    ]
    assert org_calls["count"] == 0
    assert project_calls["count"] == 0
