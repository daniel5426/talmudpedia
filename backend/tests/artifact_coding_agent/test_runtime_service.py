from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.agent.execution.trace_recorder import ExecutionTraceRecorder
from app.api.routers.artifact_coding_agent import _build_session_detail_response
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.artifact_runtime import ArtifactCodingMessage, ArtifactCodingSession, ArtifactCodingSharedDraft, ArtifactRun, ArtifactRunDomain, ArtifactRunEvent, ArtifactRunStatus
from app.db.postgres.models.registry import IntegrationCredential, IntegrationCredentialCategory, ToolRegistry
from app.services.artifact_coding_shared_draft_service import ArtifactCodingSharedDraftService
from app.db.postgres.models.identity import Tenant, User
from app.services.artifact_coding_chat_history_service import ArtifactCodingChatHistoryService
from app.services.artifact_coding_agent_profile import ensure_artifact_coding_agent_profile
from app.services.artifact_coding_agent_test_tools import (
    artifact_coding_await_last_test_result,
    artifact_coding_run_test,
)
from app.services.artifact_coding_agent_tools import (
    _resolve_session_context,
    artifact_coding_create_file,
    artifact_coding_list_credentials,
    artifact_coding_set_tool_contract,
    artifact_coding_set_entry_module,
    ensure_artifact_coding_tools,
)
from app.services.artifact_coding_runtime_service import ArtifactCodingRuntimeService
from app.services.artifact_runtime.revision_service import ArtifactRevisionService
from app.services.platform_architect_worker_tools import (
    architect_worker_binding_get_state,
    architect_worker_binding_prepare,
)


