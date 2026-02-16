from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import Agent, AgentStatus
from app.db.postgres.models.registry import ModelCapabilityType, ModelRegistry
from app.services.published_app_coding_agent_tools import ensure_coding_agent_tools

CODING_AGENT_PROFILE_SLUG = "published-app-coding-agent"
CODING_AGENT_PROFILE_NAME = "Published App Coding Agent"


def _build_coding_agent_graph(model_id: str, tool_ids: list[str]) -> dict:
    instructions = (
        "You are the coding runtime for a published app draft workspace. "
        "Use the available tools to inspect files, edit code, validate with tests/build checks, "
        "and create checkpoints for safe restore points. "
        "Only modify files through tools, keep edits within project policy constraints, "
        "and summarize completed changes and verification results."
    )
    return {
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {
                "id": "coding_agent",
                "type": "agent",
                "position": {"x": 260, "y": 0},
                "config": {
                    "name": "Coding Agent",
                    "model_id": model_id,
                    "instructions": instructions,
                    "include_chat_history": True,
                    "reasoning_effort": "medium",
                    "output_format": "text",
                    "tools": tool_ids,
                    "tool_execution_mode": "sequential",
                    "max_tool_iterations": 24,
                    "tool_timeout_s": 360,
                },
            },
            {
                "id": "end",
                "type": "end",
                "position": {"x": 520, "y": 0},
                "config": {"output_variable": "last_agent_output"},
            },
        ],
        "edges": [
            {"id": "e-start-agent", "source": "start", "target": "coding_agent", "type": "control"},
            {"id": "e-agent-end", "source": "coding_agent", "target": "end", "type": "control"},
        ],
    }


async def _resolve_default_chat_model_id(db: AsyncSession, tenant_id) -> str:
    default_stmt = select(ModelRegistry).where(
        ModelRegistry.tenant_id == tenant_id,
        ModelRegistry.capability_type == ModelCapabilityType.CHAT,
        ModelRegistry.is_default == True,
        ModelRegistry.is_active == True,
    )
    res = await db.execute(default_stmt)
    model = res.scalar_one_or_none()
    if model:
        return str(model.id)

    global_default_stmt = select(ModelRegistry).where(
        ModelRegistry.tenant_id == None,
        ModelRegistry.capability_type == ModelCapabilityType.CHAT,
        ModelRegistry.is_default == True,
        ModelRegistry.is_active == True,
    )
    res = await db.execute(global_default_stmt)
    model = res.scalar_one_or_none()
    if model:
        return str(model.id)

    fallback_stmt = select(ModelRegistry).where(
        ModelRegistry.capability_type == ModelCapabilityType.CHAT,
        ModelRegistry.is_active == True,
        or_(ModelRegistry.tenant_id == tenant_id, ModelRegistry.tenant_id == None),
    )
    res = await db.execute(fallback_stmt)
    model = res.scalars().first()
    if model is None:
        raise ValueError("No active chat model is available for coding-agent profile")
    return str(model.id)


async def ensure_coding_agent_profile(db: AsyncSession, tenant_id) -> Agent:
    # Import side-effect ensures function tools are registered in registry.
    import app.services.published_app_coding_agent_tools  # noqa: F401

    tool_ids = await ensure_coding_agent_tools(db)
    model_id = await _resolve_default_chat_model_id(db, tenant_id)
    graph_definition = _build_coding_agent_graph(model_id, tool_ids)

    result = await db.execute(
        select(Agent).where(
            Agent.slug == CODING_AGENT_PROFILE_SLUG,
            Agent.tenant_id == tenant_id,
        )
    )
    agent = result.scalar_one_or_none()

    if agent is None:
        agent = Agent(
            tenant_id=tenant_id,
            name=CODING_AGENT_PROFILE_NAME,
            slug=CODING_AGENT_PROFILE_SLUG,
            description="System coding-agent profile for published app runtime editing.",
            graph_definition=graph_definition,
            tools=tool_ids,
            referenced_tool_ids=tool_ids,
            status=AgentStatus.published,
            is_active=True,
            is_public=False,
        )
        db.add(agent)
        await db.flush()
        return agent

    agent.name = CODING_AGENT_PROFILE_NAME
    agent.description = "System coding-agent profile for published app runtime editing."
    agent.graph_definition = graph_definition
    agent.tools = tool_ids
    agent.referenced_tool_ids = tool_ids
    agent.status = AgentStatus.published
    agent.is_active = True
    agent.is_public = False
    await db.flush()
    return agent
