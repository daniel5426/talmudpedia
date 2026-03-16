from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessageChunk
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionMode
from app.db.postgres.models.agents import Agent, AgentRun, RunStatus
from app.db.postgres.models.artifact_runtime import Artifact, ArtifactCodingSession, ArtifactCodingSharedDraft, ArtifactRun
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.registry import ModelCapabilityType, ModelRegistry, ModelStatus
from app.services import registry_seeding
from app.services.artifact_coding_runtime_service import ArtifactCodingRuntimeService
from app.services.model_resolver import ModelResolver
from app.services.platform_architect_worker_runtime_service import PlatformArchitectWorkerRuntimeService
from app.services.workload_provisioning_service import WorkloadProvisioningService


class _ScriptedProvider:
    def __init__(self, builders):
        self._builders = builders
        self._idx = 0

    async def stream(self, _messages, _system_prompt=None, **_kwargs):
        response = self._builders[self._idx]()
        self._idx += 1
        for chunk in response:
            yield chunk


def _tool_call_chunks(tool_name: str, payload: dict):
    return [
        AIMessageChunk(
            content="",
            tool_call_chunks=[{"id": f"call-{tool_name}", "name": tool_name, "args": __import__("json").dumps(payload)}],
        )
    ]


async def _seed_tenant_user_and_model(db_session):
    suffix = uuid4().hex[:8]
    existing_defaults = (
        await db_session.execute(
            select(ModelRegistry).where(
                ModelRegistry.tenant_id.is_(None),
                ModelRegistry.capability_type == ModelCapabilityType.CHAT,
                ModelRegistry.is_default.is_(True),
            )
        )
    ).scalars().all()
    for item in existing_defaults:
        item.is_default = False
    tenant = Tenant(name=f"Architect Worker E2E {suffix}", slug=f"architect-worker-e2e-{suffix}")
    user = User(email=f"architect-worker-e2e-{suffix}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()
    model = ModelRegistry(
        tenant_id=None,
        name="Unit Chat Model",
        slug=f"unit-chat-{suffix}",
        capability_type=ModelCapabilityType.CHAT,
        status=ModelStatus.ACTIVE,
        is_active=True,
        is_default=True,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(user)
    return tenant, user, model


@pytest.mark.asyncio
async def test_seeded_architect_run_spawns_artifact_worker_and_persists_artifact(db_session, monkeypatch):
    tenant, user, _model = await _seed_tenant_user_and_model(db_session)
    architect = await registry_seeding.seed_platform_architect_agent(db_session)
    assert architect is not None
    tenant_id = architect.tenant_id

    provisioning = WorkloadProvisioningService(db_session)
    await provisioning.provision_agent_policy(agent=architect, actor_user_id=user.id)
    await db_session.commit()

    shared: dict[str, object] = {}
    draft_key = f"architect-worker-{uuid4().hex[:8]}"
    seeded_binding = await PlatformArchitectWorkerRuntimeService(db_session).prepare_binding(
        {
            "__tool_runtime_context__": {
                "tenant_id": str(tenant_id),
                "user_id": str(user.id),
                "run_id": str(uuid4()),
            },
            "binding_type": "artifact_shared_draft",
            "prepare_mode": "create_new_draft",
            "replace_snapshot": True,
            "draft_key": draft_key,
            "title_prompt": "Create a greeting tool artifact",
            "draft_seed": {
                "kind": "tool_impl",
                "display_name": "Greeting Tool",
                "description": "Draft greeting tool",
                "entry_module_path": "main.py",
                "runtime_target": "cloudflare_workers",
            },
        }
    )

    original_prepare_binding = PlatformArchitectWorkerRuntimeService.prepare_binding
    child_run_id = uuid4()
    async def capture_prepare(self, payload):
        result = await original_prepare_binding(self, payload)
        shared["binding_ref"] = result["binding_ref"]
        return result

    async def capture_spawn(self, payload):
        parent_run_id = UUID(str(payload["__tool_runtime_context__"]["run_id"]))
        child_run = AgentRun(
            id=child_run_id,
            tenant_id=tenant_id,
            agent_id=uuid4(),
            user_id=user.id,
            initiator_user_id=user.id,
            status=RunStatus.completed,
            root_run_id=parent_run_id,
            parent_run_id=parent_run_id,
            input_params={
                "context": {
                    "architect_worker_binding_ref": seeded_binding["binding_ref"],
                }
            },
            output_result={"summary": "Artifact draft updated."},
        )
        db_session.add(child_run)
        await db_session.flush()

        runtime = ArtifactCodingRuntimeService(db_session)
        session, shared_draft, _artifact, _run, _last_test_run = await runtime.get_session_state_for_user(
            tenant_id=tenant_id,
            user_id=user.id,
            session_id=UUID(str(seeded_binding["binding_ref"]["binding_id"])),
        )
        snapshot = dict(shared_draft.working_draft_snapshot or {})
        snapshot["display_name"] = "Greeting Tool"
        snapshot["description"] = "A greeting tool generated by architect worker flow"
        snapshot["source_files"] = [
            {
                "path": "main.py",
                "content": "def execute(inputs, config, context):\n    return {\"message\": \"shalom\"}\n",
            }
        ]
        shared_draft.working_draft_snapshot = snapshot
        shared_draft.last_run_id = child_run.id
        session.last_run_id = child_run.id
        await db_session.commit()

        shared["run_id"] = str(child_run.id)
        return {
            "mode": "async",
            "run_id": str(child_run.id),
            "status": "queued",
            "worker_agent_slug": "artifact-coding-agent",
            "binding_ref": seeded_binding["binding_ref"],
            "lineage": {"parent_run_id": str(parent_run_id)},
            "effective_scope_subset": ["agents.execute"],
        }

    monkeypatch.setattr(PlatformArchitectWorkerRuntimeService, "prepare_binding", capture_prepare)
    monkeypatch.setattr(PlatformArchitectWorkerRuntimeService, "spawn_worker", capture_spawn)

    @asynccontextmanager
    async def shared_session():
        yield db_session

    monkeypatch.setattr("app.services.platform_architect_worker_tools.get_session", shared_session)
    monkeypatch.setattr("app.services.artifact_coding_agent_tools.get_session", shared_session)

    provider = _ScriptedProvider(
        [
            lambda: _tool_call_chunks(
                "architect-worker-binding-prepare",
                {
                    "binding_type": "artifact_shared_draft",
                    "prepare_mode": "reuse_existing",
                    "binding_id": seeded_binding["binding_ref"]["binding_id"],
                },
            ),
            lambda: _tool_call_chunks(
                "architect-worker-spawn",
                {
                    "objective": "Update the bound artifact draft into a minimal greeting tool.",
                    "constraints": ["Use main.py as the entry file."],
                    "binding_ref": seeded_binding["binding_ref"],
                },
            ),
            lambda: _tool_call_chunks(
                "architect-worker-await",
                {
                    "run_id": str(child_run_id),
                },
            ),
            lambda: _tool_call_chunks(
                "architect-worker-binding-persist-artifact",
                {
                    "binding_ref": seeded_binding["binding_ref"],
                },
            ),
            lambda: [AIMessageChunk(content="Successfully created the greeting artifact through the worker flow.")],
        ]
    )

    async def fake_resolve(_self, _model_id):
        return provider

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)

    executor = AgentExecutorService(db=db_session)
    run_id = await executor.start_run(
        agent_id=architect.id,
        input_params={
            "messages": [{"role": "user", "content": "Create a greeting tool artifact using the worker flow."}],
            "context": {},
        },
        user_id=user.id,
        background=False,
        mode=ExecutionMode.DEBUG,
    )
    async for _ in executor.run_and_stream(run_id, db_session, mode=ExecutionMode.DEBUG):
        pass

    run = await db_session.get(AgentRun, run_id)
    assert run is not None
    assert run.status == RunStatus.completed
    output_result = run.output_result if isinstance(run.output_result, dict) else {}
    final_output = str(
        output_result.get("final_output")
        or output_result.get("last_agent_output")
        or output_result.get("output")
        or output_result
    )
    assert "Successfully created the greeting artifact" in final_output

    child_run = await db_session.get(AgentRun, child_run_id)
    assert child_run is not None
    assert child_run.parent_run_id == run.id
    assert child_run.root_run_id == run.id
    assert child_run.status == RunStatus.completed

    session = (
        await db_session.execute(
            select(ArtifactCodingSession).where(ArtifactCodingSession.id == seeded_binding["binding_ref"]["binding_id"])
        )
    ).scalar_one()
    shared_draft = (
        await db_session.execute(
            select(ArtifactCodingSharedDraft).where(ArtifactCodingSharedDraft.last_run_id == child_run.id)
        )
    ).scalar_one()
    assert session.last_run_id == child_run.id
    assert shared_draft.last_run_id == child_run.id
    assert shared_draft.working_draft_snapshot["source_files"][0]["path"] == "main.py"

    artifact = (
        await db_session.execute(
            select(Artifact)
            .options(selectinload(Artifact.latest_draft_revision))
            .where(
                Artifact.tenant_id == tenant_id,
                Artifact.display_name == "Greeting Tool",
            )
        )
    ).scalar_one()
    assert session.artifact_id == artifact.id
    assert shared_draft.artifact_id == artifact.id
    assert artifact.display_name == "Greeting Tool"
    assert artifact.latest_draft_revision is not None
    assert artifact.latest_draft_revision.entry_module_path == "main.py"

    artifact_runs = (
        await db_session.execute(
            select(ArtifactRun).where(ArtifactRun.artifact_id == artifact.id)
        )
    ).scalars().all()
    assert artifact_runs == []


@pytest.mark.asyncio
async def test_seeded_architect_run_rejects_second_mutating_spawn_for_active_binding(db_session, monkeypatch):
    tenant, user, _model = await _seed_tenant_user_and_model(db_session)
    architect = await registry_seeding.seed_platform_architect_agent(db_session)
    assert architect is not None

    provisioning = WorkloadProvisioningService(db_session)
    await provisioning.provision_agent_policy(agent=architect, actor_user_id=user.id)
    await db_session.commit()

    shared: dict[str, object] = {}
    draft_key = f"architect-worker-blocked-{uuid4().hex[:8]}"
    seeded_binding = await PlatformArchitectWorkerRuntimeService(db_session).prepare_binding(
        {
            "__tool_runtime_context__": {
                "tenant_id": str(architect.tenant_id),
                "user_id": str(user.id),
                "run_id": str(uuid4()),
            },
            "binding_type": "artifact_shared_draft",
            "prepare_mode": "create_new_draft",
            "replace_snapshot": True,
            "draft_key": draft_key,
            "title_prompt": "Prepare a bound artifact draft",
            "draft_seed": {
                "kind": "tool_impl",
                "display_name": "Blocked Tool",
                "description": "Draft for binding lock test",
                "entry_module_path": "main.py",
                "runtime_target": "cloudflare_workers",
            },
        }
    )
    original_prepare_binding = PlatformArchitectWorkerRuntimeService.prepare_binding
    child_run_id = uuid4()

    async def capture_prepare(self, payload):
        result = await original_prepare_binding(self, payload)
        shared["binding_ref"] = result["binding_ref"]
        return result

    async def capture_spawn(self, payload):
        if shared.get("first_run_id"):
            raise RuntimeError("BINDING_RUN_ACTIVE")
        parent_run_id = UUID(str(payload["__tool_runtime_context__"]["run_id"]))
        child_run = AgentRun(
            id=child_run_id,
            tenant_id=architect.tenant_id,
            agent_id=uuid4(),
            user_id=user.id,
            initiator_user_id=user.id,
            status=RunStatus.queued,
            root_run_id=parent_run_id,
            parent_run_id=parent_run_id,
            input_params={
                "context": {
                    "architect_worker_binding_ref": seeded_binding["binding_ref"],
                }
            },
        )
        db_session.add(child_run)
        await db_session.flush()

        runtime = ArtifactCodingRuntimeService(db_session)
        session, shared_draft, _artifact, _run, _last_test_run = await runtime.get_session_state_for_user(
            tenant_id=architect.tenant_id,
            user_id=user.id,
            session_id=UUID(str(seeded_binding["binding_ref"]["binding_id"])),
        )
        shared_draft.last_run_id = child_run.id
        session.active_run_id = child_run.id
        await db_session.commit()

        shared["first_run_id"] = str(child_run.id)
        return {
            "mode": "async",
            "run_id": str(child_run.id),
            "status": "queued",
            "worker_agent_slug": "artifact-coding-agent",
            "binding_ref": seeded_binding["binding_ref"],
            "lineage": {"parent_run_id": str(parent_run_id)},
            "effective_scope_subset": ["agents.execute"],
        }

    monkeypatch.setattr(PlatformArchitectWorkerRuntimeService, "prepare_binding", capture_prepare)
    monkeypatch.setattr(PlatformArchitectWorkerRuntimeService, "spawn_worker", capture_spawn)

    @asynccontextmanager
    async def shared_session():
        yield db_session

    monkeypatch.setattr("app.services.platform_architect_worker_tools.get_session", shared_session)

    provider = _ScriptedProvider(
        [
            lambda: _tool_call_chunks(
                "architect-worker-binding-prepare",
                {
                    "binding_type": "artifact_shared_draft",
                    "prepare_mode": "reuse_existing",
                    "binding_id": seeded_binding["binding_ref"]["binding_id"],
                },
            ),
            lambda: _tool_call_chunks(
                "architect-worker-spawn",
                {
                    "objective": "Start a mutating artifact worker run.",
                    "binding_ref": seeded_binding["binding_ref"],
                },
            ),
            lambda: _tool_call_chunks(
                "architect-worker-spawn",
                {
                    "objective": "Attempt a second mutating artifact worker run on the same binding.",
                    "binding_ref": seeded_binding["binding_ref"],
                },
            ),
            lambda: [AIMessageChunk(content="The artifact binding is busy with an active worker run, so I did not start a second mutating worker.")],
        ]
    )

    async def fake_resolve(_self, _model_id):
        return provider

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)

    executor = AgentExecutorService(db=db_session)
    run_id = await executor.start_run(
        agent_id=architect.id,
        input_params={
            "messages": [{"role": "user", "content": "Start two artifact workers on the same draft."}],
            "context": {},
        },
        user_id=user.id,
        background=False,
        mode=ExecutionMode.DEBUG,
    )
    async for _ in executor.run_and_stream(run_id, db_session, mode=ExecutionMode.DEBUG):
        pass

    run = await db_session.get(AgentRun, run_id)
    assert run is not None
    assert run.status == RunStatus.completed
    output_result = run.output_result if isinstance(run.output_result, dict) else {}
    final_output = str(
        output_result.get("final_output")
        or output_result.get("last_agent_output")
        or output_result.get("output")
        or output_result
    )
    assert "binding is busy with an active worker run" in final_output

    child_runs = (
        await db_session.execute(
            select(AgentRun).where(AgentRun.parent_run_id == run.id).order_by(AgentRun.created_at.asc())
        )
    ).scalars().all()
    assert len(child_runs) == 1
    assert child_runs[0].status == RunStatus.queued

    session = (
        await db_session.execute(
            select(ArtifactCodingSession).where(ArtifactCodingSession.id == seeded_binding["binding_ref"]["binding_id"])
        )
    ).scalar_one()
    assert session.active_run_id == child_runs[0].id
