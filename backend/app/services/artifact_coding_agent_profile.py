from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import Agent, AgentStatus
from app.services.artifact_coding_agent_tools import ARTIFACT_CODING_AGENT_SURFACE, ensure_artifact_coding_tools
from app.services.workload_provisioning_service import WorkloadProvisioningService

ARTIFACT_CODING_AGENT_PROFILE_SLUG = "artifact-coding-agent"
ARTIFACT_CODING_AGENT_PROFILE_NAME = "Artifact Coding Agent"
DEFAULT_ARTIFACT_CODING_MODEL_ID = "openai/gpt-5"


def resolve_artifact_coding_profile_model_id() -> str:
    raw = str(os.getenv("ARTIFACT_CODING_AGENT_MODEL_ID") or DEFAULT_ARTIFACT_CODING_MODEL_ID).strip()
    return raw or DEFAULT_ARTIFACT_CODING_MODEL_ID


def _resolve_existing_graph_model_id(graph_definition: dict | None) -> str | None:
    if not isinstance(graph_definition, dict):
        return None
    nodes = graph_definition.get("nodes")
    if not isinstance(nodes, list):
        return None
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if str(node.get("id") or "").strip() != "artifact_coding_agent":
            continue
        config = node.get("config")
        if not isinstance(config, dict):
            return None
        model_id = str(config.get("model_id") or "").strip()
        if model_id:
            return model_id
    return None


def _build_artifact_coding_graph(model_id: str, tool_ids: list[str]) -> dict:
    max_tool_iterations = int(os.getenv("ARTIFACT_CODING_AGENT_MAX_TOOL_ITERATIONS", "24") or 24)
    max_tool_iterations = max(1, max_tool_iterations)
    tool_timeout_s = int(os.getenv("ARTIFACT_CODING_AGENT_TOOL_TIMEOUT_SECONDS", "90") or 90)
    tool_timeout_s = max(15, tool_timeout_s)
    instructions = (
        "You are the canonical artifact coding agent for artifact authoring across the artifact page, the playground, and delegated architect worker sessions. "
        "The artifact draft in tool context is the source of truth. "
        "Use tools to inspect and modify the artifact draft, including metadata, contracts, runtime settings, and source files. "
        "Keep edits minimal and coherent. "
        "Use file read/search tools before editing when the request depends on existing code. "
        "When changing source files, prefer targeted range updates over full replacement unless a full rewrite is cleaner. "
        "Only claim changes are complete if a mutation tool succeeded. "
        "When validation is needed, call artifact_coding_run_test once, then use artifact_coding_await_last_test_result for the terminal outcome. "
        "Use artifact_coding_get_last_test_result only for one-off inspection/debugging, not as a polling loop. "
        "If a test run is queued or running, that is normal for Cloudflare Workers cold start and queue delay; wait for it instead of starting another test run. "
        "Rely on returned test results instead of inventing outcomes. "
        "The runtime target is Cloudflare Workers-compatible Python, so do not assume local processes, local filesystem state, or arbitrary sockets. "
        "If context says artifact_coding_scope_mode=standalone, you may search existing artifacts, open an existing artifact into the current session, or start a new draft in the current session based on the user's request. "
        "If the request sounds like editing existing work, search/list artifacts first and ask only if multiple plausible matches remain. "
        "If context says artifact_coding_scope_mode=locked, do not attempt to switch to another artifact or reset the session scope. "
        "Use artifact_coding_persist_artifact only when the task explicitly requires create/save/update persistence. "
        "Never claim that persistence_readiness or platform_assets payloads were manually edited by you; those are runtime-derived state. "
        "Always answer in natural language after tool use. "
        "If context includes architect_worker_task, you are acting as a delegated worker for the platform architect rather than a user-facing chat editor. "
        "In delegated mode, complete the requested objective autonomously from the current shared draft and do not ask the end user for routine clarifications. "
        "Use reasonable defaults consistent with the task, mutate the draft directly when the path is clear, and return a concise completion summary for the architect. "
        "Ask a question only when you are genuinely blocked on missing information that cannot be safely inferred from the task, draft, or tool results. "
        "When genuinely blocked in delegated mode, your final response must begin with exactly 'BLOCKING QUESTION:' followed by one concise question, then stop."
    )
    return {
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {
                "id": "artifact_coding_agent",
                "type": "agent",
                "position": {"x": 260, "y": 0},
                "config": {
                    "name": "Artifact Coding Agent",
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
            {"id": "end", "type": "end", "position": {"x": 520, "y": 0}, "config": {"output_variable": "last_agent_output"}},
        ],
        "edges": [
            {"id": "e-start-agent", "source": "start", "target": "artifact_coding_agent", "type": "control"},
            {"id": "e-agent-end", "source": "artifact_coding_agent", "target": "end", "type": "control"},
        ],
    }


async def ensure_artifact_coding_agent_profile(
    db: AsyncSession,
    tenant_id,
    *,
    actor_user_id=None,
) -> Agent:
    import app.services.artifact_coding_agent_tools  # noqa: F401

    tool_ids = await ensure_artifact_coding_tools(db)
    result = await db.execute(
        select(Agent).where(
            Agent.slug == ARTIFACT_CODING_AGENT_PROFILE_SLUG,
            Agent.tenant_id == tenant_id,
        )
    )
    agent = result.scalar_one_or_none()
    model_id = (
        _resolve_existing_graph_model_id(agent.graph_definition if agent is not None else None)
        or resolve_artifact_coding_profile_model_id()
    )
    graph_definition = _build_artifact_coding_graph(model_id, tool_ids)
    description = (
        "Public platform artifact coding agent for live artifact draft editing from the artifact admin surface."
    )
    if agent is None:
        agent = Agent(
            tenant_id=tenant_id,
            name=ARTIFACT_CODING_AGENT_PROFILE_NAME,
            slug=ARTIFACT_CODING_AGENT_PROFILE_SLUG,
            description=description,
            graph_definition=graph_definition,
            tools=tool_ids,
            referenced_tool_ids=tool_ids,
            status=AgentStatus.published,
            is_active=True,
            is_public=True,
        )
        db.add(agent)
        await db.flush()
    else:
        agent.name = ARTIFACT_CODING_AGENT_PROFILE_NAME
        agent.slug = ARTIFACT_CODING_AGENT_PROFILE_SLUG
        agent.description = description
        agent.graph_definition = graph_definition
        agent.tools = tool_ids
        agent.referenced_tool_ids = tool_ids
        agent.status = AgentStatus.published
        agent.is_active = True
        agent.is_public = True
        await db.flush()

    await WorkloadProvisioningService(db).provision_agent_policy(
        agent=agent,
        actor_user_id=actor_user_id,
    )
    return agent
