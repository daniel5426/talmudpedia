from __future__ import annotations

import json
from uuid import UUID

import pytest
from sqlalchemy import select

from app.agent.execution.service import AgentExecutorService
from app.agent.execution.trace_recorder import ExecutionTraceRecorder
from app.core.security import ALGORITHM, SECRET_KEY
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.agent_threads import AgentThreadSurface, AgentThreadTurnStatus
from app.db.postgres.models.identity import User
from app.db.postgres.models.published_apps import PublishedAppAccount
from app.services.runtime_surface import RuntimeEventView
from app.services.security_bootstrap_service import SecurityBootstrapService
from app.services.organization_api_key_service import OrganizationAPIKeyService
from app.services.thread_service import ThreadService
from tests.published_apps._helpers import (
    admin_headers,
    install_stub_agent_worker,
    seed_admin_tenant_and_agent,
    seed_published_app,
)


ALLOWED_ORIGIN = "https://client.example.com"


def _parse_sse_events(payload: str) -> list[dict]:
    events: list[dict] = []
    for block in payload.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def _external_headers(token: str | None = None) -> dict[str, str]:
    headers = {"Origin": ALLOWED_ORIGIN}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _grant_member_role(db_session, *, organization_id, owner_id, email: str):
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(organization_id)
    await bootstrap.ensure_organization_reader_assignment(
        organization_id=organization_id,
        user_id=user.id,
        assigned_by=owner_id,
    )
    await db_session.commit()
    return user


async def _create_embed_key(db_session, *, organization_id, created_by):
    _api_key, token = await OrganizationAPIKeyService(db_session).create_api_key(
        organization_id=organization_id,
        name="Embed Runtime",
        scopes=["agents.embed"],
        created_by=created_by,
    )
    await db_session.commit()
    return token


async def _signup_external_user(client, db_session, *, app_public_id: str, organization_id, owner_id, email: str) -> str:
    signup_resp = await client.post(
        f"/public/external/apps/{app_public_id}/auth/signup",
        headers=_external_headers(),
        json={"email": email, "password": "secret123"},
    )
    assert signup_resp.status_code == 200
    await _grant_member_role(db_session, organization_id=organization_id, owner_id=owner_id, email=email)
    return signup_resp.json()["token"]


@pytest.mark.asyncio
async def test_runtime_surface_stream_headers_across_internal_published_and_embed(client, db_session, monkeypatch):
    tenant, owner, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="runtime-surface-streams-app",
        allowed_origins=[ALLOWED_ORIGIN],
    )
    external_token = await _signup_external_user(
        client,
        db_session,
        app_public_id=app.public_id,
        organization_id=tenant.id,
        owner_id=owner.id,
        email="runtime-surface-external@example.com",
    )
    embed_token = await _create_embed_key(db_session, organization_id=tenant.id, created_by=owner.id)

    install_stub_agent_worker(monkeypatch, content="shared-runtime-response")

    internal_resp = await client.post(
        f"/agents/{agent.id}/stream?mode=debug",
        headers=admin_headers(str(owner.id), str(tenant.id), str(org_unit.id)),
        json={"input": "internal hello"},
    )
    assert internal_resp.status_code == 200
    assert internal_resp.headers.get("X-Run-ID")
    assert internal_resp.headers.get("X-Thread-ID")
    assert any(item["event"] == "run.accepted" for item in _parse_sse_events(internal_resp.text))

    external_resp = await client.post(
        f"/public/external/apps/{app.public_id}/chat/stream",
        headers=_external_headers(external_token),
        json={"input": "external hello"},
    )
    assert external_resp.status_code == 200
    assert external_resp.headers.get("X-Thread-ID")
    assert external_resp.headers.get("X-Run-ID") is None
    assert any(item["event"] == "run.accepted" for item in _parse_sse_events(external_resp.text))

    embed_resp = await client.post(
        f"/public/embed/agents/{agent.id}/chat/stream",
        headers={"Authorization": f"Bearer {embed_token}"},
        json={"input": "embed hello", "external_user_id": "customer-1"},
    )
    assert embed_resp.status_code == 200
    assert embed_resp.headers.get("X-Thread-ID")
    assert embed_resp.headers.get("X-Run-ID") is None
    assert any(item["event"] == "run.accepted" for item in _parse_sse_events(embed_resp.text))


