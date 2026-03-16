from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.engine import sessionmaker as get_session
from app.db.postgres.models.agents import Agent
from app.db.postgres.models.orchestration import OrchestratorPolicy, OrchestratorTargetAllowlist
from app.db.postgres.models.registry import ToolDefinitionScope, ToolImplementationType, ToolRegistry, ToolStatus
from app.services.artifact_coding_agent_profile import (
    ARTIFACT_CODING_AGENT_PROFILE_SLUG,
    ensure_artifact_coding_agent_profile,
)
from app.db.postgres.models.artifact_runtime import ArtifactKind
from app.services.platform_architect_worker_runtime_service import PlatformArchitectWorkerRuntimeService
from app.services.tool_function_registry import register_tool_function


ARCHITECT_WORKER_NAMESPACE = "platform-architect-workers"


def _tool_schema(
    *,
    properties: dict[str, Any],
    required: list[str] | None = None,
    one_of: list[dict[str, Any]] | None = None,
    any_of: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "input": {
            "type": "object",
            "properties": properties,
            "required": list(required or []),
            "additionalProperties": False,
            **({"oneOf": one_of} if one_of else {}),
            **({"anyOf": any_of} if any_of else {}),
        },
        "output": {"type": "object", "additionalProperties": True},
    }


def _binding_ref_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "binding_type": {"type": "string", "enum": ["artifact_shared_draft"]},
            "binding_id": {"type": "string"},
        },
        "required": ["binding_type", "binding_id"],
        "additionalProperties": False,
    }


def _artifact_snapshot_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": [item.value for item in ArtifactKind]},
            "display_name": {"type": "string"},
            "description": {"type": "string"},
            "source_files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            },
            "entry_module_path": {"type": "string"},
            "python_dependencies": {"type": "string"},
            "runtime_target": {"type": "string"},
            "capabilities": {"type": "object"},
            "config_schema": {"type": "object"},
            "agent_contract": {"type": "object"},
            "rag_contract": {"type": "object"},
            "tool_contract": {"type": "object"},
        },
        "required": ["kind", "display_name", "source_files", "entry_module_path"],
        "additionalProperties": False,
    }


def _artifact_draft_seed_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": [item.value for item in ArtifactKind]},
            "display_name": {"type": "string"},
            "description": {"type": "string"},
            "entry_module_path": {"type": "string"},
            "runtime_target": {"type": "string"},
        },
        "required": ["kind"],
        "additionalProperties": False,
    }


def _spawn_target_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "worker_agent_slug": {"type": "string"},
            "binding_ref": _binding_ref_schema(),
            "objective": {"type": "string"},
            "context": {"type": "object", "additionalProperties": True},
            "constraints": {"type": "array", "items": {"type": "string"}},
            "success_criteria": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["objective"],
        "additionalProperties": False,
        "anyOf": [
            {"required": ["worker_agent_slug", "objective"]},
            {"required": ["binding_ref", "objective"]},
        ],
    }


