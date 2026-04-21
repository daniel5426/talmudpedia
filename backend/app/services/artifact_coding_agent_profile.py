from __future__ import annotations

import hashlib
import os
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import Agent, AgentStatus
from app.db.postgres.models.registry import ModelCapabilityType, ModelRegistry
from app.services.artifact_coding_agent_tools import ARTIFACT_CODING_AGENT_SURFACE, ensure_artifact_coding_tools

ARTIFACT_CODING_AGENT_PROFILE_SYSTEM_KEY = "artifact_coding_agent"
ARTIFACT_CODING_AGENT_PROFILE_NAME = "Artifact Coding Agent"
DEFAULT_ARTIFACT_CODING_MODEL_SYSTEM_KEY = "gpt-5-mini"


def _system_agent_row_key(system_key: str) -> str:
    digest = hashlib.sha1(system_key.encode("utf-8")).hexdigest()[:24]
    return f"sys-agent-{digest}"


async def resolve_artifact_coding_profile_model_id(db: AsyncSession, organization_id) -> str:
    preferred_ref = str(
        os.getenv("ARTIFACT_CODING_AGENT_MODEL_SYSTEM_KEY")
        or os.getenv("ARTIFACT_CODING_AGENT_MODEL_ID")
        or DEFAULT_ARTIFACT_CODING_MODEL_SYSTEM_KEY
    ).strip()
    scope_filter = or_(ModelRegistry.organization_id == organization_id, ModelRegistry.organization_id == None)

    if preferred_ref:
        preferred_query = (
            select(ModelRegistry)
            .where(
                ModelRegistry.capability_type == ModelCapabilityType.CHAT,
                ModelRegistry.is_active == True,
                scope_filter,
            )
            .order_by(ModelRegistry.organization_id.is_not(None).desc(), ModelRegistry.updated_at.desc())
        )
        try:
            preferred_id = UUID(preferred_ref)
        except Exception:
            preferred_id = None
        if preferred_id is not None:
            preferred_query = preferred_query.where(ModelRegistry.id == preferred_id)
        else:
            preferred_query = preferred_query.where(ModelRegistry.system_key == preferred_ref)
        preferred = (await db.execute(preferred_query)).scalars().first()
        if preferred is not None:
            return str(preferred.id)

    default_query = (
        select(ModelRegistry)
        .where(
            ModelRegistry.capability_type == ModelCapabilityType.CHAT,
            ModelRegistry.is_active == True,
            scope_filter,
        )
        .order_by(
            ModelRegistry.organization_id.is_not(None).desc(),
            ModelRegistry.is_default.desc(),
            ModelRegistry.updated_at.desc(),
        )
    )
    model = (await db.execute(default_query)).scalars().first()
    if model is None:
        raise ValueError("No active chat model available for artifact coding agent profile")
    return str(model.id)