async def _seed_tenant_and_user(db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"Artifact Tenant {suffix}", slug=f"artifact-tenant-{suffix}")
    user = User(email=f"artifact-owner-{suffix}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(user)
    return tenant, user


def _tool_impl_create_payload(name: str) -> dict[str, object]:
    return {
        "display_name": f"{name}-display",
        "description": "artifact coding payload",
        "kind": "tool_impl",
        "runtime": {
            "source_files": [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return inputs"}],
            "entry_module_path": "main.py",
            "python_dependencies": ["httpx>=0.27"],
            "runtime_target": "cloudflare_workers",
        },
        "capabilities": {"network_access": False},
        "config_schema": {"type": "object", "properties": {"enabled": {"type": "boolean"}}},
        "tool_contract": {
            "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}},
            "output_schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
            "side_effects": [],
            "execution_mode": "interactive",
            "tool_ui": {},
        },
    }


async def _create_artifact_from_payload(db_session, *, tenant_id, user_id, payload: dict[str, object]):
    service = ArtifactRevisionService(db_session)
    artifact = await service.create_artifact(
        tenant_id=tenant_id,
        created_by=user_id,
        display_name=str(payload["display_name"]),
        description=str(payload.get("description") or ""),
        kind=str(payload["kind"]),
        source_files=list(payload["runtime"]["source_files"]),
        entry_module_path=str(payload["runtime"]["entry_module_path"]),
        python_dependencies=list(payload["runtime"].get("python_dependencies") or []),
        runtime_target=str(payload["runtime"].get("runtime_target") or "cloudflare_workers"),
        capabilities=dict(payload.get("capabilities") or {}),
        config_schema=dict(payload.get("config_schema") or {}),
        tool_contract=dict(payload.get("tool_contract") or {}),
    )
    await db_session.commit()
    return artifact


async def _create_artifact_coding_worker_run(
    db_session,
    *,
    tenant,
    user,
    agent,
    session,
    shared_draft,
):
    run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        thread_id=session.agent_thread_id,
        surface="artifact_coding_agent",
        status=RunStatus.completed,
        input_params={
            "context": {
                "thread_id": str(session.agent_thread_id),
                "artifact_coding_session_id": str(session.id),
                "artifact_coding_shared_draft_id": str(shared_draft.id),
            }
        },
        output_result={"final_output": "worker context"},
    )
    db_session.add(run)
    await db_session.flush()
    return run


@pytest.mark.asyncio
async def test_runtime_service_relinks_draft_key_to_saved_artifact_without_new_shared_draft(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)

    runtime = ArtifactCodingRuntimeService(db_session)
    draft_key = f"draft-{uuid4().hex[:8]}"
    snapshot = {
        "display_name": "Delegated Tool",
        "description": "created through artifact coding",
        "kind": "tool_impl",
        "source_files": [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return inputs"}],
        "entry_module_path": "main.py",
        "python_dependencies": "httpx>=0.27",
        "runtime_target": "cloudflare_workers",
        "capabilities": {"network_access": False},
        "config_schema": {"type": "object"},
        "tool_contract": {"input_schema": {}, "output_schema": {}, "side_effects": [], "execution_mode": "interactive", "tool_ui": {}},
    }

    prepared = await runtime.prepare_session(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        title_prompt="Create a delegated tool artifact",
        artifact_id=None,
        draft_key=draft_key,
        chat_session_id=None,
        draft_snapshot=snapshot,
        replace_snapshot=True,
    )
    await db_session.commit()

    initial_state = runtime.serialize_runtime_state(
        session=prepared.session,
        shared_draft=prepared.shared_draft,
        artifact=None,
        run=None,
        last_test_run=None,
    )
    create_input = initial_state["platform_assets_create_input"]
    assert create_input is not None
    assert create_input["action"] == "artifacts.create"
    artifact = await _create_artifact_from_payload(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        payload=create_input["payload"],
    )

    relinked = await runtime.prepare_session(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        title_prompt="Persist delegated tool artifact",
        artifact_id=artifact.id,
        draft_key=draft_key,
        chat_session_id=prepared.session.id,
        draft_snapshot=None,
        replace_snapshot=False,
    )
    await db_session.commit()

    shared_drafts = (
        await db_session.execute(
            select(ArtifactCodingSharedDraft).where(ArtifactCodingSharedDraft.tenant_id == tenant.id)
        )
    ).scalars().all()

    assert len(shared_drafts) == 1
    assert relinked.shared_draft.id == prepared.shared_draft.id

    updated_state = runtime.serialize_runtime_state(
        session=relinked.session,
        shared_draft=relinked.shared_draft,
        artifact=artifact,
        run=None,
        last_test_run=None,
    )
    assert updated_state["platform_assets_create_input"] is None
    assert updated_state["platform_assets_update_input"]["action"] == "artifacts.update"
    assert updated_state["platform_assets_update_input"]["payload"]["artifact_id"] == str(artifact.id)
    assert updated_state["platform_assets_update_input"]["payload"]["patch"]["display_name"] == "Delegated Tool"


@pytest.mark.asyncio
async def test_build_initial_snapshot_from_seed_uses_seed_kind_without_agent_node_fallback(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)

    runtime = ArtifactCodingRuntimeService(db_session)
    snapshot = runtime.build_initial_snapshot_from_seed(
        {
            "kind": "tool_impl",
            "display_name": "Seeded Tool",
            "description": "seed-based initialization",
            "entry_module_path": "src/main.py",
            "runtime_target": "cloudflare_workers",
        }
    )

    assert snapshot["kind"] == "tool_impl"
    assert snapshot["display_name"] == "Seeded Tool"
    assert snapshot["entry_module_path"] == "src/main.py"
    assert snapshot["source_files"][0]["path"] == "src/main.py"


@pytest.mark.asyncio
async def test_build_initial_snapshot_from_seed_supports_javascript_create_mode(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)

    runtime = ArtifactCodingRuntimeService(db_session)
    snapshot = runtime.build_initial_snapshot_from_seed(
        {
            "kind": "tool_impl",
            "language": "javascript",
            "display_name": "Seeded JS Tool",
        }
    )

    assert snapshot["kind"] == "tool_impl"
    assert snapshot["language"] == "javascript"
    assert snapshot["entry_module_path"] == "main.js"
    assert snapshot["source_files"][0]["path"] == "main.js"
    assert "export async function execute" in snapshot["source_files"][0]["content"]


@pytest.mark.asyncio
async def test_prepare_session_without_scope_keeps_direct_shared_draft_link(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)

    runtime = ArtifactCodingRuntimeService(db_session)
    prepared = await runtime.prepare_session(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        title_prompt="Create a scope-free delegated draft",
        artifact_id=None,
        draft_key=None,
        chat_session_id=None,
        draft_snapshot=runtime.build_initial_snapshot_from_seed(
            {
                "kind": "tool_impl",
                "display_name": "Scope Free Tool",
                "entry_module_path": "src/main.py",
            }
        ),
        replace_snapshot=True,
    )
    await db_session.commit()

    shared_drafts_before = (
        await db_session.execute(
            select(ArtifactCodingSharedDraft).where(ArtifactCodingSharedDraft.tenant_id == tenant.id)
        )
    ).scalars().all()

    assert len(shared_drafts_before) == 1
    assert prepared.session.shared_draft_id == prepared.shared_draft.id

    resolved = await ArtifactCodingSharedDraftService(db_session).resolve_for_session(session=prepared.session)
    state_session, state_shared_draft, _artifact, _run, _last_test_run = await runtime.get_session_state_for_user(
        tenant_id=tenant.id,
        user_id=user.id,
        session_id=prepared.session.id,
    )
    shared_drafts_after = (
        await db_session.execute(
            select(ArtifactCodingSharedDraft).where(ArtifactCodingSharedDraft.tenant_id == tenant.id)
        )
    ).scalars().all()

    assert len(shared_drafts_after) == 1
    assert resolved.id == prepared.shared_draft.id
    assert state_session.shared_draft_id == prepared.shared_draft.id
    assert state_shared_draft.id == prepared.shared_draft.id
    assert state_shared_draft.working_draft_snapshot["kind"] == "tool_impl"
    assert state_shared_draft.working_draft_snapshot["entry_module_path"] == "src/main.py"


@pytest.mark.asyncio
async def test_artifact_tools_use_run_pinned_shared_draft_when_session_binding_changes(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    runtime = ArtifactCodingRuntimeService(db_session)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)
    prepared = await runtime.prepare_session(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        title_prompt="Use the pinned draft",
        artifact_id=None,
        draft_key=f"draft-{uuid4().hex[:8]}",
        chat_session_id=None,
        draft_snapshot=runtime.build_initial_snapshot_from_seed(
            {
                "kind": "tool_impl",
                "display_name": "Pinned Draft",
            }
        ),
        replace_snapshot=True,
    )
    alternate_shared_draft = await ArtifactCodingSharedDraftService(db_session).get_or_create_for_scope(
        tenant_id=tenant.id,
        artifact_id=None,
        draft_key=f"draft-{uuid4().hex[:8]}",
        initial_snapshot=runtime.build_initial_snapshot_from_seed(
            {
                "kind": "tool_impl",
                "display_name": "Rebound Draft",
            }
        ),
    )
    prepared.session.shared_draft_id = alternate_shared_draft.id
    prepared.shared_draft.working_draft_snapshot["display_name"] = "Pinned Draft"
    alternate_shared_draft.working_draft_snapshot["display_name"] = "Rebound Draft"
    run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        thread_id=prepared.session.agent_thread_id,
        surface="artifact_coding_agent",
        status=RunStatus.completed,
        input_params={
            "context": {
                "thread_id": str(prepared.session.agent_thread_id),
                "artifact_coding_session_id": str(prepared.session.id),
                "artifact_coding_shared_draft_id": str(prepared.shared_draft.id),
            }
        },
        output_result={"final_output": "worker context"},
    )
    db_session.add(run)
    await db_session.commit()

    _session, shared_draft, resolved_run, _artifact = await _resolve_session_context(
        db_session,
        {"run_id": str(run.id)},
    )

    assert resolved_run.id == run.id
    assert shared_draft.id == prepared.shared_draft.id
    assert shared_draft.working_draft_snapshot["display_name"] == "Pinned Draft"


@pytest.mark.asyncio
async def test_reconcile_session_run_marks_completed_run_failed_after_tool_failure(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    runtime = ArtifactCodingRuntimeService(db_session)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)
    prepared = await runtime.prepare_session(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        title_prompt="Trigger tool failure reconciliation",
        artifact_id=None,
        draft_key=None,
        chat_session_id=None,
        draft_snapshot=runtime.build_initial_snapshot_from_seed({"kind": "tool_impl"}),
        replace_snapshot=True,
    )
    run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        thread_id=prepared.session.agent_thread_id,
        surface="artifact_coding_agent",
        status=RunStatus.completed,
        input_params={
            "context": {
                "thread_id": str(prepared.session.agent_thread_id),
                "artifact_coding_session_id": str(prepared.session.id),
                "artifact_coding_shared_draft_id": str(prepared.shared_draft.id),
            }
        },
        output_result={"final_output": "Everything succeeded"},
    )
    db_session.add(run)
    await db_session.flush()
    await runtime.history.mark_run_started(session=prepared.session, run_id=run.id)
    await runtime.history.persist_user_message(
        session_id=prepared.session.id,
        run_id=run.id,
        content="Run the tests",
    )
    await ExecutionTraceRecorder(serializer=lambda value: value).save_event(
        run.id,
        db_session,
        {
            "event": "tool.failed",
            "sequence": 1,
            "ts": "2026-03-25T17:07:00+00:00",
            "data": {"error": "Artifact coding shared draft mismatch"},
        },
    )
    await db_session.commit()

    await ArtifactCodingChatHistoryService(db_session).reconcile_session_run(session=prepared.session, run=run)
    await db_session.commit()
    await db_session.refresh(run)

    assistant_message = (
        await db_session.execute(
            select(ArtifactCodingMessage).where(
                ArtifactCodingMessage.session_id == prepared.session.id,
                ArtifactCodingMessage.run_id == run.id,
                ArtifactCodingMessage.role == "assistant",
            )
        )
    ).scalar_one_or_none()

    assert run.status == RunStatus.failed
    assert run.error_message == "Artifact coding shared draft mismatch"
    assert assistant_message is not None
    assert assistant_message.content == "Execution failed: Artifact coding shared draft mismatch"


