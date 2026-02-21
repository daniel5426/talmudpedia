from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.agent.execution.service import AgentExecutorService
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.registry import (
    ToolDefinitionScope,
    ToolImplementationType,
    ToolRegistry,
    ToolStatus,
)
from app.services.published_app_draft_dev_runtime_client import PublishedAppDraftDevRuntimeClient
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from app.services.tool_function_registry import get_tool_function
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


async def _create_app_and_draft_revision(client, headers: dict[str, str], agent_id: str) -> tuple[str, str]:
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Coding Agent Contract Context App",
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


@pytest.mark.asyncio
async def test_create_run_injects_selected_agent_contract_in_context(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    tool = ToolRegistry(
        tenant_id=tenant.id,
        name="Stat Output Tool",
        slug=f"stat-output-{uuid4().hex[:8]}",
        description="Tool with optional x-ui metadata.",
        scope=ToolDefinitionScope.TENANT,
        schema={
            "input": {
                "type": "object",
                "properties": {"topic": {"type": "string"}},
                "required": ["topic"],
            },
            "output": {
                "type": "object",
                "properties": {"total": {"type": "number"}},
                "required": ["total"],
                "x-ui": {"kind": "stat", "title": "Total"},
            },
        },
        config_schema={},
        status=ToolStatus.PUBLISHED,
        implementation_type=ToolImplementationType.CUSTOM,
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.flush()

    agent.tools = [str(tool.id)]
    agent.referenced_tool_ids = [str(tool.id)]
    agent.graph_definition = {
        "nodes": [
            {
                "id": "agent",
                "type": "agent",
                "position": {"x": 0, "y": 0},
                "config": {"tools": [str(tool.id)]},
            }
        ],
        "edges": [],
    }
    await db_session.commit()

    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    captured_input_params: dict[str, object] = {}

    async def _fake_start_run(
        self,
        agent_id,
        input_params,
        user_id=None,
        background=False,
        mode=None,
        requested_scopes=None,
        **kwargs,
    ):
        captured_input_params.clear()
        captured_input_params.update(input_params or {})
        run = AgentRun(
            tenant_id=tenant.id,
            agent_id=agent_id,
            user_id=user_id,
            initiator_user_id=user_id,
            status=RunStatus.queued,
            input_params=input_params,
            surface=CODING_AGENT_SURFACE,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run.id

    async def _fake_ensure_coding_agent_profile(db, tenant_id):
        return agent

    async def _fake_resolve_run_model_ids(self, *, tenant_id, requested_model_id):
        return requested_model_id, None

    monkeypatch.setattr(AgentExecutorService, "start_run", _fake_start_run)
    monkeypatch.setattr(
        "app.services.published_app_coding_agent_runtime.ensure_coding_agent_profile",
        _fake_ensure_coding_agent_profile,
    )
    monkeypatch.setattr(
        PublishedAppCodingAgentRuntimeService,
        "_resolve_run_model_ids",
        _fake_resolve_run_model_ids,
    )

    create_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={
            "input": "Build a dashboard from the selected agent tools",
            "base_revision_id": draft_revision_id,
        },
    )
    assert create_resp.status_code == 200

    context = captured_input_params.get("context")
    assert isinstance(context, dict)
    selected_agent_contract = context.get("selected_agent_contract")
    assert isinstance(selected_agent_contract, dict)
    assert selected_agent_contract["agent"]["id"] == str(agent.id)
    assert selected_agent_contract["resolved_tool_count"] == 1
    resolved_tool = selected_agent_contract["tools"][0]
    assert resolved_tool["id"] == str(tool.id)
    assert resolved_tool["ui_hints"]["kind"] == "stat"
    assert resolved_tool["output_schema"]["x-ui"]["title"] == "Total"
    run_messages = captured_input_params.get("messages")
    assert isinstance(run_messages, list)
    assert run_messages
    system_messages = [
        item for item in run_messages if isinstance(item, dict) and item.get("role") == "system"
    ]
    assert system_messages
    assert any(
        "Selected app agent integration contract" in str(item.get("content") or "")
        for item in system_messages
    )

    created_run_id = create_resp.json()["run_id"]
    run_row = await db_session.get(AgentRun, UUID(created_run_id))
    assert run_row is not None
    run_context = (run_row.input_params or {}).get("context") if isinstance(run_row.input_params, dict) else {}
    assert isinstance(run_context, dict)
    assert isinstance(run_context.get("selected_agent_contract"), dict)


@pytest.mark.asyncio
async def test_describe_selected_agent_contract_tool_returns_compact_summary(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))

    tool = ToolRegistry(
        tenant_id=tenant.id,
        name="Contract Summary Tool",
        slug=f"contract-summary-{uuid4().hex[:8]}",
        description="Summary tool output contract.",
        scope=ToolDefinitionScope.TENANT,
        schema={
            "input": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic"},
                    "range": {"type": "string"},
                },
                "required": ["topic"],
            },
            "output": {
                "type": "object",
                "properties": {
                    "total": {"type": "number", "description": "Total"},
                    "items": {"type": "array"},
                },
                "required": ["total"],
                "x-ui": {"kind": "table", "title": "Rows"},
            },
        },
        config_schema={},
        status=ToolStatus.PUBLISHED,
        implementation_type=ToolImplementationType.CUSTOM,
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.flush()

    agent.tools = [str(tool.id)]
    agent.referenced_tool_ids = [str(tool.id)]
    agent.graph_definition = {
        "nodes": [
            {
                "id": "agent",
                "type": "agent",
                "position": {"x": 0, "y": 0},
                "config": {"tools": [str(tool.id)]},
            }
        ],
        "edges": [],
    }
    await db_session.commit()

    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    async def _fake_start_run(
        self,
        agent_id,
        input_params,
        user_id=None,
        background=False,
        mode=None,
        requested_scopes=None,
        **kwargs,
    ):
        run = AgentRun(
            tenant_id=tenant.id,
            agent_id=agent_id,
            user_id=user_id,
            initiator_user_id=user_id,
            status=RunStatus.queued,
            input_params=input_params,
            surface=CODING_AGENT_SURFACE,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run.id

    async def _fake_ensure_coding_agent_profile(db, tenant_id):
        return agent

    async def _fake_resolve_run_model_ids(self, *, tenant_id, requested_model_id):
        return requested_model_id, None

    async def _fake_heartbeat_session(self, *, sandbox_id: str, idle_timeout_seconds: int):
        return {"status": "running", "sandbox_id": sandbox_id}

    class _FakeDraftDevSession:
        status = "running"
        sandbox_id = "sandbox-test"
        last_error = None

    async def _fake_ensure_active_session(self, *, app, revision, user_id):
        return _FakeDraftDevSession()

    monkeypatch.setattr(AgentExecutorService, "start_run", _fake_start_run)
    monkeypatch.setattr(
        "app.services.published_app_coding_agent_runtime.ensure_coding_agent_profile",
        _fake_ensure_coding_agent_profile,
    )
    monkeypatch.setattr(
        PublishedAppCodingAgentRuntimeService,
        "_resolve_run_model_ids",
        _fake_resolve_run_model_ids,
    )
    monkeypatch.setattr(
        PublishedAppDraftDevRuntimeClient,
        "heartbeat_session",
        _fake_heartbeat_session,
    )
    monkeypatch.setattr(
        PublishedAppDraftDevRuntimeService,
        "ensure_active_session",
        _fake_ensure_active_session,
    )

    @asynccontextmanager
    async def _fake_get_session():
        yield db_session

    monkeypatch.setattr(
        "app.services.published_app_coding_agent_tools.get_session",
        _fake_get_session,
    )

    create_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/runs",
        headers=headers,
        json={
            "input": "create app ui",
            "base_revision_id": draft_revision_id,
        },
    )
    assert create_resp.status_code == 200
    run_id = create_resp.json()["run_id"]

    describe_fn = get_tool_function("coding_agent_describe_selected_agent_contract")
    assert describe_fn is not None
    summary = await describe_fn(
        {
            "run_id": run_id,
            "max_tools": 5,
            "max_properties_per_schema": 1,
            "include_unresolved": True,
        }
    )
    assert isinstance(summary, dict)
    assert summary["app_id"] == app_id
    assert summary["agent_id"] == str(agent.id)
    assert summary["resolved_tool_count"] == 1
    assert summary["returned_tool_count"] == 1
    first_tool = summary["tools"][0]
    assert first_tool["slug"] == tool.slug
    assert first_tool["ui_hints"]["kind"] == "table"
    assert first_tool["input_schema"]["property_count"] == 2
    assert first_tool["input_schema"]["truncated_properties"] is True
    assert first_tool["output_schema"]["property_count"] == 2
    assert first_tool["output_schema"]["truncated_properties"] is True
    assert summary["truncated_tools"] is False
    assert isinstance(summary["unresolved_tool_references"], list)
