from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.postgres.models.agents import Agent
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Organization, User
from app.db.postgres.models.registry import ModelCapabilityType, ModelRegistry, ModelStatus
from app.db.postgres.models.workspace import Project
from app.services.agent_service import AgentService
from app.services.architect_mode_service import ArchitectMode, ArchitectModeService
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
                ModelRegistry.organization_id.is_(None),
                ModelRegistry.capability_type == ModelCapabilityType.CHAT,
                ModelRegistry.is_default.is_(True),
            )
        )
    ).scalars().all()
    for item in existing_defaults:
        item.is_default = False

    model = ModelRegistry(
        organization_id=None,
        name="Bootstrap Chat Model",
        system_key=f"bootstrap-chat-{suffix}",
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
    )
    await db_session.commit()

    assert organization.id is not None
    assert project.id is not None

    agents = (
        await db_session.execute(
            select(Agent).where(Agent.organization_id == organization.id).order_by(Agent.system_key.asc())
        )
    ).scalars().all()
    system_keys = [agent.system_key for agent in agents]
    assert "platform_architect" in system_keys
    assert "artifact_coding_agent" in system_keys
    assert "published_app_coding_agent" in system_keys
    service = AgentService(db=db_session, organization_id=organization.id)
    for agent in agents:
        if agent.system_key == "published_app_coding_agent":
            continue
        validation = await service.validate_agent(agent.id)
        assert validation.valid, f"{agent.system_key} validation failed: {validation.errors}"


@pytest.mark.asyncio
async def test_create_project_bootstrap_keeps_default_agent_profiles_idempotent(db_session):
    owner = await _seed_owner_and_default_chat_model(db_session)
    service = OrganizationBootstrapService(db_session)

    organization, _default_project = await service.create_organization_with_default_project(
        owner=owner,
        name="Idempotent Org",
    )
    second_project = await service.create_project(
        organization=organization,
        created_by=owner.id,
        name="Second Project",
        owner_user_id=owner.id,
    )
    await db_session.commit()

    assert isinstance(second_project, Project)

    agents = (
        await db_session.execute(
            select(Agent).where(Agent.organization_id == organization.id).order_by(Agent.system_key.asc())
        )
    ).scalars().all()
    counts: dict[str, int] = {}
    for agent in agents:
        counts[agent.system_key] = counts.get(agent.system_key, 0) + 1

    assert counts["platform_architect"] == 1
    assert counts["artifact_coding_agent"] == 1
    assert counts["published_app_coding_agent"] == 1


@pytest.mark.asyncio
async def test_backfill_helpers_materialize_profiles_for_existing_org_without_startup_scan(db_session):
    owner = await _seed_owner_and_default_chat_model(db_session)
    organization = Organization(name="Backfill Org", slug=f"backfill-org-{uuid4().hex[:8]}")
    project = Project(
        organization_id=organization.id,
        name="Default Project",
        slug=f"project-{uuid4().hex[:12]}",
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
            select(Agent.system_key).where(Agent.organization_id == organization.id).order_by(Agent.system_key.asc())
        )
    ).scalars().all()
    assert list(agents) == [
        "artifact_coding_agent",
        "platform_architect",
        "published_app_coding_agent",
    ]


@pytest.mark.asyncio
async def test_agents_list_backfill_persists_seeded_profiles_across_requests(db_session):
    from app.api.routers.agents import list_agents

    owner = await _seed_owner_and_default_chat_model(db_session)
    organization = Organization(name="Router Backfill Org", slug=f"router-backfill-org-{uuid4().hex[:8]}")
    db_session.add(organization)
    await db_session.flush()

    root_unit = OrgUnit(
        organization_id=organization.id,
        name=organization.name,
        slug="root",
        system_key="root",
        type=OrgUnitType.org,
    )
    db_session.add(root_unit)
    await db_session.flush()

    db_session.add(
        OrgMembership(
            organization_id=organization.id,
            user_id=owner.id,
            org_unit_id=root_unit.id,
            role=OrgRole.owner,
            status=MembershipStatus.active,
        )
    )

    project = Project(
        organization_id=organization.id,
        name="Default Project",
        slug=f"project-{uuid4().hex[:12]}",
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
            "organization_id": organization.id,
            "organization_id": organization.id,
            "project_id": project.id,
            "user": owner,
        },
        db=db_session,
    )

    response_names = sorted(item["name"] for item in response["items"])
    assert response_names == [
        "Artifact Coding Agent",
        "Platform Architect",
        "Published App Coding Agent",
    ]

    verify_session_factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    async with verify_session_factory() as verify_session:
        persisted_system_keys = (
            await verify_session.execute(
                select(Agent.system_key).where(Agent.organization_id == organization.id).order_by(Agent.system_key.asc())
            )
        ).scalars().all()

    assert sorted(persisted_system_keys) == [
        "artifact_coding_agent",
        "platform_architect",
        "published_app_coding_agent",
    ]


def test_platform_architect_mode_defaults_to_default():
    assert ArchitectModeService.parse_mode(None) == ArchitectMode.DEFAULT


@pytest.mark.asyncio
async def test_agents_list_skips_backfill_when_default_profiles_already_exist(db_session, monkeypatch):
    from app.api.routers.agents import list_agents

    owner = await _seed_owner_and_default_chat_model(db_session)
    service = OrganizationBootstrapService(db_session)
    organization, project = await service.create_organization_with_default_project(
        owner=owner,
        name="No Rebootstrap Org",
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
            "organization_id": organization.id,
            "organization_id": organization.id,
            "project_id": project.id,
            "user": owner,
        },
        db=db_session,
    )

    assert sorted(item["name"] for item in response["items"]) == [
        "Artifact Coding Agent",
        "Platform Architect",
        "Published App Coding Agent",
    ]
    assert org_calls["count"] == 0
    assert project_calls["count"] == 0