@pytest.mark.asyncio
async def test_build_run_messages_maps_orchestrator_role_to_system(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)
    runtime = ArtifactCodingRuntimeService(db_session)
    prepared = await runtime.prepare_session(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        title_prompt="Start orchestrator history mapping test",
        artifact_id=None,
        draft_key=None,
        chat_session_id=None,
        draft_snapshot=runtime.build_initial_snapshot_from_seed({"kind": "tool_impl"}),
        replace_snapshot=True,
    )
    run_id = uuid4()
    await runtime.history.persist_user_message(
        session_id=prepared.session.id,
        run_id=run_id,
        content="Initial human request",
    )
    await runtime.history.persist_assistant_message(
        session_id=prepared.session.id,
        run_id=run_id,
        content="Initial assistant reply",
    )
    await runtime.history.persist_orchestrator_message(
        session_id=prepared.session.id,
        run_id=run_id,
        content="Apply the requested changes without re-asking.",
    )
    await db_session.commit()

    messages = await ArtifactCodingChatHistoryService(db_session).build_run_messages(
        session_id=prepared.session.id,
        current_prompt="Add README.md",
        current_role="orchestrator",
    )

    assert messages == [
        {"role": "user", "content": "Initial human request"},
        {"role": "assistant", "content": "Initial assistant reply"},
        {"role": "system", "content": "Apply the requested changes without re-asking."},
        {"role": "system", "content": "Add README.md"},
    ]


