from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.agent.executors.tool import ToolNodeExecutor
from app.agent.execution.service import AgentExecutorService
from app.db.postgres.models.agents import Agent, AgentRun, AgentStatus, RunStatus
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.registry import (
    ToolDefinitionScope,
    ToolImplementationType,
    ToolRegistry,
    ToolStatus,
)


async def _seed_tenant_and_user(db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"Tenant {suffix}", slug=f"tenant-{suffix}")
    user = User(email=f"owner-{suffix}@example.com", role="user")
    db_session.add_all([tenant, user])
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(user)
    return tenant, user


async def _create_agent(
    db_session,
    *,
    tenant_id: UUID,
    user_id: UUID,
    slug: str,
    status: AgentStatus,
) -> Agent:
    agent = Agent(
        tenant_id=tenant_id,
        name=f"Agent {slug}",
        slug=slug,
        description="agent_call target",
        graph_definition={"spec_version": "1.0", "nodes": [], "edges": []},
        status=status,
        created_by=user_id,
        is_active=True,
    )
    if status == AgentStatus.published:
        agent.published_at = datetime.now(timezone.utc)
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)
    return agent


async def _create_agent_call_tool(
    db_session,
    *,
    tenant_id: UUID,
    target_agent_slug: str | None = None,
    target_agent_id: UUID | None = None,
    timeout_s: int | None = None,
) -> ToolRegistry:
    implementation: dict[str, object] = {"type": "agent_call"}
    if target_agent_slug:
        implementation["target_agent_slug"] = target_agent_slug
    if target_agent_id:
        implementation["target_agent_id"] = str(target_agent_id)

    config_schema: dict[str, object] = {"implementation": implementation}
    if timeout_s is not None:
        config_schema["execution"] = {"timeout_s": timeout_s}

    tool = ToolRegistry(
        tenant_id=tenant_id,
        name=f"Agent Call {uuid4().hex[:6]}",
        slug=f"agent-call-{uuid4().hex[:8]}",
        description="call another agent",
        scope=ToolDefinitionScope.TENANT,
        schema={"input": {"type": "object"}, "output": {"type": "object"}},
        config_schema=config_schema,
        status=ToolStatus.PUBLISHED,
        version="1.0.0",
        implementation_type=ToolImplementationType.AGENT_CALL,
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


@pytest.mark.asyncio
async def test_agent_call_tool_success_returns_compact_output(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"child-{uuid4().hex[:8]}",
        status=AgentStatus.published,
    )
    tool = await _create_agent_call_tool(db_session, tenant_id=tenant.id, target_agent_slug=target.slug)

    async def fake_run_and_stream(self, run_id, db, resume_payload=None, mode=None):
        run = await db.get(AgentRun, run_id)
        run.status = RunStatus.completed
        run.output_result = {
            "state": {"last_agent_output": {"answer": "child-ok"}},
            "context": {"source": "child"},
        }
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        if False:
            yield None

    monkeypatch.setattr(AgentExecutorService, "run_and_stream", fake_run_and_stream)

    executor = ToolNodeExecutor(tenant_id=tenant.id, db=db_session)
    result = await executor.execute(
        state={"context": {"input": "hello child"}},
        config={"tool_id": str(tool.id)},
        context={"node_id": "tool-node", "mode": "debug"},
    )

    payload = result["context"]
    assert payload["mode"] == "sync"
    assert payload["status"] == "completed"
    assert payload["target_agent_slug"] == target.slug
    assert payload["output"] == {"answer": "child-ok"}
    assert payload["context"] == {"source": "child"}
    assert UUID(payload["run_id"])


@pytest.mark.asyncio
async def test_agent_call_tool_rejects_unpublished_target(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"draft-child-{uuid4().hex[:8]}",
        status=AgentStatus.draft,
    )
    tool = await _create_agent_call_tool(db_session, tenant_id=tenant.id, target_agent_slug=target.slug)

    executor = ToolNodeExecutor(tenant_id=tenant.id, db=db_session)
    with pytest.raises(PermissionError, match="published"):
        await executor.execute(
            state={"context": {"input": "hello"}},
            config={"tool_id": str(tool.id)},
            context={"node_id": "tool-node", "mode": "debug"},
        )


@pytest.mark.asyncio
async def test_agent_call_tool_timeout_returns_failed_payload(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        slug=f"slow-child-{uuid4().hex[:8]}",
        status=AgentStatus.published,
    )
    tool = await _create_agent_call_tool(
        db_session,
        tenant_id=tenant.id,
        target_agent_slug=target.slug,
        timeout_s=1,
    )

    async def slow_run_and_stream(self, run_id, db, resume_payload=None, mode=None):
        await asyncio.sleep(1.2)
        if False:
            yield None

    monkeypatch.setattr(AgentExecutorService, "run_and_stream", slow_run_and_stream)

    executor = ToolNodeExecutor(tenant_id=tenant.id, db=db_session)
    result = await executor.execute(
        state={"context": {"input": "slow call"}},
        config={"tool_id": str(tool.id)},
        context={"node_id": "tool-node", "mode": "debug"},
    )

    payload = result["context"]
    assert payload["status"] == "failed"
    assert "timed out" in payload["error"]

    run = await db_session.get(AgentRun, UUID(payload["run_id"]))
    assert run is not None
    assert run.status == RunStatus.failed


@pytest.mark.asyncio
async def test_agent_call_tool_denies_cross_tenant_target(db_session):
    tenant_a, user_a = await _seed_tenant_and_user(db_session)
    tenant_b, user_b = await _seed_tenant_and_user(db_session)
    target = await _create_agent(
        db_session,
        tenant_id=tenant_b.id,
        user_id=user_b.id,
        slug=f"other-tenant-{uuid4().hex[:8]}",
        status=AgentStatus.published,
    )
    tool = await _create_agent_call_tool(
        db_session,
        tenant_id=tenant_a.id,
        target_agent_id=target.id,
    )

    executor = ToolNodeExecutor(tenant_id=tenant_a.id, db=db_session)
    with pytest.raises(ValueError, match="tenant scope"):
        await executor.execute(
            state={"context": {"input": "hello"}},
            config={"tool_id": str(tool.id)},
            context={"node_id": "tool-node", "mode": "debug"},
        )
