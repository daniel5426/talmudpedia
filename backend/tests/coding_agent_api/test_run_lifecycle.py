from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionEvent
from app.db.postgres.models.agents import Agent, AgentRun, RunStatus
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppCodingRunSandboxStatus,
    PublishedAppCodingChatMessage,
    PublishedAppCodingChatMessageRole,
    PublishedAppCodingChatSession,
    PublishedAppDraftDevSession,
    PublishedAppDraftDevSessionStatus,
    PublishedAppRevision,
    PublishedAppRevisionKind,
)
from app.db.postgres.models.registry import (
    ModelCapabilityType,
    ModelProviderBinding,
    ModelProviderType,
    ModelRegistry,
    ModelStatus,
)
from app.services.published_app_coding_agent_engines.base import EngineCancelResult
from app.services.published_app_coding_agent_engines.native_engine import NativePublishedAppCodingAgentEngine
from app.services.published_app_coding_agent_engines.opencode_engine import OpenCodePublishedAppCodingAgentEngine
from app.services.published_app_coding_agent_engines.prompt_history import build_opencode_effective_prompt
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_run_sandbox_service import PublishedAppCodingRunSandboxService
from app.services.published_app_draft_dev_runtime_client import PublishedAppDraftDevRuntimeClient
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


@pytest.fixture(autouse=True)
def _mock_run_sandbox_context(monkeypatch):
    async def _fake_ensure_run_sandbox_context(self, *, run, app, base_revision, actor_id):
        context = self._run_context(run)
        context["coding_run_sandbox_id"] = "sandbox-test"
        context["coding_run_sandbox_status"] = "running"
        context["coding_run_sandbox_started_at"] = datetime.now(timezone.utc).isoformat()
        context["coding_run_sandbox_workspace_path"] = "/workspace"
        return {
            "opencode_sandbox_id": "sandbox-test",
            "opencode_workspace_path": "/workspace",
        }

    monkeypatch.setattr(
        PublishedAppCodingAgentRuntimeService,
        "_ensure_run_sandbox_context",
        _fake_ensure_run_sandbox_context,
    )


async def _create_app_and_draft_revision(
    client,
    headers: dict[str, str],
    agent_id: str,
    *,
    app_name: str | None = None,
) -> tuple[str, str]:
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": app_name or "Coding Agent API App",
            "agent_id": agent_id,
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    draft_revision_id = state_resp.json()["current_draft_revision"]["id"]
    return app_id, draft_revision_id