@pytest.mark.asyncio
async def test_session_detail_includes_run_events_for_failed_run_without_assistant_message(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)
    runtime = ArtifactCodingRuntimeService(db_session)
    prepared = await runtime.prepare_session(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        title_prompt="Show failed partial history",
        artifact_id=None,
        draft_key=None,
        chat_session_id=None,
        draft_snapshot=runtime.build_initial_snapshot_from_seed({"kind": "tool_impl"}),
        replace_snapshot=True,
    )
    run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        thread_id=prepared.session.agent_thread_id,
        surface="artifact_coding_agent",
        status=RunStatus.running,
        input_params={
            "context": {
                "thread_id": str(prepared.session.agent_thread_id),
                "artifact_coding_session_id": str(prepared.session.id),
                "artifact_coding_shared_draft_id": str(prepared.shared_draft.id),
            }
        },
        output_result=None,
    )
    db_session.add(run)
    await db_session.flush()
    await runtime.history.mark_run_started(session=prepared.session, run_id=run.id)
    await runtime.history.persist_user_message(
        session_id=prepared.session.id,
        run_id=run.id,
        content="Please fix the artifact",
    )
    recorder = ExecutionTraceRecorder(serializer=lambda value: value)
    await recorder.save_event(
        run.id,
        db_session,
        {
            "event": "token",
            "sequence": 1,
            "ts": "2026-03-25T18:00:00+00:00",
            "content": "Inspecting files. ",
            "data": {"content": "Inspecting files. "},
        },
    )
    await recorder.save_event(
        run.id,
        db_session,
        {
            "event": "on_tool_start",
            "name": "artifact-coding-read-file",
            "span_id": "tool-1",
            "sequence": 2,
            "ts": "2026-03-25T18:00:01+00:00",
            "data": {"summary": "Read main.py"},
        },
    )
    await db_session.commit()
    session = await db_session.get(ArtifactCodingSession, prepared.session.id)
    assert session is not None
    await db_session.refresh(session)

    detail = await _build_session_detail_response(
        db=db_session,
        tenant_id=tenant.id,
        session=session,
        before_message_id=None,
        limit=10,
    )

    assert [message.role for message in detail.messages] == ["user"]
    assert [event.event for event in detail.run_events] == ["assistant.delta", "tool.started"]
    assert detail.run_events[0].run_id == str(run.id)


@pytest.mark.asyncio
async def test_prepare_session_run_input_uses_native_session_thread_and_orchestrator_role(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    runtime = ArtifactCodingRuntimeService(db_session)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)
    prepared = await runtime.prepare_session(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        title_prompt="Prepare native session input",
        artifact_id=None,
        draft_key=None,
        chat_session_id=None,
        draft_snapshot=runtime.build_initial_snapshot_from_seed({"kind": "tool_impl"}),
        replace_snapshot=True,
    )
    run_id = uuid4()
    await runtime.history.persist_user_message(
        session_id=prepared.session.id,
        run_id=run_id,
        content="Initial human request",
    )
    await runtime.history.persist_assistant_message(
        session_id=prepared.session.id,
        run_id=run_id,
        content="Initial assistant reply",
    )
    await db_session.commit()

    prepared_input = await runtime.prepare_session_run_input(
        tenant_id=tenant.id,
        user_id=user.id,
        session=prepared.session,
        shared_draft=prepared.shared_draft,
        prompt="Apply the requested changes without re-asking.",
        prompt_role="orchestrator",
        model_id=None,
        extra_context={"architect_worker_binding_ref": {"binding_type": "artifact_shared_draft", "binding_id": str(prepared.session.id)}},
    )

    assert prepared_input["thread_id"] == str(prepared.session.agent_thread_id)
    assert prepared_input["input_params"]["thread_id"] == str(prepared.session.agent_thread_id)
    assert prepared_input["input_params"]["messages"] == [
        {"role": "user", "content": "Initial human request"},
        {"role": "assistant", "content": "Initial assistant reply"},
        {"role": "system", "content": "Apply the requested changes without re-asking."},
    ]
    assert prepared_input["input_params"]["context"]["conversation_message_role"] == "orchestrator"


