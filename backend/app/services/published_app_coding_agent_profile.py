from __future__ import annotations

import os
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import Agent, AgentStatus
from app.db.postgres.models.registry import ModelCapabilityType, ModelRegistry
from app.services.published_app_coding_agent_tools import ensure_coding_agent_tools

CODING_AGENT_PROFILE_SLUG = "published-app-coding-agent"
CODING_AGENT_PROFILE_NAME = "Published App Coding Agent"


def _build_coding_agent_graph(model_id: str, tool_ids: list[str]) -> dict:
    max_tool_iterations = int(os.getenv("APPS_CODING_AGENT_MAX_TOOL_ITERATIONS", "30") or 30)
    if max_tool_iterations < 1:
        max_tool_iterations = 1
    tool_timeout_s = int(os.getenv("APPS_CODING_AGENT_TOOL_TIMEOUT_SECONDS", "120") or 120)
    if tool_timeout_s < 15:
        tool_timeout_s = 15

    instructions = (
        "You are the coding runtime for a published app draft workspace. "
        "Use the available tools to inspect files, edit code, validate with tests/build checks, "
        "and create checkpoints for safe restore points. "
        "Start by inspecting the workspace with tools before asking follow-up questions. "
        "Use patch-first editing: prefer `coding_agent_apply_patch` for every code change. "
        "Use `coding_agent_read_file_range` and `coding_agent_workspace_index` to avoid full-file reads unless necessary. "
        "For straightforward requests (for example color/style text changes), apply an initial patch proactively. "
        "Ask clarification only when the target is genuinely ambiguous after search/read steps. "
        "Only modify files through tools, keep edits within project policy constraints, "
        "When calling file tools, always provide explicit path keys: `path` for reads/deletes and "
        "`from_path` + `to_path` for rename, and `patch` for patch application. "
        "`coding_agent_write_file` is deprecated and may be disabled; do not rely on it. "
        "Do not claim that changes are complete unless an apply_patch/rename/delete tool call succeeded. "
        "If a tool fails, explain the failure clearly instead of pretending the edit was applied. "
        "When patch apply fails, use returned refresh windows to re-read only the relevant line ranges before retrying. "
        "At the start of every run, inspect the selected-agent contract from context and call "
        "`coding_agent_describe_selected_agent_contract` for compact summaries, or "
        "`coding_agent_get_agent_integration_contract` for full raw contract payloads when needed. "
        "When implementing runtime-agent integrations in the app UI, use tool input/output schemas plus optional `x-ui` hints as source of truth. "
        "and summarize completed changes and verification results. "
        "Always respond with natural-language text to every user message. "
        "If the user sends a greeting or general question, answer directly and briefly."
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
                    "max_tool_iterations": max_tool_iterations,
                    "tool_timeout_s": tool_timeout_s,
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


async def resolve_coding_agent_chat_model_id(db: AsyncSession, tenant_id) -> str:
    return await _resolve_default_chat_model_id(db, tenant_id)


def _extract_profile_model_id(graph_definition: dict[str, Any] | None) -> str | None:
    if not isinstance(graph_definition, dict):
        return None
    nodes = graph_definition.get("nodes")
    if not isinstance(nodes, list):
        return None
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if str(node.get("type") or "").strip().lower() != "agent":
            continue
        config = node.get("config")
        if not isinstance(config, dict):
            continue
        model_id = str(config.get("model_id") or "").strip()
        if model_id:
            return model_id
    return None


async def ensure_coding_agent_profile(db: AsyncSession, tenant_id) -> Agent:
    # Import side-effect ensures function tools are registered in registry.
    import app.services.published_app_coding_agent_tools  # noqa: F401

    tool_ids = await ensure_coding_agent_tools(db)

    result = await db.execute(
        select(Agent).where(
            Agent.slug == CODING_AGENT_PROFILE_SLUG,
            Agent.tenant_id == tenant_id,
        )
    )
    agent = result.scalar_one_or_none()

    if agent is None:
        model_id = await resolve_coding_agent_chat_model_id(db, tenant_id)
        graph_definition = _build_coding_agent_graph(model_id, tool_ids)
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

    model_id = _extract_profile_model_id(agent.graph_definition)
    if not model_id:
        model_id = await resolve_coding_agent_chat_model_id(db, tenant_id)
    graph_definition = _build_coding_agent_graph(model_id, tool_ids)

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
