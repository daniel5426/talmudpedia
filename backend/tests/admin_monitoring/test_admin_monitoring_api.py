from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.db.postgres.models.agent_threads import AgentThread, AgentThreadSurface, AgentThreadStatus
from app.db.postgres.models.agents import Agent, AgentRun, AgentStatus, RunStatus
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.db.postgres.models.registry import ModelCapabilityType, ModelRegistry, ModelStatus
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppAccount
from app.services.security_bootstrap_service import SecurityBootstrapService


def _auth_headers(user_id: str, tenant_id: str, org_unit_id: str) -> dict[str, str]:
    token = create_access_token(
        subject=user_id,
        tenant_id=tenant_id,
        org_unit_id=org_unit_id,
        org_role="owner",
    )
    return {"Authorization": f"Bearer {token}", "X-Tenant-ID": tenant_id}


async def _seed_monitoring_fixture(db_session):
    tenant = Tenant(name=f"Tenant {uuid4().hex[:6]}", slug=f"tenant-{uuid4().hex[:8]}")
    owner = User(
        email=f"owner-{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("secret123"),
        role="user",
        full_name="Owner",
    )
    platform_user = User(
        email=f"platform-{uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("secret123"),
        role="user",
        full_name="Platform User",
    )
    db_session.add_all([tenant, owner, platform_user])
    await db_session.flush()

    org_unit = OrgUnit(
        tenant_id=tenant.id,
        name="Root",
        slug=f"root-{uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    db_session.add(org_unit)
    await db_session.flush()

    for user, role in ((owner, OrgRole.owner), (platform_user, OrgRole.member)):
        db_session.add(
            OrgMembership(
                tenant_id=tenant.id,
                user_id=user.id,
                org_unit_id=org_unit.id,
                role=role,
                status=MembershipStatus.active,
            )
        )
    await db_session.flush()

    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_owner_assignment(tenant_id=tenant.id, user_id=owner.id, assigned_by=owner.id)
    await bootstrap.ensure_member_assignment(tenant_id=tenant.id, user_id=platform_user.id, assigned_by=owner.id)

    agent_primary = Agent(
        tenant_id=tenant.id,
        name="Primary Agent",
        slug=f"primary-{uuid4().hex[:6]}",
        graph_definition={"nodes": [], "edges": []},
        status=AgentStatus.published,
    )
    agent_secondary = Agent(
        tenant_id=tenant.id,
        name="Secondary Agent",
        slug=f"secondary-{uuid4().hex[:6]}",
        graph_definition={"nodes": [], "edges": []},
        status=AgentStatus.published,
    )
    db_session.add_all([agent_primary, agent_secondary])
    await db_session.flush()

    app = PublishedApp(
        tenant_id=tenant.id,
        agent_id=agent_primary.id,
        name="Standalone App",
        slug=f"standalone-{uuid4().hex[:6]}",
    )
    db_session.add(app)
    await db_session.flush()

    mapped_account = PublishedAppAccount(
        published_app_id=app.id,
        global_user_id=platform_user.id,
        email=f"mapped-{uuid4().hex[:6]}@example.com",
        full_name="Mapped Account",
    )
    unmapped_account = PublishedAppAccount(
        published_app_id=app.id,
        email=f"unmapped-{uuid4().hex[:6]}@example.com",
        full_name="Unmapped Account",
    )
    db_session.add_all([mapped_account, unmapped_account])
    await db_session.flush()

    now = datetime.now(timezone.utc)
    threads = [
        AgentThread(
            tenant_id=tenant.id,
            user_id=platform_user.id,
            agent_id=agent_primary.id,
            title="Platform Thread",
            surface=AgentThreadSurface.internal,
            status=AgentThreadStatus.active,
            last_activity_at=now,
        ),
        AgentThread(
            tenant_id=tenant.id,
            app_account_id=mapped_account.id,
            published_app_id=app.id,
            agent_id=agent_primary.id,
            title="Mapped Account Thread",
            surface=AgentThreadSurface.published_host_runtime,
            status=AgentThreadStatus.active,
            last_activity_at=now - timedelta(minutes=1),
        ),
        AgentThread(
            tenant_id=tenant.id,
            app_account_id=unmapped_account.id,
            published_app_id=app.id,
            agent_id=agent_primary.id,
            title="Unmapped Account Thread",
            surface=AgentThreadSurface.published_host_runtime,
            status=AgentThreadStatus.active,
            last_activity_at=now - timedelta(minutes=2),
        ),
        AgentThread(
            tenant_id=tenant.id,
            agent_id=agent_primary.id,
            external_user_id="embed-user",
            title="Embed Primary Thread",
            surface=AgentThreadSurface.embedded_runtime,
            status=AgentThreadStatus.active,
            last_activity_at=now - timedelta(minutes=3),
        ),
        AgentThread(
            tenant_id=tenant.id,
            agent_id=agent_secondary.id,
            external_user_id="embed-user",
            title="Embed Secondary Thread",
            surface=AgentThreadSurface.embedded_runtime,
            status=AgentThreadStatus.active,
            last_activity_at=now - timedelta(minutes=4),
        ),
    ]
    db_session.add_all(threads)
    await db_session.flush()

    for index, thread in enumerate(threads):
        db_session.add(
            AgentRun(
                tenant_id=tenant.id,
                agent_id=thread.agent_id,
                user_id=platform_user.id if thread.user_id == platform_user.id else None,
                published_app_id=app.id if thread.published_app_id else None,
                published_app_account_id=thread.app_account_id,
                thread_id=thread.id,
                surface=thread.surface.value,
                usage_tokens=100 + index,
                status=RunStatus.failed if index == 2 else RunStatus.completed,
                created_at=now - timedelta(minutes=index),
                started_at=now - timedelta(minutes=index, seconds=20),
                completed_at=now - timedelta(minutes=index, seconds=5),
                error_message="boom" if index == 2 else None,
            )
        )

    await db_session.commit()
    return {
        "tenant": tenant,
        "owner": owner,
        "platform_user": platform_user,
        "org_unit": org_unit,
        "agent_primary": agent_primary,
        "agent_secondary": agent_secondary,
        "mapped_account": mapped_account,
        "unmapped_account": unmapped_account,
        "threads": threads,
    }


@pytest.mark.asyncio
async def test_admin_users_merges_mapped_app_accounts_and_keeps_embed_scoped(client, db_session):
    fixture = await _seed_monitoring_fixture(db_session)
    headers = _auth_headers(str(fixture["owner"].id), str(fixture["tenant"].id), str(fixture["org_unit"].id))

    response = await client.get("/admin/users", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    actor_ids = {item["actor_id"] for item in payload["items"]}
    assert str(fixture["platform_user"].id) in actor_ids
    assert f"app_account:{fixture['unmapped_account'].id}" in actor_ids
    assert f"app_account:{fixture['mapped_account'].id}" not in actor_ids
    assert any(item["actor_type"] == "embedded_external_user" for item in payload["items"])

    platform_row = next(item for item in payload["items"] if item["actor_id"] == str(fixture["platform_user"].id))
    assert platform_row["threads_count"] == 2
    assert platform_row["source_app_count"] == 1


@pytest.mark.asyncio
async def test_admin_user_threads_include_merged_mapped_account_threads(client, db_session):
    fixture = await _seed_monitoring_fixture(db_session)
    headers = _auth_headers(str(fixture["owner"].id), str(fixture["tenant"].id), str(fixture["org_unit"].id))

    response = await client.get(f"/admin/users/{fixture['platform_user'].id}/threads", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    titles = {item["title"] for item in payload["items"]}
    assert "Platform Thread" in titles
    assert "Mapped Account Thread" in titles
    assert "Unmapped Account Thread" not in titles


@pytest.mark.asyncio
async def test_admin_threads_filter_by_agent_and_include_actor_metadata(client, db_session):
    fixture = await _seed_monitoring_fixture(db_session)
    headers = _auth_headers(str(fixture["owner"].id), str(fixture["tenant"].id), str(fixture["org_unit"].id))

    response = await client.get(f"/admin/threads?agent_id={fixture['agent_primary'].id}", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["items"]
    assert all(item["agent_id"] == str(fixture["agent_primary"].id) for item in payload["items"])
    assert any(item["actor_type"] == "platform_user" for item in payload["items"])
    assert any(item["actor_type"] == "published_app_account" for item in payload["items"])


@pytest.mark.asyncio
async def test_agent_stats_can_scope_to_single_agent_and_merged_actor(client, db_session):
    fixture = await _seed_monitoring_fixture(db_session)
    headers = _auth_headers(str(fixture["owner"].id), str(fixture["tenant"].id), str(fixture["org_unit"].id))

    response = await client.get(
        f"/admin/stats/summary?section=agents&days=7&agent_id={fixture['agent_primary'].id}",
        headers=headers,
    )
    assert response.status_code == 200
    agents_payload = response.json()["agents"]

    assert agents_payload["agent_count"] == 1
    assert agents_payload["total_runs"] == 4
    assert agents_payload["top_users_by_runs"][0]["user_id"] == str(fixture["platform_user"].id)
    assert agents_payload["top_users_by_runs"][0]["count"] == 2


@pytest.mark.asyncio
async def test_resource_stats_models_do_not_require_slug(client, db_session):
    fixture = await _seed_monitoring_fixture(db_session)
    headers = _auth_headers(str(fixture["owner"].id), str(fixture["tenant"].id), str(fixture["org_unit"].id))

    db_session.add(
        ModelRegistry(
            tenant_id=fixture["tenant"].id,
            name="Vision Model",
            capability_type=ModelCapabilityType.VISION,
            status=ModelStatus.ACTIVE,
            metadata_={"vision": True},
            is_active=True,
        )
    )
    await db_session.commit()

    response = await client.get(
        "/admin/stats/summary?section=resources&days=30",
        headers=headers,
    )
    assert response.status_code == 200

    payload = response.json()["resources"]
    assert payload["model_count"] >= 1
    assert any(item["name"] == "Vision Model" for item in payload["models"])
    assert all("slug" not in item for item in payload["models"])