@pytest.mark.asyncio
async def test_serialize_runtime_state_separates_verification_state_from_persistence_readiness(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    runtime = ArtifactCodingRuntimeService(db_session)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)
    prepared = await runtime.prepare_session(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        title_prompt="Prepare verification state split test",
        artifact_id=None,
        draft_key=None,
        chat_session_id=None,
        draft_snapshot=runtime.build_initial_snapshot_from_seed(
            {
                "kind": "tool_impl",
                "display_name": "Verify Split",
            }
        ),
        replace_snapshot=True,
    )

    last_test_run = ArtifactRun(
        id=uuid4(),
        revision_id=uuid4(),
        tenant_id=tenant.id,
        domain=ArtifactRunDomain.TEST,
        status=ArtifactRunStatus.COMPLETED,
        queue_class="artifact_test",
        sandbox_backend="cloudflare_workers",
        result_payload={"ok": True},
        runtime_metadata={"worker_name": "cf-worker"},
    )

    state = runtime.serialize_runtime_state(
        session=prepared.session,
        shared_draft=prepared.shared_draft,
        artifact=None,
        run=None,
        last_test_run=last_test_run,
    )

    assert state["persistence_readiness"] == {
        "ready": True,
        "mode": "create",
        "missing_fields": [],
    }
    assert state["verification_state"] == {
        "has_test_run": True,
        "latest_test_run_id": str(last_test_run.id),
        "latest_test_status": "completed",
        "latest_test_terminal": True,
        "latest_test_successful": True,
        "result_payload": {"ok": True},
        "error_payload": {},
        "runtime_metadata": {"worker_name": "cf-worker"},
    }


@pytest.mark.asyncio
async def test_continue_prompt_run_uses_session_history_and_persists_orchestrator_turn(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    runtime = ArtifactCodingRuntimeService(db_session)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)
    prepared = await runtime.prepare_session(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        title_prompt="Start native continuation test",
        artifact_id=None,
        draft_key=None,
        chat_session_id=None,
        draft_snapshot=runtime.build_initial_snapshot_from_seed({"kind": "tool_impl"}),
        replace_snapshot=True,
    )
    initial_run = AgentRun(
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        initiator_user_id=user.id,
        thread_id=prepared.session.agent_thread_id,
        status=RunStatus.completed,
        input_params={"context": {"thread_id": str(prepared.session.agent_thread_id)}},
        output_result={"final_output": "Initial worker response"},
    )
    db_session.add(initial_run)
    await db_session.flush()
    await runtime.history.mark_run_started(session=prepared.session, run_id=initial_run.id)
    await runtime.history.persist_user_message(
        session_id=prepared.session.id,
        run_id=initial_run.id,
        content="Initial human request",
    )
    await runtime.history.persist_assistant_message(
        session_id=prepared.session.id,
        run_id=initial_run.id,
        content="Initial assistant reply",
    )
    await db_session.commit()

    captured: dict[str, object] = {}
    continued_run_id = uuid4()

    async def fake_start_run(self, *, agent_id, input_params, user_id, background, mode, requested_scopes, thread_id, **kwargs):
        del self, mode, requested_scopes, kwargs
        captured["agent_id"] = str(agent_id)
        captured["input_params"] = input_params
        captured["background"] = background
        captured["thread_id"] = str(thread_id)
        run = AgentRun(
            id=continued_run_id,
            tenant_id=tenant.id,
            agent_id=agent_id,
            user_id=user_id,
            initiator_user_id=user_id,
            thread_id=thread_id,
            status=RunStatus.queued,
            input_params=input_params,
            output_result=None,
        )
        db_session.add(run)
        await db_session.flush()
        return continued_run_id

    monkeypatch.setattr("app.services.artifact_coding_runtime_service.AgentExecutorService.start_run", fake_start_run)

    session, shared_draft, run = await runtime.continue_prompt_run(
        tenant_id=tenant.id,
        user_id=user.id,
        chat_session_id=prepared.session.id,
        orchestrator_prompt="Set slug to native-continuation and add README.md",
        model_id=None,
    )

    assert session.id == prepared.session.id
    assert shared_draft.id == prepared.shared_draft.id
    assert run.id == continued_run_id
    assert captured["background"] is True
    assert captured["thread_id"] == str(prepared.session.agent_thread_id)
    assert captured["input_params"]["messages"] == [
        {"role": "user", "content": "Initial human request"},
        {"role": "assistant", "content": "Initial assistant reply"},
        {"role": "system", "content": "Set slug to native-continuation and add README.md"},
    ]

    messages = await ArtifactCodingChatHistoryService(db_session).list_messages_page(session_id=prepared.session.id, limit=10)
    serialized = [item.role for item in messages[0]]
    assert "orchestrator" in serialized


@pytest.mark.asyncio
async def test_artifact_coding_agent_profile_includes_delegated_worker_mode_instructions(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)

    node = next(
        item
        for item in agent.graph_definition["nodes"]
        if item.get("id") == "artifact_coding_agent"
    )
    instructions = node["config"]["instructions"]

    assert "architect_worker_task" in instructions
    assert "delegated worker" in instructions
    assert "complete the requested objective autonomously" in instructions
    assert "BLOCKING QUESTION:" in instructions
    assert "artifact_coding_await_last_test_result" in instructions
    assert "queued or running" in instructions
    assert "Artifacts may use either python or javascript language lanes." in instructions
    assert "Language is selected during create flow and must not be changed after the artifact has been persisted." in instructions
    assert "Use artifact_coding_list_credentials when you need to reference an existing credential." in instructions
    assert "Credential references must use exact string literals of the form @{credential-id}." in instructions
    assert "If the current locked session is already bound to an existing persisted artifact and the request implies a new artifact or a different language" in instructions
    assert "outside the current artifact scope and cannot be completed from this chat" in instructions
    assert "Do not tell the caller to open another session, create another artifact, or continue elsewhere" in instructions
    assert "Do not emit scaffolds, suggested source files, or workflow steps by default when refusing for scope conflict." in instructions
    assert "display_name, kind, language, source_files, entry_module_path, runtime_target, capabilities, config_schema" in instructions
    assert "exactly one kind-matching contract object via the matching contract tool" in instructions
    assert "entry_module_path points to a real file in source_files" in instructions
    assert "kind=tool_impl" in instructions
    assert "Tool identity, binding, and publish pinning are separate follow-up lifecycle steps" in instructions
    assert "Use artifact_coding_set_metadata for display_name and description only." in instructions
    assert "artifact_coding_set_tool_contract" in instructions
    assert "Do not wrap it inside agent_contract, rag_contract, or tool_contract keys." in instructions
    assert "Do not place metadata fields like display_name or description inside contract objects." in instructions