async def _insert_coding_agent_run(
    db_session,
    *,
    tenant_id,
    agent_id,
    user_id,
    app_id: str,
    base_revision_id: str,
    status: RunStatus,
    execution_engine: str = "native",
) -> AgentRun:
    run = AgentRun(
        tenant_id=tenant_id,
        agent_id=agent_id,
        user_id=user_id,
        initiator_user_id=user_id,
        status=status,
        input_params={
            "input": "test",
            "context": {
                "coding_run_sandbox_id": "sandbox-test",
                "coding_run_sandbox_status": "running",
                "coding_run_sandbox_workspace_path": "/workspace",
            },
        },
        surface=CODING_AGENT_SURFACE,
        published_app_id=UUID(app_id),
        base_revision_id=UUID(base_revision_id),
        execution_engine=execution_engine,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


async def _insert_chat_model(
    db_session,
    *,
    tenant_id,
    name: str,
    is_default: bool,
) -> ModelRegistry:
    model = ModelRegistry(
        tenant_id=tenant_id,
        name=name,
        slug=f"{name.lower().replace(' ', '-')}-{uuid4().hex[:6]}",
        capability_type=ModelCapabilityType.CHAT,
        status=ModelStatus.ACTIVE,
        is_active=True,
        is_default=is_default,
        metadata_={},
        default_resolution_policy={},
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


def test_apply_run_scoped_model_override_pins_agent_node_model() -> None:
    graph_definition = {
        "nodes": [
            {"id": "start", "type": "start", "config": {}},
            {"id": "agent", "type": "agent", "config": {"model_id": "old-model", "name": "Agent"}},
            {"id": "llm", "type": "llm", "config": {"model_id": "other-old"}},
            {"id": "end", "type": "end", "config": {}},
        ],
        "edges": [],
    }
    patched = AgentExecutorService._apply_run_scoped_model_override(graph_definition, "pinned-model")
    assert patched["nodes"][1]["config"]["model_id"] == "pinned-model"
    assert patched["nodes"][2]["config"]["model_id"] == "pinned-model"
    assert patched["nodes"][0]["config"] == {}


@pytest.mark.asyncio
async def test_coding_agent_create_run_list_and_get(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    async def _fake_create_run(
        self,
        *,
        app,
        base_revision,
        actor_id,
        user_prompt,
        messages=None,
        requested_scopes=None,
        requested_model_id=None,
        execution_engine="native",
        chat_session_id=None,
    ):
        normalized_messages = list(messages or [])
        if not normalized_messages or normalized_messages[-1].get("content") != user_prompt:
            normalized_messages.append({"role": "user", "content": user_prompt})
        run = AgentRun(
            tenant_id=app.tenant_id,
            agent_id=app.agent_id,
            user_id=actor_id,
            initiator_user_id=actor_id,
            status=RunStatus.queued,
            input_params={"input": user_prompt, "messages": normalized_messages},
            surface=CODING_AGENT_SURFACE,
            published_app_id=app.id,
            base_revision_id=base_revision.id,
            requested_model_id=requested_model_id,
            resolved_model_id=requested_model_id,
            execution_engine=execution_engine,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "create_run", _fake_create_run)

    create_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={
            "input": "Update the hero title",
            "base_revision_id": draft_revision_id,
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
        },
    )
    assert create_resp.status_code == 200
    create_payload = create_resp.json()
    assert create_payload["status"] == "queued"
    assert create_payload["published_app_id"] == app_id
    assert create_payload["base_revision_id"] == draft_revision_id
    assert create_payload["execution_engine"] == "native"
    assert create_payload["requested_model_id"] is None
    assert create_payload["resolved_model_id"] is None

    run_id = create_payload["run_id"]
    list_resp = await client.get(f"/admin/apps/{app_id}/coding-agent/runs?limit=10", headers=headers)
    assert list_resp.status_code == 200
    list_payload = list_resp.json()
    assert any(item["run_id"] == run_id for item in list_payload)
    selected = next(item for item in list_payload if item["run_id"] == run_id)
    assert selected["execution_engine"] == "native"

    get_resp = await client.get(f"/admin/apps/{app_id}/coding-agent/runs/{run_id}", headers=headers)
    assert get_resp.status_code == 200
    get_payload = get_resp.json()
    assert get_payload["run_id"] == run_id
    assert get_payload["surface"] == CODING_AGENT_SURFACE
    assert get_payload["execution_engine"] == "native"
    run_row = await db_session.get(AgentRun, UUID(run_id))
    assert run_row is not None
    run_messages = run_row.input_params.get("messages") if isinstance(run_row.input_params, dict) else None
    assert isinstance(run_messages, list)
    assert run_messages[0]["role"] == "user"
    assert run_messages[0]["content"] == "Update the hero title"


@pytest.mark.asyncio
async def test_coding_agent_create_run_uses_active_builder_sandbox_snapshot(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, initial_draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    session = PublishedAppDraftDevSession(
        published_app_id=UUID(app_id),
        user_id=user.id,
        revision_id=UUID(initial_draft_revision_id),
        sandbox_id="builder-sandbox-1",
        preview_url="http://127.0.0.1:5173/sandbox/builder-sandbox-1",
        status=PublishedAppDraftDevSessionStatus.running,
        idle_timeout_seconds=180,
    )
    db_session.add(session)
    await db_session.commit()

    async def _fake_snapshot_files(self, *, sandbox_id: str):
        assert sandbox_id == "builder-sandbox-1"
        return {
            "files": {
                "src/main.tsx": "import React from 'react';\nexport default function App(){return <main>Live</main>}\n",
                "package.json": '{"name":"live-app"}',
                "dist/assets/index.js": "console.log('artifact');",
                ".vite/deps/chunk-1.js": "export default 1;",
                "tsconfig.tsbuildinfo": '{"version": "5.0"}',
            }
        }

    async def _fake_create_run(
        self,
        *,
        app,
        base_revision,
        actor_id,
        user_prompt,
        messages=None,
        requested_scopes=None,
        requested_model_id=None,
        execution_engine="native",
        chat_session_id=None,
    ):
        run = AgentRun(
            tenant_id=app.tenant_id,
            agent_id=app.agent_id,
            user_id=actor_id,
            initiator_user_id=actor_id,
            status=RunStatus.queued,
            input_params={"input": user_prompt, "messages": list(messages or [])},
            surface=CODING_AGENT_SURFACE,
            published_app_id=app.id,
            base_revision_id=base_revision.id,
            execution_engine=execution_engine,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    monkeypatch.setattr(PublishedAppDraftDevRuntimeClient, "snapshot_files", _fake_snapshot_files)
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "create_run", _fake_create_run)

    response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={"input": "Make the headline bigger"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["base_revision_id"] != initial_draft_revision_id

    updated_app = await db_session.get(PublishedApp, UUID(app_id))
    assert updated_app is not None
    assert str(updated_app.current_draft_revision_id) == payload["base_revision_id"]
    updated_revision = await db_session.get(PublishedAppRevision, UUID(payload["base_revision_id"]))
    assert updated_revision is not None
    draft_files = dict(updated_revision.files or {})
    assert "src/main.tsx" in draft_files
    assert "package.json" in draft_files
    assert "dist/assets/index.js" not in draft_files
    assert ".vite/deps/chunk-1.js" not in draft_files
    assert "tsconfig.tsbuildinfo" not in draft_files


@pytest.mark.asyncio
async def test_coding_agent_create_run_detects_stale_revision(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, _ = await _create_app_and_draft_revision(client, headers, str(agent.id))

    conflict_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={"input": "Any update", "base_revision_id": str(uuid4())},
    )
    assert conflict_resp.status_code == 409
    detail = conflict_resp.json()["detail"]
    assert detail["code"] == "REVISION_CONFLICT"
    assert detail["latest_revision_id"]


@pytest.mark.asyncio
async def test_runtime_create_run_uses_chat_scoped_sandbox_key(db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    app = PublishedApp(
        tenant_id=tenant.id,
        agent_id=agent.id,
        name=f"Chat Scope App {uuid4().hex[:6]}",
        slug=f"chat-scope-{uuid4().hex[:8]}",
        template_key="chat-classic",
        auth_enabled=True,
        auth_providers=["password"],
    )
    db_session.add(app)
    await db_session.flush()

    revision = PublishedAppRevision(
        published_app_id=app.id,
        kind=PublishedAppRevisionKind.draft,
        template_key=app.template_key,
        entry_file="src/main.tsx",
        files={"src/main.tsx": "export default function App(){return <main />}\n"},
        created_by=user.id,
    )
    db_session.add(revision)
    await db_session.flush()
    app.current_draft_revision_id = revision.id
    await db_session.commit()

    await _insert_chat_model(
        db_session,
        tenant_id=tenant.id,
        name="Scoped Chat Model",
        is_default=True,
    )

    captured: dict[str, str | None] = {}

    async def _fake_ensure_run_sandbox_context(self, *, run, app, base_revision, actor_id):
        captured["controller_session_id"] = self._chat_sandbox_scope_for_run(run)
        context = self._run_context(run)
        context["coding_run_sandbox_id"] = "chat-scope-sandbox"
        context["coding_run_sandbox_status"] = "running"
        context["coding_run_sandbox_workspace_path"] = "/workspace"
        return {
            "opencode_sandbox_id": "chat-scope-sandbox",
            "opencode_workspace_path": "/workspace",
        }

    monkeypatch.setenv("APPS_CODING_AGENT_CHAT_SANDBOX_REUSE_ENABLED", "1")
    monkeypatch.setenv("APPS_CODING_AGENT_NATIVE_ENABLED", "1")
    monkeypatch.setattr(
        PublishedAppCodingAgentRuntimeService,
        "_ensure_run_sandbox_context",
        _fake_ensure_run_sandbox_context,
    )

    service = PublishedAppCodingAgentRuntimeService(db_session)
    chat_session_id = uuid4()
    run = await service.create_run(
        app=app,
        base_revision=revision,
        actor_id=user.id,
        user_prompt="hello",
        execution_engine="native",
        chat_session_id=chat_session_id,
    )
    assert captured["controller_session_id"] == f"chat-{chat_session_id}"
    context = run.input_params.get("context") if isinstance(run.input_params, dict) else {}
    assert isinstance(context, dict)
    assert context.get("sandbox_scope_key") == f"chat-{chat_session_id}"
    timings = context.get("timing_metrics_ms")
    assert isinstance(timings, dict)
    assert int(timings.get("create_run", -1)) >= 0
    assert int(timings.get("sandbox_start", -1)) >= 0


@pytest.mark.asyncio
async def test_coding_agent_create_run_rejects_unavailable_model(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={
            "input": "Use this model",
            "base_revision_id": draft_revision_id,
            "model_id": str(uuid4()),
        },
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "CODING_AGENT_MODEL_UNAVAILABLE"
    assert detail["field"] == "model_id"
    assert "unavailable" in str(detail["message"]).lower()


@pytest.mark.asyncio
async def test_coding_agent_create_run_rejects_opencode_when_engine_unavailable(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    async def _fake_resolve_model(self, *, tenant_id, requested_model_id):
        return None, uuid4()

    monkeypatch.delenv("APPS_SANDBOX_CONTROLLER_URL", raising=False)
    monkeypatch.delenv("APPS_DRAFT_DEV_CONTROLLER_URL", raising=False)
    monkeypatch.delenv("APPS_CODING_AGENT_OPENCODE_BASE_URL", raising=False)
    monkeypatch.delenv("APPS_CODING_AGENT_OPENCODE_USE_SANDBOX_CONTROLLER", raising=False)
    monkeypatch.setenv("APPS_CODING_AGENT_SANDBOX_REQUIRED", "0")
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_ENABLED", "0")

    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "_resolve_run_model_ids", _fake_resolve_model)

    response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={
            "input": "Use OpenCode",
            "base_revision_id": draft_revision_id,
            "engine": "opencode",
        },
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "CODING_AGENT_ENGINE_UNAVAILABLE"
    assert detail["field"] == "engine"


@pytest.mark.asyncio
async def test_coding_agent_create_run_rejects_opencode_when_runtime_path_unavailable(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))
    await _insert_chat_model(
        db_session,
        tenant_id=tenant.id,
        name="Tenant Chat Runtime Path",
        is_default=True,
    )

    async def _fake_resolve_model(self, *, tenant_id, requested_model_id):
        return None, uuid4()

    async def _fail_sandbox_context(self, *, run, app, base_revision, actor_id):
        raise self._engine_unsupported_runtime_error("sandbox workspace path is not resolvable")

    async def _healthy(self, *, force=False):
        return None

    async def _fake_opencode_model(self, *, tenant_id, resolved_model_id):
        return "openai/gpt-5"

    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "_resolve_run_model_ids", _fake_resolve_model)
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "_ensure_run_sandbox_context", _fail_sandbox_context)
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "_resolve_opencode_model_id", _fake_opencode_model)
    monkeypatch.setattr("app.services.opencode_server_client.OpenCodeServerClient.ensure_healthy", _healthy)

    response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={
            "input": "Use OpenCode",
            "base_revision_id": draft_revision_id,
            "engine": "opencode",
        },
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "CODING_AGENT_ENGINE_UNSUPPORTED_RUNTIME"
    assert detail["field"] == "engine"


@pytest.mark.asyncio
async def test_coding_agent_create_run_persists_opencode_execution_engine(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))
    await _insert_chat_model(
        db_session,
        tenant_id=tenant.id,
        name="Tenant Chat OpenCode",
        is_default=True,
    )

    resolved_model_id = uuid4()

    async def _fake_resolve_model(self, *, tenant_id, requested_model_id):
        return None, resolved_model_id

    async def _fake_opencode_model(self, *, tenant_id, resolved_model_id):
        return "openai/gpt-5"

    async def _healthy(self, *, force=False):
        return None

    async def _fake_start_run(self, agent_id, input_params, user_id=None, background=False, mode=None, requested_scopes=None, **kwargs):
        profile = await self.db.get(Agent, agent_id)
        assert profile is not None
        run = AgentRun(
            tenant_id=profile.tenant_id,
            agent_id=agent_id,
            user_id=user_id,
            initiator_user_id=user_id,
            status=RunStatus.queued,
            input_params=input_params,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run.id

    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "_resolve_run_model_ids", _fake_resolve_model)
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "_resolve_opencode_model_id", _fake_opencode_model)
    monkeypatch.setattr(AgentExecutorService, "start_run", _fake_start_run)
    monkeypatch.setattr("app.services.opencode_server_client.OpenCodeServerClient.ensure_healthy", _healthy)

    response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={
            "input": "Use OpenCode",
            "base_revision_id": draft_revision_id,
            "engine": "opencode",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_engine"] == "opencode"

    run_row = await db_session.get(AgentRun, UUID(payload["run_id"]))
    assert run_row is not None
    assert run_row.execution_engine == "opencode"


@pytest.mark.asyncio
async def test_coding_agent_create_run_resolves_opencode_model_from_provider_binding(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    model = await _insert_chat_model(
        db_session,
        tenant_id=tenant.id,
        name="Tenant Chat OpenCode Bound",
        is_default=True,
    )
    binding = ModelProviderBinding(
        model_id=model.id,
        tenant_id=tenant.id,
        provider=ModelProviderType.OPENAI,
        provider_model_id="gpt-4o-mini",
        is_enabled=True,
        priority=0,
        config={},
    )
    db_session.add(binding)
    await db_session.commit()

    captured_input_params: dict = {}

    async def _healthy(self, *, force=False):
        return None

    async def _fake_start_run(self, agent_id, input_params, user_id=None, background=False, mode=None, requested_scopes=None, **kwargs):
        captured_input_params.update(input_params)
        profile = await self.db.get(Agent, agent_id)
        assert profile is not None
        run = AgentRun(
            tenant_id=profile.tenant_id,
            agent_id=agent_id,
            user_id=user_id,
            initiator_user_id=user_id,
            status=RunStatus.queued,
            input_params=input_params,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run.id

    monkeypatch.setattr(AgentExecutorService, "start_run", _fake_start_run)
    monkeypatch.setattr("app.services.opencode_server_client.OpenCodeServerClient.ensure_healthy", _healthy)

    response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={
            "input": "Use OpenCode with mapped model",
            "base_revision_id": draft_revision_id,
            "engine": "opencode",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_engine"] == "opencode"
    context = captured_input_params.get("context", {})
    assert context.get("resolved_model_id") == str(model.id)
    assert context.get("opencode_model_id") == "openai/gpt-4o-mini"


@pytest.mark.asyncio
async def test_coding_agent_create_run_persists_requested_and_resolved_model_ids(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))
    selected_model = await _insert_chat_model(
        db_session,
        tenant_id=tenant.id,
        name="Tenant Chat Preferred",
        is_default=True,
    )

    async def _fake_start_run(self, agent_id, input_params, user_id=None, background=False, mode=None, requested_scopes=None, **kwargs):
        profile = await self.db.get(Agent, agent_id)
        assert profile is not None
        run = AgentRun(
            tenant_id=profile.tenant_id,
            agent_id=agent_id,
            user_id=user_id,
            initiator_user_id=user_id,
            status=RunStatus.queued,
            input_params=input_params,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run.id

    monkeypatch.setattr(AgentExecutorService, "start_run", _fake_start_run)

    response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={
            "input": "Use explicit model",
            "base_revision_id": draft_revision_id,
            "model_id": str(selected_model.id),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["requested_model_id"] == str(selected_model.id)
    assert payload["resolved_model_id"] == str(selected_model.id)

    run_row = await db_session.get(AgentRun, UUID(payload["run_id"]))
    assert run_row is not None
    assert str(run_row.requested_model_id) == str(selected_model.id)
    assert str(run_row.resolved_model_id) == str(selected_model.id)


@pytest.mark.asyncio
async def test_coding_agent_run_keeps_pinned_resolved_model_after_defaults_change(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))
    first_model = await _insert_chat_model(
        db_session,
        tenant_id=tenant.id,
        name="Tenant Chat A",
        is_default=True,
    )
    second_model = await _insert_chat_model(
        db_session,
        tenant_id=tenant.id,
        name="Tenant Chat B",
        is_default=False,
    )

    async def _fake_start_run(self, agent_id, input_params, user_id=None, background=False, mode=None, requested_scopes=None, **kwargs):
        profile = await self.db.get(Agent, agent_id)
        assert profile is not None
        run = AgentRun(
            tenant_id=profile.tenant_id,
            agent_id=agent_id,
            user_id=user_id,
            initiator_user_id=user_id,
            status=RunStatus.queued,
            input_params=input_params,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run.id

    monkeypatch.setattr(AgentExecutorService, "start_run", _fake_start_run)

    response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={
            "input": "Auto model selection",
            "base_revision_id": draft_revision_id,
        },
    )
    assert response.status_code == 200
    run_id = UUID(response.json()["run_id"])
    created = await db_session.get(AgentRun, run_id)
    assert created is not None
    assert created.requested_model_id is None
    assert str(created.resolved_model_id) == str(first_model.id)

    first_model.is_default = False
    second_model.is_default = True
    await db_session.commit()

    persisted = await db_session.get(AgentRun, run_id)
    assert persisted is not None
    assert str(persisted.resolved_model_id) == str(first_model.id)


@pytest.mark.asyncio
async def test_coding_agent_create_run_defaults_to_opencode_engine(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))
    await _insert_chat_model(
        db_session,
        tenant_id=tenant.id,
        name="Tenant Chat Default OpenCode",
        is_default=True,
    )

    resolved_model_id = uuid4()

    async def _fake_resolve_model(self, *, tenant_id, requested_model_id):
        return None, resolved_model_id

    async def _fake_resolve_opencode_model(self, *, tenant_id, resolved_model_id):
        return "openai/gpt-5-mini"

    async def _healthy(self, *, force=False):
        return None

    async def _fake_start_run(self, agent_id, input_params, user_id=None, background=False, mode=None, requested_scopes=None, **kwargs):
        profile = await self.db.get(Agent, agent_id)
        assert profile is not None
        run = AgentRun(
            tenant_id=profile.tenant_id,
            agent_id=agent_id,
            user_id=user_id,
            initiator_user_id=user_id,
            status=RunStatus.queued,
            input_params=input_params,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run.id

    monkeypatch.setenv("APPS_CODING_AGENT_DEFAULT_ENGINE", "opencode")
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "_resolve_run_model_ids", _fake_resolve_model)
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "_resolve_opencode_model_id", _fake_resolve_opencode_model)
    monkeypatch.setattr("app.services.opencode_server_client.OpenCodeServerClient.ensure_healthy", _healthy)
    monkeypatch.setattr(AgentExecutorService, "start_run", _fake_start_run)

    response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={
            "input": "Use the default coding engine",
            "base_revision_id": draft_revision_id,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_engine"] == "opencode"
    assert payload["chat_session_id"]

    run_row = await db_session.get(AgentRun, UUID(payload["run_id"]))
    assert run_row is not None
    assert run_row.execution_engine == "opencode"


@pytest.mark.asyncio
async def test_coding_agent_create_run_rejects_native_when_native_engine_disabled(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    async def _fake_resolve_model(self, *, tenant_id, requested_model_id):
        return None, uuid4()

    monkeypatch.setenv("APPS_CODING_AGENT_NATIVE_ENABLED", "0")
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "_resolve_run_model_ids", _fake_resolve_model)

    response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={
            "input": "Try native engine",
            "base_revision_id": draft_revision_id,
            "engine": "native",
        },
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "CODING_AGENT_ENGINE_UNAVAILABLE"
    assert detail["field"] == "engine"


@pytest.mark.asyncio
async def test_coding_agent_create_run_allows_native_when_native_engine_enabled(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))
    await _insert_chat_model(
        db_session,
        tenant_id=tenant.id,
        name="Tenant Chat Native Enabled",
        is_default=True,
    )

    async def _fake_resolve_model(self, *, tenant_id, requested_model_id):
        return None, uuid4()

    async def _fake_start_run(self, agent_id, input_params, user_id=None, background=False, mode=None, requested_scopes=None, **kwargs):
        profile = await self.db.get(Agent, agent_id)
        assert profile is not None
        run = AgentRun(
            tenant_id=profile.tenant_id,
            agent_id=agent_id,
            user_id=user_id,
            initiator_user_id=user_id,
            status=RunStatus.queued,
            input_params=input_params,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run.id

    monkeypatch.setenv("APPS_CODING_AGENT_NATIVE_ENABLED", "1")
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "_resolve_run_model_ids", _fake_resolve_model)
    monkeypatch.setattr(AgentExecutorService, "start_run", _fake_start_run)

    response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={
            "input": "Use native",
            "base_revision_id": draft_revision_id,
            "engine": "native",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_engine"] == "native"


@pytest.mark.asyncio
async def test_coding_agent_create_run_builds_history_from_owned_chat_session(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    existing_run = await _insert_coding_agent_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.completed,
    )
    session = PublishedAppCodingChatSession(
        published_app_id=UUID(app_id),
        user_id=user.id,
        title="Existing thread",
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    db_session.add_all(
        [
            PublishedAppCodingChatMessage(
                session_id=session.id,
                run_id=existing_run.id,
                role=PublishedAppCodingChatMessageRole.user,
                content="Earlier prompt",
            ),
            PublishedAppCodingChatMessage(
                session_id=session.id,
                run_id=existing_run.id,
                role=PublishedAppCodingChatMessageRole.assistant,
                content="Earlier answer",
            ),
        ]
    )
    await db_session.commit()

    captured: dict[str, object] = {}

    async def _fake_create_run(
        self,
        *,
        app,
        base_revision,
        actor_id,
        user_prompt,
        messages=None,
        requested_scopes=None,
        requested_model_id=None,
        execution_engine="native",
        chat_session_id=None,
    ):
        captured["messages"] = list(messages or [])
        captured["chat_session_id"] = chat_session_id
        run = AgentRun(
            tenant_id=app.tenant_id,
            agent_id=app.agent_id,
            user_id=actor_id,
            initiator_user_id=actor_id,
            status=RunStatus.queued,
            input_params={
                "input": user_prompt,
                "messages": list(messages or []),
                "context": {"chat_session_id": str(chat_session_id) if chat_session_id else None},
            },
            surface=CODING_AGENT_SURFACE,
            published_app_id=app.id,
            base_revision_id=base_revision.id,
            execution_engine=execution_engine,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    monkeypatch.setenv("APPS_CODING_AGENT_NATIVE_ENABLED", "1")
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "create_run", _fake_create_run)

    response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={
            "input": "Continue this thread",
            "base_revision_id": draft_revision_id,
            "engine": "native",
            "chat_session_id": str(session.id),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["chat_session_id"] == str(session.id)
    assert str(captured.get("chat_session_id")) == str(session.id)

    run_messages = captured.get("messages")
    assert isinstance(run_messages, list)
    assert run_messages[0] == {"role": "user", "content": "Earlier prompt"}
    assert run_messages[1] == {"role": "assistant", "content": "Earlier answer"}
    assert run_messages[-1] == {"role": "user", "content": "Continue this thread"}

    created_run_id = UUID(payload["run_id"])
    persisted_user_message = (
        await db_session.execute(
            select(PublishedAppCodingChatMessage).where(
                PublishedAppCodingChatMessage.run_id == created_run_id,
                PublishedAppCodingChatMessage.role == PublishedAppCodingChatMessageRole.user,
            )
        )
    ).scalar_one_or_none()
    assert persisted_user_message is not None
    assert persisted_user_message.content == "Continue this thread"
    assert persisted_user_message.session_id == session.id


@pytest.mark.asyncio
async def test_coding_agent_create_run_rejects_chat_session_not_owned_by_app_scope(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))
    other_app_id, _ = await _create_app_and_draft_revision(
        client,
        headers,
        str(agent.id),
        app_name="Coding Agent API App 2",
    )

    foreign_session = PublishedAppCodingChatSession(
        published_app_id=UUID(other_app_id),
        user_id=user.id,
        title="Other app thread",
        last_message_at=datetime.now(timezone.utc),
    )
    db_session.add(foreign_session)
    await db_session.commit()
    await db_session.refresh(foreign_session)

    monkeypatch.setenv("APPS_CODING_AGENT_NATIVE_ENABLED", "1")

    response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={
            "input": "Use chat session from another app",
            "base_revision_id": draft_revision_id,
            "engine": "native",
            "chat_session_id": str(foreign_session.id),
        },
    )
    assert response.status_code == 404
    assert "chat session" in str(response.json()["detail"]).lower()


@pytest.mark.asyncio
async def test_coding_agent_create_run_tolerates_draft_session_prewarm_failure(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))
    selected_model = await _insert_chat_model(
        db_session,
        tenant_id=tenant.id,
        name="Tenant Chat Prewarm Safe",
        is_default=True,
    )

    async def _fake_start_run(self, agent_id, input_params, user_id=None, background=False, mode=None, requested_scopes=None, **kwargs):
        profile = await self.db.get(Agent, agent_id)
        assert profile is not None
        run = AgentRun(
            tenant_id=profile.tenant_id,
            agent_id=agent_id,
            user_id=user_id,
            initiator_user_id=user_id,
            status=RunStatus.queued,
            input_params=input_params,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run.id

    monkeypatch.setattr(AgentExecutorService, "start_run", _fake_start_run)

    response = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={
            "input": "Create run even if prewarm fails",
            "base_revision_id": draft_revision_id,
            "model_id": str(selected_model.id),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    run_row = await db_session.get(AgentRun, UUID(payload["run_id"]))
    assert run_row is not None
    assert run_row.status == RunStatus.queued
    assert str(run_row.resolved_model_id) == str(selected_model.id)


@pytest.mark.asyncio
async def test_coding_agent_stream_returns_sse_envelopes(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    run = await _insert_coding_agent_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.queued,
    )
    stream_called = False

    async def _fake_stream(self, *, app, run, resume_payload=None):
        nonlocal stream_called
        stream_called = True
        now = datetime.now(timezone.utc).isoformat()
        yield {
            "event": "run.accepted",
            "run_id": str(run.id),
            "app_id": str(app.id),
            "seq": 1,
            "ts": now,
            "stage": "run",
            "payload": {"status": "queued"},
            "diagnostics": [],
        }
        yield {
            "event": "run.completed",
            "run_id": str(run.id),
            "app_id": str(app.id),
            "seq": 2,
            "ts": now,
            "stage": "run",
            "payload": {"status": "completed"},
            "diagnostics": [],
        }

    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "stream_run_events", _fake_stream)

    async with client.stream(
        "GET",
        f"/admin/apps/{app_id}/coding-agent/runs/{run.id}/stream",
        headers=headers,
    ) as stream_resp:
        assert stream_resp.status_code == 200
        assert stream_resp.headers["content-type"].startswith("text/event-stream")
        body = (await stream_resp.aread()).decode("utf-8")
        assert "data: {\"event\": \"run.accepted\"" in body
        assert "data: {\"event\": \"run.completed\"" in body
        assert "\n\n" in body

    assert stream_called is True


@pytest.mark.asyncio
async def test_stream_run_events_emits_assistant_delta_from_final_output_when_tokens_missing(
    client,
    db_session,
    monkeypatch,
):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    run = await _insert_coding_agent_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.queued,
    )
    app = await db_session.get(PublishedApp, UUID(app_id))
    assert app is not None

    async def _fake_run_and_stream(self, run_id, db, resume_payload=None, mode=None):
        run_row = await db.get(AgentRun, run_id)
        assert run_row is not None
        run_row.status = RunStatus.completed
        run_row.output_result = {
            "messages": [{"role": "assistant", "content": "Hello from final output"}],
            "state": {"last_agent_output": "Hello from final output"},
        }
        run_row.completed_at = datetime.now(timezone.utc)
        await db.commit()
        if False:  # pragma: no cover
            yield

    async def _skip_auto_apply(self, run):
        return None

    monkeypatch.setattr(AgentExecutorService, "run_and_stream", _fake_run_and_stream)
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "auto_apply_and_checkpoint", _skip_auto_apply)

    service = PublishedAppCodingAgentRuntimeService(db_session)
    events = []
    async for event in service.stream_run_events(app=app, run=run):
        events.append(event)

    event_names = [event["event"] for event in events]
    assert "assistant.delta" in event_names
    assistant_index = event_names.index("assistant.delta")
    run_completed_index = event_names.index("run.completed")
    assert assistant_index < run_completed_index
    assistant_payload = events[assistant_index]["payload"]
    assert assistant_payload["content"] == "Hello from final output"


@pytest.mark.asyncio
async def test_stream_run_events_uses_prompt_fallback_when_final_output_missing(
    client,
    db_session,
    monkeypatch,
):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    run = await _insert_coding_agent_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.queued,
    )
    run.input_params = {
        "input": "what can you do?",
        "context": {
            "coding_run_sandbox_id": "sandbox-test",
            "coding_run_sandbox_status": "running",
            "coding_run_sandbox_workspace_path": "/workspace",
        },
    }
    await db_session.commit()
    await db_session.refresh(run)

    app = await db_session.get(PublishedApp, UUID(app_id))
    assert app is not None

    async def _fake_run_and_stream(self, run_id, db, resume_payload=None, mode=None):
        run_row = await db.get(AgentRun, run_id)
        assert run_row is not None
        run_row.status = RunStatus.completed
        run_row.output_result = {}
        run_row.completed_at = datetime.now(timezone.utc)
        await db.commit()
        if False:  # pragma: no cover
            yield

    async def _skip_auto_apply(self, run):
        return None

    monkeypatch.setattr(AgentExecutorService, "run_and_stream", _fake_run_and_stream)
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "auto_apply_and_checkpoint", _skip_auto_apply)

    service = PublishedAppCodingAgentRuntimeService(db_session)
    events = []
    async for event in service.stream_run_events(app=app, run=run):
        events.append(event)

    assistant_events = [event for event in events if event["event"] == "assistant.delta"]
    assert assistant_events
    content = str(assistant_events[-1]["payload"].get("content") or "")
    assert "inspect and edit files" in content