@pytest.mark.asyncio
async def test_runtime_surface_resume_paths_share_payload_handling_for_internal_and_external(client, db_session, monkeypatch):
    tenant, owner, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="runtime-surface-resume-app",
        allowed_origins=[ALLOWED_ORIGIN],
    )
    external_token = await _signup_external_user(
        client,
        db_session,
        app_public_id=app.public_id,
        organization_id=tenant.id,
        owner_id=owner.id,
        email="runtime-surface-resume@example.com",
    )
    app_account = (
        await db_session.execute(
            select(PublishedAppAccount).where(
                PublishedAppAccount.published_app_id == app.id,
                PublishedAppAccount.email == "runtime-surface-resume@example.com",
            )
        )
    ).scalar_one()

    thread_service = ThreadService(db_session)
    external_thread = await thread_service.resolve_or_create_thread(
        organization_id=tenant.id,
        user_id=None,
        app_account_id=app_account.id,
        agent_id=agent.id,
        published_app_id=app.id,
        surface=AgentThreadSurface.published_host_runtime,
        thread_id=None,
        input_text="resume me",
    )

    internal_run = AgentRun(
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=owner.id,
        initiator_user_id=owner.id,
        status=RunStatus.paused,
        input_params={"messages": []},
    )
    external_run = AgentRun(
        organization_id=tenant.id,
        agent_id=agent.id,
        initiator_user_id=owner.id,
        thread_id=external_thread.thread.id,
        status=RunStatus.paused,
        input_params={"messages": []},
    )
    db_session.add_all([internal_run, external_run])
    await db_session.commit()

    resume_calls: list[tuple[str, dict]] = []

    async def fake_resume(self, run_id, payload, background=True):
        resume_calls.append((str(run_id), dict(payload)))
        run = await self.db.get(AgentRun, run_id)
        run.status = RunStatus.completed
        run.output_result = {"final_output": "resumed"}
        await self.db.commit()

    monkeypatch.setattr(AgentExecutorService, "resume_run", fake_resume)

    internal_resp = await client.post(
        f"/agents/{agent.id}/stream?mode=debug",
        headers=admin_headers(str(owner.id), str(tenant.id), str(org_unit.id)),
        json={"run_id": str(internal_run.id), "input": "approved", "context": {"approval": "yes"}},
    )
    assert internal_resp.status_code == 200

    external_resp = await client.post(
        f"/public/external/apps/{app.public_id}/chat/stream",
        headers=_external_headers(external_token),
        json={"run_id": str(external_run.id), "input": "approved", "context": {"approval": "yes"}},
    )
    assert external_resp.status_code == 200

    assert resume_calls == [
        (str(internal_run.id), {"approval": "yes", "input": "approved"}),
        (str(external_run.id), {"approval": "yes", "input": "approved"}),
    ]


