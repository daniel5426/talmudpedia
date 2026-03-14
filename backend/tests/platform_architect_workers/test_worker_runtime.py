from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.execution.tool_input_contracts import validate_tool_input_schema
from app.db.postgres.models.agents import AgentRun, AgentStatus, RunStatus
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.registry import ToolImplementationType, ToolRegistry
from app.services.platform_architect_contracts import build_architect_graph_definition
from app.services.platform_architect_worker_tools import architect_worker_spawn
from app.services.platform_architect_worker_runtime_service import PlatformArchitectWorkerRuntimeService
from app.services.platform_architect_worker_tools import (
    architect_worker_binding_prepare,
    ensure_platform_architect_worker_tools,
)


async def _seed_tenant_and_user(db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"Architect Worker Tenant {suffix}", slug=f"architect-worker-tenant-{suffix}")
    user = User(email=f"architect-worker-{suffix}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(user)
    return tenant, user


async def _get_tool_by_slug(db_session, slug: str) -> ToolRegistry:
    result = await db_session.execute(select(ToolRegistry).where(ToolRegistry.slug == slug))
    return result.scalar_one()


@pytest.mark.asyncio
async def test_architect_worker_tools_seed_expected_slugs(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    tool_ids = await ensure_platform_architect_worker_tools(
        db_session,
        tenant_id=tenant.id,
        actor_user_id=user.id,
    )
    await db_session.commit()

    tools = (
        await db_session.execute(select(ToolRegistry).where(ToolRegistry.id.in_(tool_ids)))
    ).scalars().all()
    by_slug = {tool.slug: tool for tool in tools}

    assert set(by_slug.keys()) == {
        "architect-worker-binding-prepare",
        "architect-worker-binding-get-state",
        "architect-worker-spawn",
        "architect-worker-spawn-group",
        "architect-worker-get-run",
        "architect-worker-join",
        "architect-worker-cancel",
    }
    assert by_slug["architect-worker-spawn"].implementation_type == ToolImplementationType.FUNCTION
    assert by_slug["architect-worker-spawn"].config_schema["implementation"]["function_name"] == "architect_worker_spawn"
    assert by_slug["architect-worker-spawn"].config_schema["execution"]["strict_input_schema"] is True
    assert by_slug["architect-worker-binding-prepare"].config_schema["execution"]["strict_input_schema"] is True

    spawn_schema = by_slug["architect-worker-spawn"].schema["input"]
    assert "task" not in spawn_schema["properties"]
    assert "objective" in spawn_schema["properties"]
    assert spawn_schema["properties"]["binding_ref"]["required"] == ["binding_type", "binding_id"]
    assert "oneOf" not in spawn_schema
    assert spawn_schema["anyOf"] == [
        {"required": ["worker_agent_slug", "objective"]},
        {"required": ["binding_ref", "objective"]},
    ]

    binding_prepare_schema = by_slug["architect-worker-binding-prepare"].schema["input"]
    assert "binding_payload" not in binding_prepare_schema["properties"]
    assert binding_prepare_schema["properties"]["prepare_mode"]["enum"] == [
        "reuse_existing",
        "attach_existing_artifact",
        "create_new_draft",
        "seed_snapshot",
    ]
    assert binding_prepare_schema["properties"]["draft_seed"]["required"] == ["kind"]
    create_branch = next(
        variant
        for variant in binding_prepare_schema["oneOf"]
        if variant["properties"]["prepare_mode"]["const"] == "create_new_draft"
    )
    assert create_branch["required"] == ["binding_type", "prepare_mode", "title_prompt", "draft_seed"]
    assert create_branch["not"] == {"required": ["draft_snapshot"]}


@pytest.mark.asyncio
async def test_binding_prepare_schema_accepts_lightweight_seed_and_rejects_old_snapshot_guesses(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    await ensure_platform_architect_worker_tools(
        db_session,
        tenant_id=tenant.id,
        actor_user_id=user.id,
    )
    await db_session.commit()
    tool = await _get_tool_by_slug(db_session, "architect-worker-binding-prepare")

    assert validate_tool_input_schema(
        tool,
        {
            "binding_type": "artifact_shared_draft",
            "prepare_mode": "create_new_draft",
            "title_prompt": "Create a tool artifact draft",
            "draft_seed": {"kind": "tool_impl"},
        },
    ) == []

    missing_kind_errors = validate_tool_input_schema(
        tool,
        {
            "binding_type": "artifact_shared_draft",
            "prepare_mode": "create_new_draft",
            "title_prompt": "Create a tool artifact draft",
            "draft_seed": {},
        },
    )
    assert any("kind" in item["message"] for item in missing_kind_errors)

    files_guess_errors = validate_tool_input_schema(
        tool,
        {
            "binding_type": "artifact_shared_draft",
            "prepare_mode": "create_new_draft",
            "draft_snapshot": {"files": {}},
        },
    )
    assert any("not valid under any of the given schemas" in item["message"] for item in files_guess_errors)

    entrypoint_errors = validate_tool_input_schema(
        tool,
        {
            "binding_type": "artifact_shared_draft",
            "prepare_mode": "seed_snapshot",
            "title_prompt": "Seed a snapshot",
            "draft_snapshot": {
                "kind": "tool_impl",
                "slug": "seeded-tool",
                "display_name": "Seeded Tool",
                "entrypoint": "main.py",
                "source_files": [{"path": "main.py", "text": "print('x')"}],
            },
        },
    )
    assert any("entry_module_path" in item["message"] for item in entrypoint_errors)
    assert any("text" in item["message"] for item in entrypoint_errors)


@pytest.mark.asyncio
async def test_spawn_schema_allows_bound_worker_payload_with_explicit_worker_slug(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    await ensure_platform_architect_worker_tools(
        db_session,
        tenant_id=tenant.id,
        actor_user_id=user.id,
    )
    await db_session.commit()
    tool = await _get_tool_by_slug(db_session, "architect-worker-spawn")

    errors = validate_tool_input_schema(
        tool,
        {
            "binding_ref": {
                "binding_type": "artifact_shared_draft",
                "binding_id": "11111111-1111-1111-1111-111111111111",
            },
            "worker_agent_slug": "artifact-coding-agent",
            "objective": "Implement the bound artifact draft.",
            "timeout_s": 600,
        },
    )

    assert errors == []


@pytest.mark.asyncio
async def test_spawn_group_target_schema_allows_bound_worker_payload_with_explicit_worker_slug(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    await ensure_platform_architect_worker_tools(
        db_session,
        tenant_id=tenant.id,
        actor_user_id=user.id,
    )
    await db_session.commit()
    tool = await _get_tool_by_slug(db_session, "architect-worker-spawn-group")

    errors = validate_tool_input_schema(
        tool,
        {
            "targets": [
                {
                    "binding_ref": {
                        "binding_type": "artifact_shared_draft",
                        "binding_id": "11111111-1111-1111-1111-111111111111",
                    },
                    "worker_agent_slug": "artifact-coding-agent",
                    "objective": "Implement the bound artifact draft.",
                }
            ],
            "timeout_s": 600,
        },
    )

    assert errors == []


@pytest.mark.asyncio
async def test_prepare_then_spawn_succeeds_across_separate_tool_sessions(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    await ensure_platform_architect_worker_tools(
        db_session,
        tenant_id=tenant.id,
        actor_user_id=user.id,
    )
    await db_session.commit()

    session_factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    monkeypatch.setattr("app.services.platform_architect_worker_tools.get_session", session_factory)

    spawned_run_id = uuid4()

    async def fake_spawn_run(
        self,
        *,
        caller_run_id,
        parent_node_id,
        target_agent_id,
        target_agent_slug,
        mapped_input_payload,
        failure_policy,
        timeout_s,
        scope_subset,
        idempotency_key,
        start_background,
    ):
        del caller_run_id, parent_node_id, target_agent_id, failure_policy, timeout_s, scope_subset, idempotency_key, start_background
        run = AgentRun(
            id=spawned_run_id,
            tenant_id=tenant.id,
            agent_id=uuid4(),
            user_id=user.id,
            initiator_user_id=user.id,
            status=RunStatus.queued,
            root_run_id=spawned_run_id,
            parent_run_id=None,
            input_params=mapped_input_payload,
            output_result={"worker_agent_slug": target_agent_slug},
        )
        self.db.add(run)
        await self.db.flush()
        return {
            "spawned_run_ids": [str(spawned_run_id)],
            "lineage": {"parent_run_id": str(uuid4())},
            "effective_scope_subset": ["agents.execute"],
        }

    monkeypatch.setattr(
        "app.services.orchestration_kernel_service.OrchestrationKernelService.spawn_run",
        fake_spawn_run,
    )

    prepare_result = await architect_worker_binding_prepare(
        {
            "__tool_runtime_context__": {
                "tenant_id": str(tenant.id),
                "user_id": str(user.id),
                "run_id": str(uuid4()),
            },
            "binding_type": "artifact_shared_draft",
            "prepare_mode": "create_new_draft",
            "title_prompt": "Create a random number tool",
            "draft_seed": {"kind": "tool_impl"},
        }
    )

    spawn_result = await architect_worker_spawn(
        {
            "__tool_runtime_context__": {
                "tenant_id": str(tenant.id),
                "user_id": str(user.id),
                "run_id": str(uuid4()),
            },
            "objective": "Implement the bound tool draft.",
            "binding_ref": prepare_result["binding_ref"],
            "worker_agent_slug": "artifact-coding-agent",
            "timeout_s": 120,
        }
    )

    assert spawn_result["mode"] == "async"
    assert spawn_result["run_id"] == str(spawned_run_id)
    assert spawn_result["binding_ref"] == prepare_result["binding_ref"]


def test_architect_graph_instructions_include_async_worker_flow():
    graph = build_architect_graph_definition(
        model_id="model-1",
        tool_ids=[
            "platform-rag",
            "platform-agents",
            "platform-assets",
            "platform-governance",
            "architect-worker-binding-prepare",
            "architect-worker-binding-get-state",
            "architect-worker-spawn",
            "architect-worker-spawn-group",
            "architect-worker-get-run",
            "architect-worker-join",
            "architect-worker-cancel",
        ],
    )
    runtime_node = next(node for node in graph["nodes"] if node["id"] == "architect_runtime")
    instructions = runtime_node["config"]["instructions"]

    assert "architect-worker-spawn" in instructions
    assert "architect-worker-binding-prepare" in instructions
    assert "Do not call raw orchestration.* actions" in instructions
    assert "must not end the run after spawn/join alone" in instructions
    assert "Do not treat successful worker completion as task completion by itself" in instructions
    assert "Do not invent nested fields like task.instructions" in instructions
    assert "agents.create_shell" in instructions
    assert "rag.create_pipeline_shell" in instructions
    assert "draft_seed.kind" in instructions
    assert "Do not invent non-canonical binding fields such as create, files, entrypoint, or text." in instructions
    assert "artifact-coding-agent-call" not in instructions
    assert "artifact-coding-session-prepare" not in instructions


@pytest.mark.asyncio
async def test_spawn_group_rejects_duplicate_binding_refs_before_kernel(monkeypatch):
    service = PlatformArchitectWorkerRuntimeService(SimpleNamespace())

    class _FakeAdapter:
        async def build_spawn_payload(self, *, tenant_id, user_id, binding_ref):
            del tenant_id, user_id, binding_ref
            return {"worker_agent_slug": "artifact-coding-agent", "context": {}}

    service.bindings = SimpleNamespace(adapter_for_ref=lambda _ref: _FakeAdapter())

    with pytest.raises(RuntimeError, match="BINDING_RUN_ACTIVE"):
        await service.spawn_group(
            {
                "__tool_runtime_context__": {
                    "tenant_id": str(uuid4()),
                    "user_id": str(uuid4()),
                    "run_id": str(uuid4()),
                },
                "targets": [
                    {
                        "objective": "first",
                        "binding_ref": {"binding_type": "artifact_shared_draft", "binding_id": "11111111-1111-1111-1111-111111111111"},
                    },
                    {
                        "objective": "second",
                        "binding_ref": {"binding_type": "artifact_shared_draft", "binding_id": "11111111-1111-1111-1111-111111111111"},
                    },
                ],
            }
        )


@pytest.mark.asyncio
async def test_worker_get_run_returns_binding_ref_from_run_record(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    parent = AgentRun(
        tenant_id=tenant.id,
        agent_id=uuid4(),
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.running,
        input_params={"messages": [], "context": {}},
    )
    db_session.add(parent)
    await db_session.flush()
    parent.root_run_id = parent.id
    child = AgentRun(
        tenant_id=tenant.id,
        agent_id=uuid4(),
        user_id=user.id,
        initiator_user_id=user.id,
        status=RunStatus.completed,
        root_run_id=parent.id,
        parent_run_id=parent.id,
        input_params={
            "context": {
                "architect_worker_binding_ref": {
                    "binding_type": "artifact_shared_draft",
                    "binding_id": str(uuid4()),
                }
            }
        },
        output_result={"ok": True},
    )
    db_session.add(child)
    await db_session.commit()

    service = PlatformArchitectWorkerRuntimeService(db_session)
    result = await service.get_run(
        {
            "__tool_runtime_context__": {
                "tenant_id": str(tenant.id),
                "user_id": str(user.id),
                "run_id": str(parent.id),
            },
            "run_id": str(child.id),
        }
    )

    assert result["run_id"] == str(child.id)
    assert result["status"] == RunStatus.completed.value
    assert result["binding_ref"]["binding_type"] == "artifact_shared_draft"