def _build_artifact_coding_graph(model_id: str, tool_ids: list[str]) -> dict:
    max_tool_iterations = int(os.getenv("ARTIFACT_CODING_AGENT_MAX_TOOL_ITERATIONS", "24") or 24)
    max_tool_iterations = max(1, max_tool_iterations)
    tool_timeout_s = int(os.getenv("ARTIFACT_CODING_AGENT_TOOL_TIMEOUT_SECONDS", "90") or 90)
    tool_timeout_s = max(15, tool_timeout_s)
    instructions = (
        "You are the canonical artifact coding agent for artifact authoring across the artifact page and delegated architect worker sessions. "
        "The artifact draft in tool context is the source of truth. "
        "Use tools to inspect and modify the artifact draft, including metadata, contracts, runtime settings, and source files. "
        "Keep edits minimal and coherent. "
        "A runnable artifact is invalid unless the current entry module exposes execute(inputs, config, context). "
        "Use file read/search tools before editing when the request depends on existing code. "
        "Before mutating part of a file, use artifact_coding_read_file with include_line_numbers=true or artifact_coding_search_in_files with context_before/context_after to capture the exact current text. "
        "For bounded code edits, prefer artifact_coding_replace_text_in_file with exact old_text/new_text replacement. "
        "Use artifact_coding_replace_file only when the change is broad or the exact old text cannot be isolated cleanly. "
        "Do not remove, rename, or break the execute handler unless you replace it in the same edit sequence. "
        "Only claim changes are complete if a mutation tool succeeded. "
        "Use artifact_coding_set_metadata for display_name and description only. "
        "Use the kind-specific contract mutation tools for contracts: artifact_coding_set_agent_contract, artifact_coding_set_rag_contract, and artifact_coding_set_tool_contract. "
        "When setting a contract, pass only the raw inner contract object. "
        "Do not wrap it inside agent_contract, rag_contract, or tool_contract keys. "
        "Do not place metadata fields like display_name or description inside contract objects. "
        "When validation is needed, call artifact_coding_run_test once, then use artifact_coding_await_last_test_result for the terminal outcome. "
        "Use artifact_coding_get_last_test_result only for one-off inspection/debugging, not as a polling loop. "
        "If a test run is queued or running, that is normal for Cloudflare Workers cold start and queue delay; wait for it instead of starting another test run. "
        "Rely on returned test results instead of inventing outcomes. "
        "Artifacts run on Cloudflare Workers-compatible runtime paths, so do not assume local processes, local filesystem state, or arbitrary sockets. "
        "Artifacts may use either python or javascript language lanes. "
        "Honor the draft language when writing code and dependencies. "
        "Language is selected during create flow and must not be changed after the artifact has been persisted. "
        "The openai Python SDK is out of contract for organization artifacts; prefer direct HTTP or lighter compatible libraries when needed. "
        "Use artifact_coding_list_credentials when you need to reference an existing credential. "
        "Credential references must use exact string literals of the form @{credential-id}. "
        "Do not invent credential ids. "
        "Do not use mixed or embedded forms such as Bearer @{id}, concatenated strings, template strings, comments, or artifact_runtime_sdk imports. "
        "You are always working on the current bound draft only. "
        "Do not attempt to switch to another artifact, start a different draft, or persist artifacts yourself. "
        "If the current locked session is already bound to an existing persisted artifact and the request implies a new artifact or a different language than the current artifact language, do not mutate the draft. "
        "Respond briefly in natural language that the request is outside the current artifact scope and cannot be completed from this chat, then stop. "
        "Do not tell the caller to open another session, create another artifact, or continue elsewhere unless they explicitly ask what to do next. "
        "Do not emit scaffolds, suggested source files, or workflow steps by default when refusing for scope conflict. "
        "Always answer in natural language after tool use. "
        "If context includes architect_worker_task, you are acting as a delegated worker for the platform architect rather than a user-facing chat editor. "
        "In delegated mode, complete the requested objective autonomously from the current shared draft and do not ask the end user for routine clarifications. "
        "Use reasonable defaults consistent with the task, mutate the draft directly when the path is clear, and return a concise completion summary for the architect. "
        "When the delegated task is to create or prepare a new artifact, make the draft persistence-ready before you claim completion. "
        "That means filling the required artifact fields in the bound draft itself: display_name, kind, language, source_files, entry_module_path, runtime_target, capabilities, config_schema, and exactly one kind-matching contract object via the matching contract tool (agent_contract for agent_node, rag_contract for rag_operator, tool_contract for tool_impl). "
        "Ensure entry_module_path points to a real file in source_files, keep runtime_target aligned with the code you wrote, and set dependencies when imports require them. "
        "If the task asks for additional metadata like description, set it in the draft too. "
        "For tool-backed artifacts, use kind=tool_impl and put the executable handler plus tool contract on the artifact draft itself. "
        "Tool identity, binding, and publish pinning are separate follow-up lifecycle steps outside this draft-editing runtime. "
        "Do not leave creation-critical draft fields implicit when the task is to create a runnable artifact for the architect. "
        "Before claiming completion for a runnable artifact task, call artifact_coding_validate_runtime_contract and ensure it returns ok=true. "
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
    organization_id,
    *,
    actor_user_id=None,
) -> Agent:
    import app.services.artifact_coding_agent_tools  # noqa: F401

    tool_ids = await ensure_artifact_coding_tools(db)
    result = await db.execute(
        select(Agent).where(
            Agent.system_key == ARTIFACT_CODING_AGENT_PROFILE_SYSTEM_KEY,
            Agent.organization_id == organization_id,
        )
    )
    agent = result.scalar_one_or_none()
    model_id = await resolve_artifact_coding_profile_model_id(db, organization_id)
    graph_definition = _build_artifact_coding_graph(model_id, tool_ids)
    description = (
        "Public platform artifact coding agent for live artifact draft editing from the artifact admin surface."
    )
    if agent is None:
        agent = Agent(
            organization_id=organization_id,
            name=ARTIFACT_CODING_AGENT_PROFILE_NAME,
            system_key=ARTIFACT_CODING_AGENT_PROFILE_SYSTEM_KEY,
            slug=_system_agent_row_key(ARTIFACT_CODING_AGENT_PROFILE_SYSTEM_KEY),
            description=description,
            graph_definition=graph_definition,
            tools=tool_ids,
            referenced_tool_ids=tool_ids,
            status=AgentStatus.published,
            is_active=True,
            is_public=True,
            show_in_playground=False,
        )
        db.add(agent)
        await db.flush()
    else:
        agent.name = ARTIFACT_CODING_AGENT_PROFILE_NAME
        agent.system_key = ARTIFACT_CODING_AGENT_PROFILE_SYSTEM_KEY
        agent.slug = _system_agent_row_key(ARTIFACT_CODING_AGENT_PROFILE_SYSTEM_KEY)
        agent.description = description
        agent.graph_definition = graph_definition
        agent.tools = tool_ids
        agent.referenced_tool_ids = tool_ids
        agent.status = AgentStatus.published
        agent.is_active = True
        agent.is_public = True
        agent.show_in_playground = False
        await db.flush()

    return agent