@pytest.mark.asyncio
async def test_runtime_surface_internal_run_events_and_cancel_routes_preserve_contract(client, db_session):
    tenant, owner, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(owner.id), str(tenant.id), str(org_unit.id))

    run = AgentRun(
        organization_id=tenant.id,
        agent_id=agent.id,
        user_id=owner.id,
        initiator_user_id=owner.id,
        status=RunStatus.running,
        output_result={"messages": []},
        input_params={"messages": []},
        depth=0,
    )
    db_session.add(run)
    await db_session.flush()
    run.root_run_id = run.id
    await db_session.commit()

    recorder = ExecutionTraceRecorder(serializer=lambda value: value)
    await recorder.save_event(
        run.id,
        db_session,
        {
            "event": "on_tool_start",
            "name": "lookup_client",
            "span_id": "tool-call-1",
            "visibility": "internal",
            "data": {"input": {"client_id": "123"}},
        },
    )
    await db_session.commit()

    events_resp = await client.get(f"/agents/runs/{run.id}/events", headers=headers)
    assert events_resp.status_code == 200
    payload = events_resp.json()
    assert payload["run_id"] == str(run.id)
    assert payload["event_count"] == 1
    assert payload["events"][0]["visibility"] == "internal"

    cancel_resp = await client.post(
        f"/agents/runs/{run.id}/cancel",
        headers=headers,
        json={"assistant_output_text": "partial answer"},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"
    assert cancel_resp.json()["run_id"] == str(run.id)

    await db_session.refresh(run)
    assert run.status == RunStatus.cancelled
    assert run.output_result["final_output"] == "partial answer"
    assert run.output_result["messages"][-1] == {"role": "assistant", "content": "partial answer"}


@pytest.mark.asyncio
async def test_runtime_surface_host_thread_detail_uses_canonical_public_event_projection(client, db_session, monkeypatch):
    tenant, owner, _, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="runtime-surface-host-events-app",
        auth_enabled=True,
        auth_providers=["password"],
    )

    signup_resp = await client.post(
        "/_talmudpedia/auth/signup",
        headers={"Host": f"{app.public_id}.apps.localhost"},
        json={"email": "runtime-surface-host@example.com", "password": "secret123"},
    )
    assert signup_resp.status_code == 200
    signup_user = (
        await db_session.execute(select(User).where(User.email == "runtime-surface-host@example.com"))
    ).scalar_one()
    bootstrap = SecurityBootstrapService(db_session)
    await bootstrap.ensure_default_roles(tenant.id)
    await bootstrap.ensure_organization_reader_assignment(
        organization_id=tenant.id,
        user_id=signup_user.id,
        assigned_by=owner.id,
    )
    await db_session.commit()

    async def fake_list_run_events(*, db, run_id, view, after_sequence=None, limit=None):
        _ = db, after_sequence, limit
        assert view == RuntimeEventView.public_safe
        return [{"event": "reasoning.update", "run_id": str(run_id), "payload": {"content": "canonical"}}]

    monkeypatch.setattr("app.services.runtime_surface.service.list_run_events", fake_list_run_events)

    app_account = (
        await db_session.execute(
            select(PublishedAppAccount).where(
                PublishedAppAccount.published_app_id == app.id,
                PublishedAppAccount.email == "runtime-surface-host@example.com",
            )
        )
    ).scalar_one()

    thread_service = ThreadService(db_session)
    resolved = await thread_service.resolve_or_create_thread(
        organization_id=tenant.id,
        user_id=None,
        app_account_id=app_account.id,
        agent_id=agent.id,
        published_app_id=app.id,
        surface=AgentThreadSurface.published_host_runtime,
        thread_id=None,
        input_text="hydrate canonical path",
    )
    run = AgentRun(
        organization_id=tenant.id,
        agent_id=agent.id,
        initiator_user_id=owner.id,
        thread_id=resolved.thread.id,
        input_params={"input": "hydrate canonical path"},
    )
    db_session.add(run)
    await db_session.flush()
    await thread_service.start_turn(
        thread_id=resolved.thread.id,
        run_id=run.id,
        user_input_text="hydrate canonical path",
    )
    await thread_service.complete_turn(
        run_id=run.id,
        status=AgentThreadTurnStatus.completed,
        assistant_output_text="History response",
    )
    await db_session.commit()

    thread_resp = await client.get(
        f"/_talmudpedia/threads/{resolved.thread.id}",
        headers={"Host": f"{app.public_id}.apps.localhost"},
    )
    assert thread_resp.status_code == 200
    payload = thread_resp.json()
    assert payload["turns"][0]["run_events"][0]["event"] == "reasoning.update"