@pytest.mark.asyncio
async def test_artifact_coding_tools_publish_kind_specific_contract_tool_schemas(db_session):
    await ensure_artifact_coding_tools(db_session)

    tool = await db_session.scalar(
        select(ToolRegistry).where(ToolRegistry.slug == "artifact-coding-set-tool-contract")
    )

    assert tool is not None
    assert tool.schema["input"]["required"] == ["tool_contract"]
    assert "contract_payload" not in tool.schema["input"]["properties"]
    assert "tool_contract" in tool.schema["input"]["properties"]
    tool_contract_schema = tool.schema["input"]["properties"]["tool_contract"]
    assert "input_schema" in tool_contract_schema["properties"]
    assert "output_schema" in tool_contract_schema["properties"]
    assert "description" not in tool_contract_schema["properties"]


@pytest.mark.asyncio
async def test_artifact_coding_set_tool_contract_accepts_inner_contract_object(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)
    runtime = ArtifactCodingRuntimeService(db_session)
    prepared = await runtime.prepare_session(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        title_prompt="Set tool contract",
        artifact_id=None,
        draft_key=None,
        chat_session_id=None,
        draft_snapshot=runtime.build_initial_snapshot_from_seed({"kind": "tool_impl"}),
        replace_snapshot=True,
    )
    worker_run = await _create_artifact_coding_worker_run(
        db_session,
        tenant=tenant,
        user=user,
        agent=agent,
        session=prepared.session,
        shared_draft=prepared.shared_draft,
    )

    @asynccontextmanager
    async def _session_override():
        yield db_session

    from app.services import artifact_coding_agent_tools as artifact_tools_module

    original_session = artifact_tools_module.get_session
    artifact_tools_module.get_session = _session_override
    try:
        result = await artifact_coding_set_tool_contract(
            {
                "run_id": str(worker_run.id),
                "tool_contract": {
                    "input_schema": {"type": "object", "properties": {"deal_id": {"type": "integer"}}},
                    "output_schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
                    "side_effects": [],
                    "execution_mode": "interactive",
                    "tool_ui": {},
                },
            }
        )
    finally:
        artifact_tools_module.get_session = original_session

    assert result["ok"] is True
    assert result["changed_fields"] == ["tool_contract"]
    assert '"deal_id"' in result["draft_snapshot"]["tool_contract"]


@pytest.mark.asyncio
async def test_artifact_coding_list_credentials_returns_safe_metadata_only(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)
    runtime = ArtifactCodingRuntimeService(db_session)
    prepared = await runtime.prepare_session(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        title_prompt="Credential listing",
        artifact_id=None,
        draft_key=None,
        chat_session_id=None,
        draft_snapshot=runtime.build_initial_snapshot_from_seed({"kind": "tool_impl"}),
        replace_snapshot=True,
    )
    worker_run = await _create_artifact_coding_worker_run(
        db_session,
        tenant=tenant,
        user=user,
        agent=agent,
        session=prepared.session,
        shared_draft=prepared.shared_draft,
    )
    db_session.add(
        IntegrationCredential(
            tenant_id=tenant.id,
            category=IntegrationCredentialCategory.TOOL_PROVIDER,
            provider_key="search_api",
            provider_variant=None,
            display_name="Search API Key",
            credentials={"api_key": "super-secret"},
            is_enabled=True,
            is_default=False,
        )
    )
    await db_session.commit()

    @asynccontextmanager
    async def _session_override():
        yield db_session

    from app.services import artifact_coding_agent_tools as artifact_tools_module

    original_session = artifact_tools_module.get_session
    artifact_tools_module.get_session = _session_override
    try:
        result = await artifact_coding_list_credentials({"run_id": str(worker_run.id)})
    finally:
        artifact_tools_module.get_session = original_session

    assert result["credentials"] == [
        {
            "id": result["credentials"][0]["id"],
            "name": "Search API Key",
            "category": "tool_provider",
        }
    ]
    assert "credentials" in result
    assert "super-secret" not in str(result)