@register_tool_function("architect_worker_binding_prepare")
async def architect_worker_binding_prepare(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        result = await PlatformArchitectWorkerRuntimeService(db).prepare_binding(tool_payload)
        await db.commit()
        return result


@register_tool_function("architect_worker_binding_get_state")
async def architect_worker_binding_get_state(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        return await PlatformArchitectWorkerRuntimeService(db).get_binding_state(tool_payload)


@register_tool_function("architect_worker_binding_persist_artifact")
async def architect_worker_binding_persist_artifact(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        result = await PlatformArchitectWorkerRuntimeService(db).persist_binding_artifact(tool_payload)
        await db.commit()
        return result


@register_tool_function("architect_worker_spawn")
async def architect_worker_spawn(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        result = await PlatformArchitectWorkerRuntimeService(db).spawn_worker(tool_payload)
        await db.commit()
        return result


@register_tool_function("architect_worker_spawn_group")
async def architect_worker_spawn_group(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        result = await PlatformArchitectWorkerRuntimeService(db).spawn_group(tool_payload)
        await db.commit()
        return result


@register_tool_function("architect_worker_get_run")
async def architect_worker_get_run(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        return await PlatformArchitectWorkerRuntimeService(db).get_run(tool_payload)


@register_tool_function("architect_worker_await")
async def architect_worker_await(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        return await PlatformArchitectWorkerRuntimeService(db).await_run(tool_payload)


@register_tool_function("architect_worker_respond")
async def architect_worker_respond(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        result = await PlatformArchitectWorkerRuntimeService(db).respond_to_run(tool_payload)
        await db.commit()
        return result


@register_tool_function("architect_worker_join")
async def architect_worker_join(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        return await PlatformArchitectWorkerRuntimeService(db).join_group(tool_payload)


@register_tool_function("architect_worker_cancel")
async def architect_worker_cancel(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        result = await PlatformArchitectWorkerRuntimeService(db).cancel(tool_payload)
        await db.commit()
        return result


ARCHITECT_WORKER_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "slug": "architect-worker-binding-prepare",
        "name": "Architect Worker Binding Prepare",
        "description": "Prepare or reuse a binding-backed worker state for the architect. Normal artifact creation uses prepare_mode=create_new_draft with title_prompt plus draft_seed.kind; full draft_snapshot is reserved for seed_snapshot only.",
        "implementation_type": ToolImplementationType.FUNCTION,
        "schema": _tool_schema(
            properties={
                "binding_type": {"type": "string", "enum": ["artifact_shared_draft"]},
                "prepare_mode": {
                    "type": "string",
                    "enum": ["reuse_existing", "attach_existing_artifact", "create_new_draft", "seed_snapshot"],
                },
                "binding_id": {"type": "string"},
                "artifact_id": {"type": "string"},
                "draft_key": {"type": "string"},
                "title_prompt": {"type": "string"},
                "draft_seed": _artifact_draft_seed_schema(),
                "draft_snapshot": _artifact_snapshot_schema(),
                "replace_snapshot": {"type": "boolean"},
            },
            required=["binding_type", "prepare_mode"],
            one_of=[
                {
                    "properties": {"prepare_mode": {"const": "reuse_existing"}},
                    "required": ["binding_type", "prepare_mode", "binding_id"],
                },
                {
                    "properties": {"prepare_mode": {"const": "attach_existing_artifact"}},
                    "required": ["binding_type", "prepare_mode", "artifact_id"],
                },
                {
                    "properties": {"prepare_mode": {"const": "create_new_draft"}},
                    "required": ["binding_type", "prepare_mode", "title_prompt", "draft_seed"],
                    "not": {"required": ["draft_snapshot"]},
                },
                {
                    "properties": {"prepare_mode": {"const": "seed_snapshot"}},
                    "required": ["binding_type", "prepare_mode", "title_prompt", "draft_snapshot"],
                    "not": {"required": ["draft_seed"]},
                },
            ],
        ),
        "config_schema": {
            "implementation": {"type": "function", "function_name": "architect_worker_binding_prepare"},
            "execution": {
                "timeout_s": 30,
                "is_pure": False,
                "concurrency_group": ARCHITECT_WORKER_NAMESPACE,
                "max_concurrency": 8,
                "strict_input_schema": True,
            },
        },
    },
    {
        "slug": "architect-worker-binding-get-state",
        "name": "Architect Worker Binding Get State",
        "description": "Fetch the latest binding-backed worker state and canonical export payload.",
        "implementation_type": ToolImplementationType.FUNCTION,
        "schema": _tool_schema(
            properties={
                "binding_ref": _binding_ref_schema(),
                "run_id": {"type": "string"},
            },
            required=["binding_ref"],
        ),
        "config_schema": {
            "implementation": {"type": "function", "function_name": "architect_worker_binding_get_state"},
            "execution": {
                "timeout_s": 30,
                "is_pure": True,
                "concurrency_group": ARCHITECT_WORKER_NAMESPACE,
                "max_concurrency": 8,
                "strict_input_schema": True,
            },
        },
    },
    {
        "slug": "architect-worker-binding-persist-artifact",
        "name": "Architect Worker Binding Persist Artifact",
        "description": "Persist a binding-backed artifact draft server-side without routing persistence payloads through the model layer.",
        "implementation_type": ToolImplementationType.FUNCTION,
        "schema": _tool_schema(
            properties={
                "binding_ref": _binding_ref_schema(),
                "mode": {"type": "string", "enum": ["auto", "create", "update"]},
            },
            required=["binding_ref"],
        ),
        "config_schema": {
            "implementation": {"type": "function", "function_name": "architect_worker_binding_persist_artifact"},
            "execution": {
                "timeout_s": 30,
                "is_pure": False,
                "concurrency_group": ARCHITECT_WORKER_NAMESPACE,
                "max_concurrency": 8,
                "strict_input_schema": True,
            },
        },
    },
    {
        "slug": "architect-worker-spawn",
        "name": "Architect Worker Spawn",
        "description": "Spawn one async worker run for the architect.",
        "implementation_type": ToolImplementationType.FUNCTION,
        "schema": _tool_schema(
            properties={
                "worker_agent_slug": {"type": "string"},
                "binding_ref": _binding_ref_schema(),
                "objective": {"type": "string"},
                "context": {"type": "object", "additionalProperties": True},
                "constraints": {"type": "array", "items": {"type": "string"}},
                "success_criteria": {"type": "array", "items": {"type": "string"}},
                "scope_subset": {"type": "array", "items": {"type": "string"}},
                "idempotency_key": {"type": "string"},
                "failure_policy": {"type": "string"},
                "timeout_s": {"type": "integer"},
            },
            required=["objective"],
            any_of=[
                {"required": ["worker_agent_slug", "objective"]},
                {"required": ["binding_ref", "objective"]},
            ],
        ),
        "config_schema": {
            "implementation": {"type": "function", "function_name": "architect_worker_spawn"},
            "execution": {
                "timeout_s": 30,
                "is_pure": False,
                "concurrency_group": ARCHITECT_WORKER_NAMESPACE,
                "max_concurrency": 8,
                "strict_input_schema": True,
            },
        },
    },
    {
        "slug": "architect-worker-spawn-group",
        "name": "Architect Worker Spawn Group",
        "description": "Spawn an async parallel worker group for the architect.",
        "implementation_type": ToolImplementationType.FUNCTION,
        "schema": _tool_schema(
            properties={
                "targets": {"type": "array", "items": _spawn_target_schema()},
                "scope_subset": {"type": "array", "items": {"type": "string"}},
                "idempotency_key_prefix": {"type": "string"},
                "failure_policy": {"type": "string"},
                "join_mode": {"type": "string"},
                "quorum_threshold": {"type": "integer"},
                "timeout_s": {"type": "integer"},
            },
            required=["targets"],
        ),
        "config_schema": {
            "implementation": {"type": "function", "function_name": "architect_worker_spawn_group"},
            "execution": {
                "timeout_s": 30,
                "is_pure": False,
                "concurrency_group": ARCHITECT_WORKER_NAMESPACE,
                "max_concurrency": 8,
                "strict_input_schema": True,
            },
        },
    },
    {
        "slug": "architect-worker-get-run",
        "name": "Architect Worker Get Run",
        "description": "Inspect one architect worker run snapshot. Prefer architect-worker-await for normal waiting behavior.",
        "implementation_type": ToolImplementationType.FUNCTION,
        "schema": _tool_schema(properties={"run_id": {"type": "string"}}, required=["run_id"]),
        "config_schema": {
            "implementation": {"type": "function", "function_name": "architect_worker_get_run"},
            "execution": {
                "timeout_s": 30,
                "is_pure": True,
                "concurrency_group": ARCHITECT_WORKER_NAMESPACE,
                "max_concurrency": 8,
                "strict_input_schema": True,
            },
        },
    },
    {
        "slug": "architect-worker-await",
        "name": "Architect Worker Await",
        "description": "Wait server-side for a child worker to complete, fail, cancel, or block on input instead of repeatedly polling get-run.",
        "implementation_type": ToolImplementationType.FUNCTION,
        "schema": _tool_schema(
            properties={
                "run_id": {"type": "string"},
                "timeout_s": {"type": "number"},
                "poll_interval_s": {"type": "number"},
            },
            required=["run_id"],
        ),
        "config_schema": {
            "implementation": {"type": "function", "function_name": "architect_worker_await"},
            "execution": {
                "timeout_s": 90,
                "is_pure": True,
                "concurrency_group": ARCHITECT_WORKER_NAMESPACE,
                "max_concurrency": 8,
                "strict_input_schema": True,
            },
        },
    },
    {
        "slug": "architect-worker-respond",
        "name": "Architect Worker Respond",
        "description": "Provide an orchestrator response when a worker is waiting for input, resuming or continuing the delegated run.",
        "implementation_type": ToolImplementationType.FUNCTION,
        "schema": _tool_schema(
            properties={
                "run_id": {"type": "string"},
                "response": {"type": "string"},
            },
            required=["run_id", "response"],
        ),
        "config_schema": {
            "implementation": {"type": "function", "function_name": "architect_worker_respond"},
            "execution": {
                "timeout_s": 30,
                "is_pure": False,
                "concurrency_group": ARCHITECT_WORKER_NAMESPACE,
                "max_concurrency": 8,
                "strict_input_schema": True,
            },
        },
    },
    {
        "slug": "architect-worker-join",
        "name": "Architect Worker Join",
        "description": "Join an architect worker group.",
        "implementation_type": ToolImplementationType.FUNCTION,
        "schema": _tool_schema(
            properties={
                "orchestration_group_id": {"type": "string"},
                "mode": {"type": "string"},
                "quorum_threshold": {"type": "integer"},
                "timeout_s": {"type": "integer"},
            },
            required=["orchestration_group_id"],
        ),
        "config_schema": {
            "implementation": {"type": "function", "function_name": "architect_worker_join"},
            "execution": {
                "timeout_s": 30,
                "is_pure": True,
                "concurrency_group": ARCHITECT_WORKER_NAMESPACE,
                "max_concurrency": 8,
                "strict_input_schema": True,
            },
        },
    },
    {
        "slug": "architect-worker-cancel",
        "name": "Architect Worker Cancel",
        "description": "Cancel an architect worker subtree.",
        "implementation_type": ToolImplementationType.FUNCTION,
        "schema": _tool_schema(
            properties={
                "run_id": {"type": "string"},
                "include_root": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            required=["run_id"],
        ),
        "config_schema": {
            "implementation": {"type": "function", "function_name": "architect_worker_cancel"},
            "execution": {
                "timeout_s": 30,
                "is_pure": False,
                "concurrency_group": ARCHITECT_WORKER_NAMESPACE,
                "max_concurrency": 8,
                "strict_input_schema": True,
            },
        },
    },
]


async def ensure_platform_architect_worker_tools(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_user_id: UUID | None = None,
) -> list[str]:
    import app.services.platform_architect_worker_tools  # noqa: F401

    await ensure_artifact_coding_agent_profile(db, tenant_id, actor_user_id=actor_user_id)

    try:
        result = await db.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'tool_registry'
                  AND column_name IN ('artifact_id', 'artifact_version', 'artifact_revision_id')
                """
            )
        )
        cols = {row[0] for row in result.all()}
    except Exception:
        result = await db.execute(text("PRAGMA table_info(tool_registry)"))
        cols = {row[1] for row in result.all()}
    if not {"artifact_id", "artifact_version", "artifact_revision_id"}.issubset(cols):
        raise RuntimeError("platform architect worker tools require the current tool_registry schema")

    tool_ids: list[str] = []
    for spec in ARCHITECT_WORKER_TOOL_SPECS:
        result = await db.execute(
            select(ToolRegistry).where(
                and_(
                    ToolRegistry.tenant_id.is_(None),
                    ToolRegistry.slug == spec["slug"],
                )
            )
        )
        tool = result.scalar_one_or_none()
        if tool is None:
            tool = ToolRegistry(
                tenant_id=None,
                name=spec["name"],
                slug=spec["slug"],
                description=spec["description"],
                scope=ToolDefinitionScope.GLOBAL,
                schema=spec["schema"],
                config_schema=spec["config_schema"],
                status=ToolStatus.PUBLISHED,
                version="1.0.0",
                implementation_type=spec["implementation_type"],
                artifact_id=None,
                artifact_version=None,
                artifact_revision_id=None,
                builtin_key=None,
                builtin_template_id=None,
                is_builtin_template=False,
                is_active=True,
                is_system=True,
                published_at=datetime.now(timezone.utc),
            )
            db.add(tool)
            await db.flush()
        else:
            tool.name = spec["name"]
            tool.description = spec["description"]
            tool.scope = ToolDefinitionScope.GLOBAL
            tool.schema = spec["schema"]
            tool.config_schema = spec["config_schema"]
            tool.status = ToolStatus.PUBLISHED
            tool.version = "1.0.0"
            tool.implementation_type = spec["implementation_type"]
            tool.artifact_id = None
            tool.artifact_version = None
            tool.artifact_revision_id = None
            tool.is_active = True
            tool.is_system = True
            tool.published_at = tool.published_at or datetime.now(timezone.utc)
        tool_ids.append(str(tool.id))
    await db.flush()
    return tool_ids


async def ensure_platform_architect_worker_orchestration_policy(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    orchestrator_agent_id: UUID,
) -> None:
    artifact_agent = await ensure_artifact_coding_agent_profile(db, tenant_id, actor_user_id=None)
    result = await db.execute(
        select(OrchestratorPolicy).where(
            and_(
                OrchestratorPolicy.tenant_id == tenant_id,
                OrchestratorPolicy.orchestrator_agent_id == orchestrator_agent_id,
            )
        )
    )
    policy = result.scalar_one_or_none()
    if policy is None:
        policy = OrchestratorPolicy(
            tenant_id=tenant_id,
            orchestrator_agent_id=orchestrator_agent_id,
            allowed_scope_subset=["agents.execute"],
            is_active=True,
        )
        db.add(policy)
    else:
        policy.is_active = True
        policy.allowed_scope_subset = ["agents.execute"]

    agent_result = await db.execute(
        select(Agent).where(
            and_(
                Agent.tenant_id == tenant_id,
                Agent.slug == ARTIFACT_CODING_AGENT_PROFILE_SLUG,
            )
        )
    )
    artifact_agent_row = agent_result.scalar_one_or_none()
    target_agent_id = artifact_agent_row.id if artifact_agent_row is not None else artifact_agent.id
    allow_result = await db.execute(
        select(OrchestratorTargetAllowlist).where(
            and_(
                OrchestratorTargetAllowlist.tenant_id == tenant_id,
                OrchestratorTargetAllowlist.orchestrator_agent_id == orchestrator_agent_id,
                OrchestratorTargetAllowlist.target_agent_id == target_agent_id,
            )
        )
    )
    allow = allow_result.scalar_one_or_none()
    if allow is None:
        allow = OrchestratorTargetAllowlist(
            tenant_id=tenant_id,
            orchestrator_agent_id=orchestrator_agent_id,
            target_agent_id=target_agent_id,
            target_agent_slug=ARTIFACT_CODING_AGENT_PROFILE_SLUG,
            is_active=True,
        )
        db.add(allow)
    else:
        allow.target_agent_slug = ARTIFACT_CODING_AGENT_PROFILE_SLUG
        allow.is_active = True
    await db.flush()