@pytest.mark.asyncio
async def test_stream_run_events_handles_detached_run_instance(
    client,
    db_session,
    monkeypatch,
):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    run = await _insert_coding_agent_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.queued,
    )
    app = await db_session.get(PublishedApp, UUID(app_id))
    assert app is not None

    # Simulate router/service passing an instance that is no longer persistent.
    db_session.sync_session.expunge(run)

    async def _fake_run_and_stream(self, run_id, db, resume_payload=None, mode=None):
        run_row = await db.get(AgentRun, run_id)
        assert run_row is not None
        run_row.status = RunStatus.completed
        run_row.output_result = {
            "state": {"last_agent_output": "Detached run handled"},
        }
        run_row.completed_at = datetime.now(timezone.utc)
        await db.commit()
        if False:  # pragma: no cover
            yield

    async def _skip_auto_apply(self, run):
        return None

    monkeypatch.setattr(AgentExecutorService, "run_and_stream", _fake_run_and_stream)
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "auto_apply_and_checkpoint", _skip_auto_apply)

    service = PublishedAppCodingAgentRuntimeService(db_session)
    events = []
    async for event in service.stream_run_events(app=app, run=run):
        events.append(event)

    assert events[-1]["event"] == "run.completed"
    assistant_events = [event for event in events if event["event"] == "assistant.delta"]
    assert assistant_events
    assert assistant_events[-1]["payload"]["content"] == "Detached run handled"