@pytest.mark.asyncio
async def test_artifact_coding_set_entry_module_rejects_language_mismatch(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)
    runtime = ArtifactCodingRuntimeService(db_session)
    prepared = await runtime.prepare_session(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        title_prompt="Reject mismatched entry module",
        artifact_id=None,
        draft_key=None,
        chat_session_id=None,
        draft_snapshot=runtime.build_initial_snapshot_from_seed({"kind": "tool_impl", "language": "python"}),
        replace_snapshot=True,
    )
    worker_run = await _create_artifact_coding_worker_run(
        db_session,
        tenant=tenant,
        user=user,
        agent=agent,
        session=prepared.session,
        shared_draft=prepared.shared_draft,
    )

    @asynccontextmanager
    async def _session_override():
        yield db_session

    from app.services import artifact_coding_agent_tools as artifact_tools_module

    original_session = artifact_tools_module.get_session
    artifact_tools_module.get_session = _session_override
    try:
        await artifact_coding_create_file(
            {"run_id": str(worker_run.id), "path": "main.js", "content": "export async function execute() { return {}; }\n"}
        )
        with pytest.raises(ValueError, match="not compatible with artifact language"):
            await artifact_coding_set_entry_module({"run_id": str(worker_run.id), "path": "main.js"})
    finally:
        artifact_tools_module.get_session = original_session


@pytest.mark.asyncio
async def test_artifact_coding_run_test_rejects_duplicate_active_test_run(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)
    runtime = ArtifactCodingRuntimeService(db_session)
    prepared = await runtime.prepare_session(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        title_prompt="Duplicate active test run guard",
        artifact_id=None,
        draft_key=None,
        chat_session_id=None,
        draft_snapshot=runtime.build_initial_snapshot_from_seed({"kind": "tool_impl"}),
        replace_snapshot=True,
    )
    worker_run = await _create_artifact_coding_worker_run(
        db_session,
        tenant=tenant,
        user=user,
        agent=agent,
        session=prepared.session,
        shared_draft=prepared.shared_draft,
    )
    active_test_run = ArtifactRun(
        tenant_id=tenant.id,
        revision_id=uuid4(),
        artifact_id=None,
        domain=ArtifactRunDomain.TEST,
        status=ArtifactRunStatus.QUEUED,
        queue_class="artifact_test",
        sandbox_backend="cloudflare_workers",
        input_payload={},
        config_payload={},
        context_payload={},
        runtime_metadata={},
    )
    db_session.add(active_test_run)
    await db_session.flush()
    prepared.shared_draft.last_test_run_id = active_test_run.id
    await db_session.commit()

    @asynccontextmanager
    async def _session_override():
        yield db_session

    monkeypatch.setattr(
        "app.services.artifact_coding_agent_test_tools.get_session",
        _session_override,
    )

    with pytest.raises(ValueError, match="TEST_RUN_ALREADY_ACTIVE"):
        await artifact_coding_run_test({"run_id": str(worker_run.id)})


@pytest.mark.asyncio
async def test_artifact_coding_await_last_test_result_waits_for_terminal_state(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)
    runtime = ArtifactCodingRuntimeService(db_session)
    prepared = await runtime.prepare_session(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        title_prompt="Await terminal artifact test result",
        artifact_id=None,
        draft_key=None,
        chat_session_id=None,
        draft_snapshot=runtime.build_initial_snapshot_from_seed({"kind": "tool_impl"}),
        replace_snapshot=True,
    )
    worker_run = await _create_artifact_coding_worker_run(
        db_session,
        tenant=tenant,
        user=user,
        agent=agent,
        session=prepared.session,
        shared_draft=prepared.shared_draft,
    )
    queued_test_run = ArtifactRun(
        tenant_id=tenant.id,
        revision_id=uuid4(),
        artifact_id=None,
        domain=ArtifactRunDomain.TEST,
        status=ArtifactRunStatus.QUEUED,
        queue_class="artifact_test",
        sandbox_backend="cloudflare_workers",
        input_payload={},
        config_payload={},
        context_payload={},
        runtime_metadata={},
    )
    db_session.add(queued_test_run)
    await db_session.flush()
    prepared.shared_draft.last_test_run_id = queued_test_run.id
    await db_session.commit()

    @asynccontextmanager
    async def _session_override():
        yield db_session

    async def _fake_wait_for_terminal_state(self, run_id, *, timeout_seconds=30.0):
        del self, timeout_seconds
        run = await db_session.get(ArtifactRun, run_id)
        run.status = ArtifactRunStatus.COMPLETED
        run.result_payload = {"passed": True}
        run.runtime_metadata = {"waited": True}
        await db_session.flush()
        return run

    monkeypatch.setattr(
        "app.services.artifact_coding_agent_test_tools.get_session",
        _session_override,
    )
    monkeypatch.setattr(
        "app.services.artifact_coding_agent_test_tools.ArtifactExecutionService.wait_for_terminal_state",
        _fake_wait_for_terminal_state,
    )

    result = await artifact_coding_await_last_test_result(
        {"run_id": str(worker_run.id), "timeout_seconds": 120}
    )

    assert result["has_test_result"] is True
    assert result["test_run_id"] == str(queued_test_run.id)
    assert result["status"] == "completed"
    assert result["is_terminal"] is True
    assert result["wait_timed_out"] is False
    assert result["result_payload"] == {"passed": True}


