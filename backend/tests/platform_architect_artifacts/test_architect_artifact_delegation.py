from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.agent.executors.tool import ToolNodeExecutor
from app.db.postgres.models.agents import RunStatus
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.registry import ToolImplementationType, ToolRegistry
from app.services.platform_architect_artifact_delegation_tools import (
    _normalize_artifact_coding_call_payload,
    ensure_platform_architect_artifact_delegation_tools,
)
from app.services.platform_architect_contracts import (
    PLATFORM_ARCHITECT_DOMAIN_TOOLS,
    build_architect_graph_definition,
)


async def _seed_tenant_and_user(db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"Architect Tenant {suffix}", slug=f"architect-tenant-{suffix}")
    user = User(email=f"architect-owner-{suffix}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(user)
    return tenant, user


async def _get_tool_by_slug(db_session, slug: str) -> ToolRegistry:
    result = await db_session.execute(select(ToolRegistry).where(ToolRegistry.slug == slug))
    tool = result.scalar_one()
    return tool


def test_platform_assets_artifact_actions_are_canonical():
    actions = PLATFORM_ARCHITECT_DOMAIN_TOOLS["platform-assets"]["actions"]

    assert "artifacts.create" in actions
    assert "artifacts.update" in actions
    assert "artifacts.convert_kind" in actions
    assert "artifacts.create_test_run" in actions
    assert "artifacts.publish" in actions
    assert "artifacts.delete" in actions
    assert "artifacts.create_or_update_draft" not in actions


def test_architect_graph_instructions_include_artifact_delegation_flow():
    graph = build_architect_graph_definition(
        model_id="model-1",
        tool_ids=[
            "platform-rag",
            "platform-agents",
            "platform-assets",
            "platform-governance",
            "artifact-coding-agent-call",
            "artifact-coding-session-prepare",
            "artifact-coding-session-get-state",
        ],
    )
    runtime_node = next(node for node in graph["nodes"] if node["id"] == "architect_runtime")
    instructions = runtime_node["config"]["instructions"]

    assert "artifact-coding-agent-call" in instructions
    assert "artifact-coding-session-prepare" in instructions
    assert "artifact-coding-session-get-state" in instructions
    assert "artifacts.create, artifacts.update, artifacts.create_test_run" in instructions
    assert "prepare, then artifact-coding-agent-call, then artifact-coding-session-get-state" in instructions


def test_artifact_coding_agent_call_normalizes_wrapped_query_payload():
    payload = _normalize_artifact_coding_call_payload(
        {
            "query": '{"chat_session_id":"11111111-1111-1111-1111-111111111111","messages":[{"role":"user","content":"build it"}]}',
            "tenant_id": "tenant-1",
        }
    )
    assert payload["chat_session_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["messages"][0]["content"] == "build it"


@pytest.mark.asyncio
async def test_delegation_tools_seed_prepare_get_state_and_agent_call(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)

    tool_ids = await ensure_platform_architect_artifact_delegation_tools(
        db_session,
        tenant_id=tenant.id,
        actor_user_id=user.id,
    )
    await db_session.commit()

    tools = (
        await db_session.execute(
            select(ToolRegistry).where(ToolRegistry.id.in_(tool_ids))
        )
    ).scalars().all()
    by_slug = {tool.slug: tool for tool in tools}

    assert set(by_slug.keys()) == {
        "artifact-coding-session-prepare",
        "artifact-coding-session-get-state",
        "artifact-coding-agent-call",
    }
    assert by_slug["artifact-coding-session-prepare"].implementation_type == ToolImplementationType.FUNCTION
    assert by_slug["artifact-coding-session-get-state"].implementation_type == ToolImplementationType.FUNCTION
    assert by_slug["artifact-coding-agent-call"].implementation_type == ToolImplementationType.FUNCTION
    assert by_slug["artifact-coding-agent-call"].config_schema["implementation"]["function_name"] == "artifact_coding_agent_call"


@pytest.mark.asyncio
async def test_artifact_coding_agent_call_uses_runtime_service_session_flow(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    await ensure_platform_architect_artifact_delegation_tools(db_session, tenant_id=tenant.id, actor_user_id=user.id)
    tool = await _get_tool_by_slug(db_session, "artifact-coding-agent-call")
    captured: dict[str, object] = {}
    fake_session = SimpleNamespace(id=uuid4())
    fake_run = SimpleNamespace(
        id=uuid4(),
        status=RunStatus.completed,
        surface="artifact_coding_agent",
        output_result={
            "state": {"last_agent_output": {"files": [{"path": "main.py", "content": "print('ok')"}]}},
            "context": {"artifact_coding_session_id": str(fake_session.id)},
        },
        error_message=None,
    )

    class _FakeDb:
        async def get(self, model, identifier):
            del model
            if str(identifier) == str(fake_run.id):
                return fake_run
            return None

        async def refresh(self, _obj):
            return None

    class _FakeRuntime:
        def __init__(self, db):
            captured["db"] = db

        async def start_prompt_run(self, **kwargs):
            captured["start_prompt_run"] = kwargs
            return fake_session, object(), fake_run

        async def reconcile_session_run(self, *, session, run):
            captured["reconcile"] = {"session_id": str(session.id), "run_id": str(run.id)}

    class _FakeExecutor:
        def __init__(self, db):
            captured["executor_db"] = db

        async def run_and_stream(self, run_id, db, resume_payload=None, mode=None):
            captured["run_and_stream"] = {
                "run_id": str(run_id),
                "resume_payload": resume_payload,
                "mode": str(mode),
            }
            if False:
                yield None

    @asynccontextmanager
    async def _session_override():
        yield _FakeDb()

    monkeypatch.setattr(
        "app.services.platform_architect_artifact_delegation_tools.get_session",
        _session_override,
    )
    monkeypatch.setattr(
        "app.services.platform_architect_artifact_delegation_tools.ArtifactCodingRuntimeService",
        _FakeRuntime,
    )
    monkeypatch.setattr(
        "app.services.platform_architect_artifact_delegation_tools.AgentExecutorService",
        _FakeExecutor,
    )

    executor = ToolNodeExecutor(tenant_id=tenant.id, db=db_session)
    result = await executor.execute(
        state={
            "context": {
                "context": {"chat_session_id": str(fake_session.id)},
                "messages": [
                    {"role": "system", "content": "Implement the files."},
                    {"role": "user", "content": "Build the extractor."},
                ]
            }
        },
        config={"tool_id": str(tool.id)},
        context={
            "node_id": "architect-tool",
            "mode": "debug",
            "tenant_id": str(tenant.id),
            "user_id": str(user.id),
            "initiator_user_id": str(user.id),
            "chat_session_id": str(fake_session.id),
        },
    )

    payload = result["context"]
    assert payload["mode"] == "sync"
    assert payload["chat_session_id"] == str(fake_session.id)
    assert payload["surface"] == "artifact_coding_agent"
    assert captured["start_prompt_run"]["chat_session_id"] == fake_session.id
    assert captured["start_prompt_run"]["tenant_id"] == tenant.id
    assert captured["start_prompt_run"]["user_id"] == user.id


@pytest.mark.asyncio
async def test_artifact_coding_agent_call_falls_back_to_latest_session_when_missing(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    await ensure_platform_architect_artifact_delegation_tools(db_session, tenant_id=tenant.id, actor_user_id=user.id)
    tool = await _get_tool_by_slug(db_session, "artifact-coding-agent-call")
    fake_session = SimpleNamespace(id=uuid4())
    fake_run = SimpleNamespace(
        id=uuid4(),
        status=RunStatus.completed,
        surface="artifact_coding_agent",
        output_result={"state": {"last_agent_output": {"ok": True}}, "context": {}},
        error_message=None,
    )
    captured: dict[str, object] = {}

    class _FakeDb:
        async def get(self, model, identifier):
            del model
            if str(identifier) == str(fake_run.id):
                return fake_run
            return None

        async def refresh(self, _obj):
            return None

    class _FakeRuntime:
        def __init__(self, db):
            del db

        async def start_prompt_run(self, **kwargs):
            captured["chat_session_id"] = kwargs["chat_session_id"]
            return fake_session, object(), fake_run

        async def reconcile_session_run(self, *, session, run):
            del session, run

    class _FakeExecutor:
        def __init__(self, db):
            del db

        async def run_and_stream(self, run_id, db, resume_payload=None, mode=None):
            del run_id, db, resume_payload, mode
            if False:
                yield None

    @asynccontextmanager
    async def _session_override():
        yield _FakeDb()

    async def _resolve_latest(*, db, tenant_id, user_id):
        del db, tenant_id, user_id
        return fake_session.id

    monkeypatch.setattr(
        "app.services.platform_architect_artifact_delegation_tools.get_session",
        _session_override,
    )
    monkeypatch.setattr(
        "app.services.platform_architect_artifact_delegation_tools.ArtifactCodingRuntimeService",
        _FakeRuntime,
    )
    monkeypatch.setattr(
        "app.services.platform_architect_artifact_delegation_tools.AgentExecutorService",
        _FakeExecutor,
    )
    monkeypatch.setattr(
        "app.services.platform_architect_artifact_delegation_tools._resolve_latest_session_id_for_user",
        _resolve_latest,
    )

    executor = ToolNodeExecutor(tenant_id=tenant.id, db=db_session)
    await executor.execute(
        state={"context": {"query": '{"messages":[{"role":"user","content":"build it"}],"context":{}}'}},
        config={"tool_id": str(tool.id)},
        context={
            "node_id": "architect-tool",
            "mode": "debug",
            "tenant_id": str(tenant.id),
            "user_id": str(user.id),
            "initiator_user_id": str(user.id),
        },
    )

    assert captured["chat_session_id"] == fake_session.id