@pytest.mark.asyncio
async def test_stream_run_events_keeps_chat_scoped_sandbox_warm_and_records_first_token(
    client,
    db_session,
    monkeypatch,
):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    run = await _insert_coding_agent_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.queued,
    )
    run_context = run.input_params.get("context") if isinstance(run.input_params, dict) else {}
    if not isinstance(run_context, dict):
        run_context = {}
    chat_session_id = str(uuid4())
    run_context["chat_session_id"] = chat_session_id
    run_context["sandbox_scope_key"] = f"chat-{chat_session_id}"
    run.input_params = {
        **(run.input_params if isinstance(run.input_params, dict) else {}),
        "context": run_context,
    }
    await db_session.commit()
    await db_session.refresh(run)

    app = await db_session.get(PublishedApp, UUID(app_id))
    assert app is not None

    state = {"kept": False, "stopped": False}

    async def _fake_stream(self, ctx):
        yield SimpleNamespace(
            event="assistant.delta",
            stage="assistant",
            payload={"content": "Warm sandbox response"},
            diagnostics=None,
        )
        ctx.run.status = RunStatus.completed
        ctx.run.output_result = {"state": {"last_agent_output": "Warm sandbox response"}}
        ctx.run.completed_at = datetime.now(timezone.utc)
        await self._executor.db.commit()
        if False:  # pragma: no cover
            yield

    async def _skip_auto_apply(self, run):
        return None

    async def _fake_keep_warm(self, *, run_id):
        state["kept"] = True
        return SimpleNamespace(status=PublishedAppCodingRunSandboxStatus.running)

    async def _fake_stop(self, *, run_id, reason):
        state["stopped"] = True
        return SimpleNamespace(status=reason)

    monkeypatch.setattr(NativePublishedAppCodingAgentEngine, "stream", _fake_stream)
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "auto_apply_and_checkpoint", _skip_auto_apply)
    monkeypatch.setattr(PublishedAppCodingRunSandboxService, "keep_session_warm_for_run", _fake_keep_warm)
    monkeypatch.setattr(PublishedAppCodingRunSandboxService, "stop_session_for_run", _fake_stop)
    monkeypatch.setattr(
        PublishedAppCodingAgentRuntimeService,
        "_should_keep_sandbox_warm",
        classmethod(lambda cls, *, run, reason: True),
    )
    monkeypatch.setenv("APPS_CODING_AGENT_CHAT_SANDBOX_REUSE_ENABLED", "1")

    service = PublishedAppCodingAgentRuntimeService(db_session)
    events = [event async for event in service.stream_run_events(app=app, run=run)]

    assert events[-1]["event"] == "run.completed"
    assert state["kept"] is True
    assert state["stopped"] is False

    refreshed = await db_session.get(AgentRun, run.id)
    assert refreshed is not None
    refreshed_context = refreshed.input_params.get("context") if isinstance(refreshed.input_params, dict) else {}
    assert isinstance(refreshed_context, dict)
    assert str(refreshed_context.get("coding_run_sandbox_status")) == "running"
    timings = refreshed_context.get("timing_metrics_ms")
    assert isinstance(timings, dict)
    assert int(timings.get("first_token", -1)) >= 0