@pytest.mark.asyncio
async def test_artifact_coding_get_last_test_result_includes_ordered_events(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)
    runtime = ArtifactCodingRuntimeService(db_session)
    prepared = await runtime.prepare_session(
        tenant_id=tenant.id,
        user_id=user.id,
        agent_id=agent.id,
        title_prompt="Get artifact test event trail",
        artifact_id=None,
        draft_key=None,
        chat_session_id=None,
        draft_snapshot=runtime.build_initial_snapshot_from_seed({"kind": "tool_impl"}),
        replace_snapshot=True,
    )
    worker_run = await _create_artifact_coding_worker_run(
        db_session,
        tenant=tenant,
        user=user,
        agent=agent,
        session=prepared.session,
        shared_draft=prepared.shared_draft,
    )
    failed_test_run = ArtifactRun(
        tenant_id=tenant.id,
        revision_id=uuid4(),
        artifact_id=None,
        domain=ArtifactRunDomain.TEST,
        status=ArtifactRunStatus.FAILED,
        queue_class="artifact_test",
        sandbox_backend="cloudflare_workers",
        input_payload={},
        config_payload={},
        context_payload={},
        error_payload={"message": "worker crashed", "code": "CLOUDFLARE_DISPATCH_HTTP_ERROR"},
        runtime_metadata={"worker_name": "cf-worker"},
    )
    db_session.add(failed_test_run)
    await db_session.flush()
    db_session.add_all(
        [
            ArtifactRunEvent(
                run_id=failed_test_run.id,
                sequence=1,
                event_type="dispatch_started",
                payload={"data": {"worker_name": "cf-worker"}},
            ),
            ArtifactRunEvent(
                run_id=failed_test_run.id,
                sequence=2,
                event_type="dispatch_finished",
                payload={"data": {"status": "failed"}},
            ),
        ]
    )
    prepared.shared_draft.last_test_run_id = failed_test_run.id
    await db_session.commit()

    @asynccontextmanager
    async def _session_override():
        yield db_session

    monkeypatch.setattr(
        "app.services.artifact_coding_agent_test_tools.get_session",
        _session_override,
    )

    from app.services.artifact_coding_agent_test_tools import artifact_coding_get_last_test_result

    result = await artifact_coding_get_last_test_result({"run_id": str(worker_run.id)})

    assert result["has_test_result"] is True
    assert result["status"] == "failed"
    assert result["failure_summary"] == "worker crashed"
    assert result["event_count"] == 2
    assert [event["event_type"] for event in result["events"]] == [
        "dispatch_started",
        "dispatch_finished",
    ]


@pytest.mark.asyncio
async def test_architect_artifact_coding_tools_return_hydrated_state_and_canonical_export_payloads(db_session, monkeypatch):
    tenant, user = await _seed_tenant_and_user(db_session)
    artifact = await _create_artifact_from_payload(
        db_session,
        tenant_id=tenant.id,
        user_id=user.id,
        payload=_tool_impl_create_payload("hydrated-tool"),
    )
    seeded_agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)

    async def _return_seeded_agent(_db, _tenant_id, *, actor_user_id=None):
        return seeded_agent

    monkeypatch.setattr(
        "app.services.platform_architect_worker_bindings.ensure_artifact_coding_agent_profile",
        _return_seeded_agent,
    )

    @asynccontextmanager
    async def _session_override():
        yield db_session

    monkeypatch.setattr(
        "app.services.platform_architect_worker_tools.get_session",
        _session_override,
    )

    prepared = await architect_worker_binding_prepare(
        {
            "binding_type": "artifact_shared_draft",
            "prepare_mode": "attach_existing_artifact",
            "artifact_id": str(artifact.id),
            "__tool_runtime_context__": {
                "tenant_id": str(tenant.id),
                "user_id": str(user.id),
                "run_id": str(uuid4()),
            },
        }
    )

    assert prepared["binding_ref"]["binding_type"] == "artifact_shared_draft"
    assert prepared["binding_state"]["artifact_id"] == str(artifact.id)
    assert prepared["binding_state"]["draft_snapshot"]["display_name"] == "hydrated-tool-display"
    assert prepared["binding_state"]["draft_snapshot"]["source_files"][0]["path"] == "main.py"
    assert prepared["binding_state"]["platform_assets_create_input"] is None

    state = await architect_worker_binding_get_state(
        {
            "binding_ref": prepared["binding_ref"],
            "__tool_runtime_context__": {
                "tenant_id": str(tenant.id),
                "user_id": str(user.id),
                "run_id": str(uuid4()),
            },
        }
    )

    assert state["binding_state"]["artifact_id"] == str(artifact.id)
    assert state["binding_state"]["platform_assets_create_input"] is None
    assert state["binding_state"]["platform_assets_update_input"]["action"] == "artifacts.update"
    assert state["binding_state"]["platform_assets_update_input"]["payload"]["artifact_id"] == str(artifact.id)
    assert state["binding_state"]["platform_assets_update_input"]["payload"]["patch"]["runtime"]["entry_module_path"] == "main.py"
