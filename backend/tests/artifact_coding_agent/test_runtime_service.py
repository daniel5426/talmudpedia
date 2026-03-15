from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.postgres.models.artifact_runtime import ArtifactCodingSharedDraft
from app.services.artifact_coding_shared_draft_service import ArtifactCodingSharedDraftService
from app.db.postgres.models.identity import Tenant, User
from app.services.artifact_coding_agent_profile import ensure_artifact_coding_agent_profile
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


def _tool_impl_create_payload(slug: str) -> dict[str, object]:
    return {
        "slug": slug,
        "display_name": f"{slug}-display",
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
        slug=str(payload["slug"]),
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


@pytest.mark.asyncio
async def test_runtime_service_relinks_draft_key_to_saved_artifact_without_new_shared_draft(db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    agent = await ensure_artifact_coding_agent_profile(db_session, tenant.id, actor_user_id=user.id)

    runtime = ArtifactCodingRuntimeService(db_session)
    draft_key = f"draft-{uuid4().hex[:8]}"
    snapshot = {
        "slug": "delegated-tool",
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
            "slug": "seeded-tool",
            "display_name": "Seeded Tool",
            "description": "seed-based initialization",
            "entry_module_path": "src/main.py",
            "runtime_target": "cloudflare_workers",
        }
    )

    assert snapshot["kind"] == "tool_impl"
    assert snapshot["slug"] == "seeded-tool"
    assert snapshot["display_name"] == "Seeded Tool"
    assert snapshot["entry_module_path"] == "src/main.py"
    assert snapshot["source_files"][0]["path"] == "src/main.py"


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
