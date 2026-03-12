from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.agent.executors.tool import ToolNodeExecutor
from app.db.postgres.models.agents import AgentStatus
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.registry import ToolImplementationType, ToolRegistry
from app.services.artifact_coding_agent_profile import ensure_artifact_coding_agent_profile
from app.services.platform_architect_artifact_delegation_tools import (
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
    assert by_slug["artifact-coding-agent-call"].implementation_type == ToolImplementationType.AGENT_CALL
    assert by_slug["artifact-coding-agent-call"].config_schema["implementation"]["target_agent_slug"] == "artifact-coding-agent"


@pytest.mark.asyncio
async def test_artifact_coding_agent_call_rejects_unpublished_target(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    await ensure_platform_architect_artifact_delegation_tools(db_session, tenant_id=tenant.id, actor_user_id=user.id)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)
    agent.status = AgentStatus.draft
    await db_session.commit()

    tool = await _get_tool_by_slug(db_session, "artifact-coding-agent-call")
    executor = ToolNodeExecutor(tenant_id=tenant.id, db=db_session)

    with pytest.raises(PermissionError, match="published"):
        await executor.execute(
            state={"context": {"input": "hello"}},
            config={"tool_id": str(tool.id)},
            context={"node_id": "architect-tool", "mode": "debug"},
        )


@pytest.mark.asyncio
async def test_artifact_coding_agent_call_rejects_cross_tenant_target(db_session):
    tenant_a, user_a = await _seed_tenant_and_user(db_session)
    tenant_b, user_b = await _seed_tenant_and_user(db_session)
    await ensure_platform_architect_artifact_delegation_tools(db_session, tenant_id=tenant_a.id, actor_user_id=user_a.id)
    agent_b = await ensure_artifact_coding_agent_profile(db_session, tenant_b.id, actor_user_id=user_b.id)

    tool = await _get_tool_by_slug(db_session, "artifact-coding-agent-call")
    tool.config_schema = {
        **dict(tool.config_schema or {}),
        "implementation": {
            "type": "agent_call",
            "target_agent_id": str(agent_b.id),
        },
    }
    await db_session.commit()

    executor = ToolNodeExecutor(tenant_id=tenant_a.id, db=db_session)
    with pytest.raises(ValueError, match="tenant scope"):
        await executor.execute(
            state={"context": {"input": "hello"}},
            config={"tool_id": str(tool.id)},
            context={"node_id": "architect-tool", "mode": "debug"},
        )