@pytest.mark.asyncio
async def test_stream_run_events_fail_closed_when_opencode_engine_raises(
    client,
    db_session,
    monkeypatch,
):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    run = await _insert_coding_agent_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.queued,
        execution_engine="opencode",
    )
    app = await db_session.get(PublishedApp, UUID(app_id))
    assert app is not None

    async def _fail_stream(self, ctx):
        raise RuntimeError("OpenCode upstream unavailable")
        if False:  # pragma: no cover
            yield

    monkeypatch.setattr(OpenCodePublishedAppCodingAgentEngine, "stream", _fail_stream)

    service = PublishedAppCodingAgentRuntimeService(db_session)
    events = []
    async for event in service.stream_run_events(app=app, run=run):
        events.append(event)

    assert events[-1]["event"] == "run.failed"
    assert "OpenCode upstream unavailable" in str(events[-1]["diagnostics"][0]["message"])

    persisted = await db_session.get(AgentRun, run.id)
    assert persisted is not None
    assert persisted.status == RunStatus.failed
    assert "OpenCode upstream unavailable" in str(persisted.error_message)


@pytest.mark.asyncio
async def test_opencode_engine_falls_back_to_coding_run_sandbox_context(db_session):
    run = AgentRun(
        id=uuid4(),
        status=RunStatus.queued,
        input_params={
            "input": "hello",
            "messages": [{"role": "user", "content": "hello"}],
            "context": {
                "coding_run_sandbox_id": "sandbox-fallback",
                "coding_run_sandbox_workspace_path": "/workspace/fallback",
                "resolved_model_id": "openai/gpt-5",
            },
        },
    )
    app = SimpleNamespace(id=uuid4())
    captured: dict[str, str] = {}

    class _FakeOpenCodeClient:
        async def start_run(self, *, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, messages):
            captured["sandbox_id"] = sandbox_id
            captured["workspace_path"] = workspace_path
            return "run-ref-fallback"

        async def stream_run_events(self, *, run_ref):
            assert run_ref == "run-ref-fallback"
            yield {"event": "run.completed", "payload": {"status": "completed"}}

    engine = OpenCodePublishedAppCodingAgentEngine(db=db_session, client=_FakeOpenCodeClient())
    events = [event async for event in engine.stream(ctx=SimpleNamespace(app=app, run=run, resume_payload=None))]
    assert events == []
    assert captured["sandbox_id"] == "sandbox-fallback"
    assert captured["workspace_path"] == "/workspace/fallback"
    timing_metrics = run.input_params.get("context", {}).get("timing_metrics_ms")
    assert isinstance(timing_metrics, dict)
    assert int(timing_metrics.get("opencode_start", -1)) >= 0
    assert run.status == RunStatus.completed


