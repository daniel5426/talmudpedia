from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import jwt
from sqlalchemy import select

from app.core.security import ALGORITHM, SECRET_KEY, create_access_token, get_password_hash
from app.db.postgres.models.agent_threads import AgentThread, AgentThreadSurface, AgentThreadStatus, AgentThreadTurn
from app.db.postgres.models.agents import Agent, AgentRun, AgentStatus, RunStatus
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Organization, User
from app.db.postgres.models.registry import ModelCapabilityType, ModelRegistry, ModelStatus
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppAccount
from app.services.security_bootstrap_service import SecurityBootstrapService


def _auth_headers(user_id: str, organization_id: str, org_unit_id: str) -> dict[str, str]:
    payload = jwt.decode(
        create_access_token(
            subject=user_id,
            organization_id=organization_id,
            org_unit_id=org_unit_id,
            org_role="owner",
        ),
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )
    payload["scope"] = ["*"]
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return {"Authorization": f"Bearer {token}", "X-Organization-ID": organization_id}


async def _seed_monitoring_fixture(db_session):
    tenant = Organization(name=f"Organization {uuid4().hex[:6]}", slug=f"tenant-{uuid4().hex[:8]}")
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
        organization_id=tenant.id,
        name="Root",
        slug=f"root-{uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    db_session.add(org_unit)
    await db_session.flush()

    for user, role in ((owner, OrgRole.owner), (platform_user, OrgRole.member)):
        db_session.add(
            OrgMembership(
                organization_id=tenant.id,
                user_id=user.id,
                org_unit_id=org_unit.id,
                role=role,
                status=MembershipStatus.active,
            )
        )
    await db_session.flush()

    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_organization_owner_assignment(organization_id=tenant.id, user_id=owner.id, assigned_by=owner.id)
    await bootstrap.ensure_organization_reader_assignment(organization_id=tenant.id, user_id=platform_user.id, assigned_by=owner.id)

    agent_primary = Agent(
        organization_id=tenant.id,
        name="Primary Agent",
        slug=f"primary-{uuid4().hex[:6]}",
        graph_definition={"nodes": [], "edges": []},
        status=AgentStatus.published,
    )
    agent_secondary = Agent(
        organization_id=tenant.id,
        name="Secondary Agent",
        slug=f"secondary-{uuid4().hex[:6]}",
        graph_definition={"nodes": [], "edges": []},
        status=AgentStatus.published,
    )
    db_session.add_all([agent_primary, agent_secondary])
    await db_session.flush()

    app = PublishedApp(
        organization_id=tenant.id,
        agent_id=agent_primary.id,
        name="Standalone App",
        public_id=f"app-{uuid4().hex[:12]}",
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
            organization_id=tenant.id,
            user_id=platform_user.id,
            agent_id=agent_primary.id,
            title="Platform Thread",
            surface=AgentThreadSurface.internal,
            status=AgentThreadStatus.active,
            last_activity_at=now,
        ),
        AgentThread(
            organization_id=tenant.id,
            app_account_id=mapped_account.id,
            published_app_id=app.id,
            agent_id=agent_primary.id,
            title="Mapped Account Thread",
            surface=AgentThreadSurface.published_host_runtime,
            status=AgentThreadStatus.active,
            last_activity_at=now - timedelta(minutes=1),
        ),
        AgentThread(
            organization_id=tenant.id,
            app_account_id=unmapped_account.id,
            published_app_id=app.id,
            agent_id=agent_primary.id,
            title="Unmapped Account Thread",
            surface=AgentThreadSurface.published_host_runtime,
            status=AgentThreadStatus.active,
            last_activity_at=now - timedelta(minutes=2),
        ),
        AgentThread(
            organization_id=tenant.id,
            agent_id=agent_primary.id,
            external_user_id="embed-user",
            title="Embed Primary Thread",
            surface=AgentThreadSurface.embedded_runtime,
            status=AgentThreadStatus.active,
            last_activity_at=now - timedelta(minutes=3),
        ),
        AgentThread(
            organization_id=tenant.id,
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
                organization_id=tenant.id,
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
    assert all("lineage" in item for item in payload["items"])
    root_row = next(item for item in payload["items"] if item["id"] == str(fixture["threads"][0].id))
    assert root_row["lineage"]["root_thread_id"] == str(fixture["threads"][0].id)
    assert root_row["lineage"]["parent_thread_id"] is None
    assert root_row["lineage"]["depth"] == 0
    assert root_row["lineage"]["is_root"] is True


@pytest.mark.asyncio
async def test_admin_thread_detail_joins_run_usage(client, db_session):
    fixture = await _seed_monitoring_fixture(db_session)
    headers = _auth_headers(str(fixture["owner"].id), str(fixture["tenant"].id), str(fixture["org_unit"].id))
    thread = fixture["threads"][0]
    run = await db_session.scalar(select(AgentRun).where(AgentRun.thread_id == thread.id).limit(1))
    assert run is not None
    run.input_tokens = 70
    run.output_tokens = 30
    run.total_tokens = 100
    run.usage_source = "exact"
    db_session.add(
        AgentThreadTurn(
            thread_id=thread.id,
            run_id=run.id,
            turn_index=0,
            user_input_text="hello",
            assistant_output_text="world",
        )
    )
    await db_session.commit()

    response = await client.get(f"/admin/threads/{thread.id}", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["token_usage"]["total_tokens"] == 100
    assert payload["token_usage"]["exact_total_tokens"] == 100
    assert payload["token_usage"]["estimated_total_tokens"] is None
    assert payload["turns"][0]["run_usage"] == {
        "source": "exact",
        "input_tokens": 70,
        "output_tokens": 30,
        "total_tokens": 100,
        "cached_input_tokens": None,
        "cached_output_tokens": None,
        "reasoning_tokens": None,
    }


@pytest.mark.asyncio
async def test_admin_thread_detail_returns_lineage_and_subthread_tree_when_requested(client, db_session):
    fixture = await _seed_monitoring_fixture(db_session)
    headers = _auth_headers(str(fixture["owner"].id), str(fixture["tenant"].id), str(fixture["org_unit"].id))
    root_thread = fixture["threads"][0]
    root_run = await db_session.scalar(select(AgentRun).where(AgentRun.thread_id == root_thread.id).limit(1))
    assert root_run is not None

    root_turn = AgentThreadTurn(
        thread_id=root_thread.id,
        run_id=root_run.id,
        turn_index=0,
        user_input_text="root hello",
        assistant_output_text="root world",
    )
    db_session.add(root_turn)
    await db_session.flush()

    child_thread = AgentThread(
        organization_id=fixture["tenant"].id,
        user_id=fixture["platform_user"].id,
        agent_id=fixture["agent_secondary"].id,
        surface=AgentThreadSurface.internal,
        title="Child thread",
        root_thread_id=root_thread.id,
        parent_thread_id=root_thread.id,
        parent_thread_turn_id=root_turn.id,
        spawned_by_run_id=root_run.id,
        lineage_depth=1,
    )
    db_session.add(child_thread)
    await db_session.flush()
    child_run = AgentRun(
        organization_id=fixture["tenant"].id,
        agent_id=fixture["agent_secondary"].id,
        user_id=fixture["platform_user"].id,
        initiator_user_id=fixture["platform_user"].id,
        thread_id=child_thread.id,
        input_params={"input": "child hello"},
        parent_run_id=root_run.id,
        root_run_id=root_run.id,
        depth=1,
    )
    db_session.add(child_run)
    await db_session.flush()
    db_session.add(
        AgentThreadTurn(
            thread_id=child_thread.id,
            run_id=child_run.id,
            turn_index=0,
            user_input_text="child hello",
            assistant_output_text="child world",
        )
    )
    await db_session.commit()

    response = await client.get(
        f"/admin/threads/{root_thread.id}?include_subthreads=true&subthread_depth=1",
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["lineage"]["root_thread_id"] == str(root_thread.id)
    assert payload["lineage"]["is_root"] is True
    assert payload["subthread_tree"]["thread"]["id"] == str(root_thread.id)
    assert len(payload["subthread_tree"]["children"]) == 1
    child_payload = payload["subthread_tree"]["children"][0]
    assert child_payload["thread"]["id"] == str(child_thread.id)
    assert child_payload["lineage"]["root_thread_id"] == str(root_thread.id)
    assert child_payload["lineage"]["parent_thread_id"] == str(root_thread.id)
    assert child_payload["lineage"]["parent_thread_turn_id"] == str(root_turn.id)
    assert child_payload["lineage"]["spawned_by_run_id"] == str(root_run.id)
    assert child_payload["lineage"]["depth"] == 1
    assert child_payload["turns"][0]["assistant_output_text"] == "child world"


@pytest.mark.asyncio
async def test_admin_thread_detail_surfaces_estimated_usage_separately(client, db_session):
    fixture = await _seed_monitoring_fixture(db_session)
    headers = _auth_headers(str(fixture["owner"].id), str(fixture["tenant"].id), str(fixture["org_unit"].id))
    thread = fixture["threads"][0]
    run = await db_session.scalar(select(AgentRun).where(AgentRun.thread_id == thread.id).limit(1))
    assert run is not None
    run.total_tokens = 44
    run.input_tokens = None
    run.output_tokens = None
    run.usage_source = "estimated"
    db_session.add(
        AgentThreadTurn(
            thread_id=thread.id,
            run_id=run.id,
            turn_index=0,
            user_input_text="hello",
            assistant_output_text="world",
        )
    )
    await db_session.commit()

    response = await client.get(f"/admin/threads/{thread.id}", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["token_usage"]["exact_total_tokens"] is None
    assert payload["token_usage"]["estimated_total_tokens"] == 44
    assert payload["turns"][0]["run_usage"] == {
        "source": "estimated",
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": 44,
        "cached_input_tokens": None,
        "cached_output_tokens": None,
        "reasoning_tokens": None,
    }


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
            organization_id=fixture["tenant"].id,
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