@pytest.mark.asyncio
async def test_runtime_surface_public_history_is_consistent_between_external_and_embed_threads(client, db_session):
    tenant, owner, _org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    app = await seed_published_app(
        db_session,
        tenant.id,
        agent.id,
        owner.id,
        slug="runtime-surface-history-app",
        allowed_origins=[ALLOWED_ORIGIN],
    )
    external_token = await _signup_external_user(
        client,
        db_session,
        app_public_id=app.public_id,
        organization_id=tenant.id,
        owner_id=owner.id,
        email="runtime-surface-history@example.com",
    )
    embed_token = await _create_embed_key(db_session, organization_id=tenant.id, created_by=owner.id)
    app_account = (
        await db_session.execute(
            select(PublishedAppAccount).where(
                PublishedAppAccount.published_app_id == app.id,
                PublishedAppAccount.email == "runtime-surface-history@example.com",
            )
        )
    ).scalar_one()

    thread_service = ThreadService(db_session)
    external_thread = await thread_service.resolve_or_create_thread(
        organization_id=tenant.id,
        user_id=None,
        app_account_id=app_account.id,
        agent_id=agent.id,
        published_app_id=app.id,
        surface=AgentThreadSurface.published_host_runtime,
        thread_id=None,
        input_text="external history",
    )
    embed_thread = await thread_service.resolve_or_create_thread(
        organization_id=tenant.id,
        user_id=None,
        agent_id=agent.id,
        published_app_id=None,
        external_user_id="customer-history",
        external_session_id=None,
        surface=AgentThreadSurface.embedded_runtime,
        thread_id=None,
        input_text="embed history",
    )

    external_run = AgentRun(
        organization_id=tenant.id,
        agent_id=agent.id,
        initiator_user_id=owner.id,
        thread_id=external_thread.thread.id,
        status=RunStatus.completed,
        input_params={"input": "external history"},
        output_result={"final_output": "external history"},
    )
    embed_run = AgentRun(
        organization_id=tenant.id,
        agent_id=agent.id,
        initiator_user_id=owner.id,
        thread_id=embed_thread.thread.id,
        status=RunStatus.completed,
        input_params={"input": "embed history"},
        output_result={"final_output": "embed history"},
    )
    db_session.add_all([external_run, embed_run])
    await db_session.flush()
    await thread_service.start_turn(
        thread_id=external_thread.thread.id,
        run_id=external_run.id,
        user_input_text="external history",
    )
    await thread_service.complete_turn(
        run_id=external_run.id,
        status=AgentThreadTurnStatus.completed,
        assistant_output_text="external history",
        metadata={"final_output": "external history"},
    )
    await thread_service.start_turn(
        thread_id=embed_thread.thread.id,
        run_id=embed_run.id,
        user_input_text="embed history",
    )
    await thread_service.complete_turn(
        run_id=embed_run.id,
        status=AgentThreadTurnStatus.completed,
        assistant_output_text="embed history",
        metadata={"final_output": "embed history"},
    )

    recorder = ExecutionTraceRecorder(serializer=lambda value: value)
    for run_id in (external_run.id, embed_run.id):
        await recorder.save_event(
            run_id,
            db_session,
            {
                "event": "on_tool_start",
                "name": "lookup_client",
                "span_id": "tool-call-1",
                "visibility": "internal",
                "data": {
                    "input": {"client_id": "32001"},
                    "display_name": "Lookup client",
                    "summary": "Looking up client data",
                },
            },
        )
        await recorder.save_event(
            run_id,
            db_session,
            {
                "event": "on_tool_end",
                "name": "lookup_client",
                "span_id": "tool-call-1",
                "visibility": "internal",
                "data": {
                    "output": {"client_id": "32001"},
                    "display_name": "Lookup client",
                    "summary": "Client data loaded",
                },
            },
        )
    await db_session.commit()

    external_resp = await client.get(
        f"/public/external/apps/{app.public_id}/threads/{external_thread.thread.id}",
        headers=_external_headers(external_token),
    )
    embed_resp = await client.get(
        f"/public/embed/agents/{agent.id}/threads/{embed_thread.thread.id}",
        headers={"Authorization": f"Bearer {embed_token}"},
        params={"external_user_id": "customer-history"},
    )
    assert external_resp.status_code == 200
    assert embed_resp.status_code == 200

    external_events = [item["event"] for item in external_resp.json()["turns"][0]["run_events"]]
    embed_events = [item["event"] for item in embed_resp.json()["turns"][0]["run_events"]]
    assert external_events == ["tool.started", "reasoning.update", "tool.completed", "reasoning.update"]
    assert embed_events == external_events