@pytest.mark.asyncio
async def test_opencode_engine_fails_when_apply_patch_failure_is_not_recovered(db_session, monkeypatch):
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_FAIL_ON_UNRECOVERED_APPLY_PATCH", "1")
    run = AgentRun(
        id=uuid4(),
        status=RunStatus.queued,
        input_params={
            "input": "update app",
            "messages": [{"role": "user", "content": "update app"}],
            "context": {
                "coding_run_sandbox_id": "sandbox-apply-fail",
                "coding_run_sandbox_workspace_path": "/workspace/apply-fail",
                "resolved_model_id": "openai/gpt-5",
            },
        },
    )
    app = SimpleNamespace(id=uuid4())

    class _FakeOpenCodeClient:
        async def start_run(self, *, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, messages):
            return "run-ref-apply-fail"

        async def stream_run_events(self, *, run_ref):
            assert run_ref == "run-ref-apply-fail"
            yield {
                "event": "tool.failed",
                "payload": {
                    "tool": "coding_agent_apply_patch",
                    "output": {"error": "Patch apply failed", "code": "PATCH_HUNK_MISMATCH"},
                },
            }
            yield {"event": "run.completed", "payload": {"status": "completed"}}

    engine = OpenCodePublishedAppCodingAgentEngine(db=db_session, client=_FakeOpenCodeClient())
    events = [event async for event in engine.stream(ctx=SimpleNamespace(app=app, run=run, resume_payload=None))]
    assert any(item.event == "tool.failed" for item in events)
    assert run.status == RunStatus.failed
    assert "apply_patch" in str(run.error_message)


@pytest.mark.asyncio
async def test_opencode_engine_allows_recovered_apply_patch_failures(db_session):
    run = AgentRun(
        id=uuid4(),
        status=RunStatus.queued,
        input_params={
            "input": "update app",
            "messages": [{"role": "user", "content": "update app"}],
            "context": {
                "coding_run_sandbox_id": "sandbox-apply-recover",
                "coding_run_sandbox_workspace_path": "/workspace/apply-recover",
                "resolved_model_id": "openai/gpt-5",
            },
        },
    )
    app = SimpleNamespace(id=uuid4())

    class _FakeOpenCodeClient:
        async def start_run(self, *, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, messages):
            return "run-ref-apply-recover"

        async def stream_run_events(self, *, run_ref):
            assert run_ref == "run-ref-apply-recover"
            yield {
                "event": "tool.failed",
                "payload": {
                    "tool": "coding_agent_apply_patch",
                    "output": {"error": "Patch apply failed", "code": "PATCH_HUNK_MISMATCH"},
                },
            }
            yield {
                "event": "tool.completed",
                "payload": {
                    "tool": "coding_agent_apply_patch",
                    "output": {"ok": True, "applied_files": ["src/App.tsx"]},
                },
            }
            yield {"event": "run.completed", "payload": {"status": "completed"}}

    engine = OpenCodePublishedAppCodingAgentEngine(db=db_session, client=_FakeOpenCodeClient())
    events = [event async for event in engine.stream(ctx=SimpleNamespace(app=app, run=run, resume_payload=None))]
    assert any(item.event == "tool.failed" for item in events)
    assert any(item.event == "tool.completed" for item in events)
    assert run.status == RunStatus.completed


def test_build_opencode_effective_prompt_includes_prior_turns() -> None:
    prompt = build_opencode_effective_prompt(
        current_user_prompt="Please continue from there",
        messages=[
            {"role": "user", "content": "Build a profile page."},
            {"role": "assistant", "content": "Done, what should I change next?"},
        ],
        max_chars=2000,
    )
    assert "Conversation context:" in prompt
    assert "User: Build a profile page." in prompt
    assert "Assistant: Done, what should I change next?" in prompt
    assert prompt.endswith("Please continue from there")


def test_build_opencode_effective_prompt_budget_truncation_is_deterministic() -> None:
    messages = [
        {"role": "user", "content": "first " + ("a" * 280)},
        {"role": "assistant", "content": "second " + ("b" * 280)},
        {"role": "user", "content": "third " + ("c" * 280)},
        {"role": "assistant", "content": "fourth " + ("d" * 280)},
        {"role": "user", "content": "fifth " + ("e" * 280)},
    ]

    prompt_a = build_opencode_effective_prompt(
        current_user_prompt="current request",
        messages=messages,
        max_chars=1024,
    )
    prompt_b = build_opencode_effective_prompt(
        current_user_prompt="current request",
        messages=messages,
        max_chars=1024,
    )

    assert prompt_a == prompt_b
    assert "current request" in prompt_a
    assert "fifth " in prompt_a
    assert "first " not in prompt_a


@pytest.mark.asyncio
async def test_stream_auto_apply_runs_before_sandbox_teardown(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    run = await _insert_coding_agent_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.queued,
        execution_engine="native",
    )
    app = await db_session.get(PublishedApp, UUID(app_id))
    assert app is not None

    state = {"stopped": False, "auto_apply_called": False}

    async def _fake_stream(self, ctx):
        ctx.run.status = RunStatus.completed
        ctx.run.output_result = {"state": {"last_agent_output": "Done"}}
        ctx.run.completed_at = datetime.now(timezone.utc)
        await self._executor.db.commit()
        if False:  # pragma: no cover
            yield

    async def _fake_auto_apply(self, run):
        assert state["stopped"] is False
        state["auto_apply_called"] = True
        return SimpleNamespace(
            id=uuid4(),
            entry_file="src/main.tsx",
            files={"src/main.tsx": "export default function App(){return null}"},
        )

    async def _fake_stop(self, *, run_id, reason):
        state["stopped"] = True
        return SimpleNamespace(status=reason)

    monkeypatch.setattr(NativePublishedAppCodingAgentEngine, "stream", _fake_stream)
    monkeypatch.setattr(PublishedAppCodingAgentRuntimeService, "auto_apply_and_checkpoint", _fake_auto_apply)
    monkeypatch.setattr(PublishedAppCodingRunSandboxService, "stop_session_for_run", _fake_stop)

    service = PublishedAppCodingAgentRuntimeService(db_session)
    events = [event async for event in service.stream_run_events(app=app, run=run)]

    assert state["auto_apply_called"] is True
    assert state["stopped"] is True
    assert any(item["event"] == "revision.created" for item in events)
    assert events[-1]["event"] == "run.completed"


@pytest.mark.asyncio
async def test_coding_agent_resume_and_cancel(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    paused_run = await _insert_coding_agent_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.paused,
    )
    running_run = await _insert_coding_agent_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.running,
    )

    resume_calls: list[tuple[str, dict, bool]] = []

    async def _fake_resume(self, run_id, payload, background=False):
        resume_calls.append((str(run_id), payload, background))

    monkeypatch.setattr(AgentExecutorService, "resume_run", _fake_resume)

    resume_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs/{paused_run.id}/resume",
        headers=headers,
        json={"payload": {"decision": "continue"}},
    )
    assert resume_resp.status_code == 200
    assert resume_resp.json()["run_id"] == str(paused_run.id)
    assert resume_calls == [(str(paused_run.id), {"decision": "continue"}, False)]

    bad_resume_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs/{running_run.id}/resume",
        headers=headers,
        json={"payload": {}},
    )
    assert bad_resume_resp.status_code == 409

    cancel_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs/{running_run.id}/cancel",
        headers=headers,
    )
    assert cancel_resp.status_code == 200
    cancel_payload = cancel_resp.json()
    assert cancel_payload["run_id"] == str(running_run.id)
    assert cancel_payload["status"] == "cancelled"


@pytest.mark.asyncio
async def test_coding_agent_cancel_fail_closed_when_opencode_cancel_unconfirmed(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    opencode_run = await _insert_coding_agent_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        status=RunStatus.running,
        execution_engine="opencode",
    )
    opencode_run.engine_run_ref = "opencode-run-1"
    await db_session.commit()

    async def _cancel_unconfirmed(self, run):
        return EngineCancelResult(
            confirmed=False,
            diagnostics=[{"message": "OpenCode cancellation not confirmed"}],
        )

    monkeypatch.setattr(OpenCodePublishedAppCodingAgentEngine, "cancel", _cancel_unconfirmed)

    cancel_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs/{opencode_run.id}/cancel",
        headers=headers,
    )
    assert cancel_resp.status_code == 200
    payload = cancel_resp.json()
    assert payload["run_id"] == str(opencode_run.id)
    assert payload["status"] == "failed"
    assert "not confirmed" in str(payload["error"]).lower()


def test_map_execution_event_includes_patch_failure_diagnostics() -> None:
    event = ExecutionEvent(
        event="on_tool_end",
        data={
            "output": {
                "error": "Patch apply failed",
                "code": "PATCH_HUNK_MISMATCH",
                "failures": [
                    {
                        "path": "src/App.tsx",
                        "recommended_refresh": {"start_line": 10, "end_line": 40},
                    }
                ],
                "result": {"code": "PATCH_HUNK_MISMATCH"},
            }
        },
        run_id="run-1",
        span_id="span-1",
        name="coding_agent_apply_patch",
    )

    mapped = NativePublishedAppCodingAgentEngine._map_execution_event(event)
    assert mapped is not None
    mapped_event, stage, payload, diagnostics = mapped
    assert mapped_event == "tool.failed"
    assert stage == "tool"
    assert payload["tool"] == "coding_agent_apply_patch"
    assert diagnostics is not None
    assert diagnostics[0]["code"] == "PATCH_HUNK_MISMATCH"
    assert diagnostics[0]["patch_failure_count"] == 1
    assert diagnostics[0]["recommended_refresh"]["path"] == "src/App.tsx"
