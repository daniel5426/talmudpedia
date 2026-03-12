from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.postgres.models.artifact_runtime import ArtifactCodingSharedDraft
from app.db.postgres.models.identity import Tenant, User
from app.services.artifact_coding_agent_profile import ensure_artifact_coding_agent_profile
from app.services.artifact_coding_runtime_service import ArtifactCodingRuntimeService
from app.services.artifact_runtime.revision_service import ArtifactRevisionService
from app.services.platform_architect_artifact_delegation_tools import (
    artifact_coding_session_get_state,
    artifact_coding_session_prepare,
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
    create_payload = initial_state["artifact_create_payload"]
    assert create_payload is not None
    artifact = await _create_artifact_from_payload(db_session, tenant_id=tenant.id, user_id=user.id, payload=create_payload)

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
    assert updated_state["artifact_create_payload"] is None
    assert updated_state["artifact_update_payload"]["artifact_id"] == str(artifact.id)
    assert updated_state["artifact_update_payload"]["patch"]["display_name"] == "Delegated Tool"


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
        "app.services.platform_architect_artifact_delegation_tools.ensure_artifact_coding_agent_profile",
        _return_seeded_agent,
    )

    @asynccontextmanager
    async def _session_override():
        yield db_session

    monkeypatch.setattr(
        "app.services.platform_architect_artifact_delegation_tools.get_session",
        _session_override,
    )

    prepared = await artifact_coding_session_prepare(
        {
            "tenant_id": str(tenant.id),
            "user_id": str(user.id),
            "artifact_id": str(artifact.id),
            "title_prompt": "Review hydrated artifact",
        }
    )

    assert prepared["artifact_id"] == str(artifact.id)
    assert prepared["draft_snapshot"]["display_name"] == "hydrated-tool-display"
    assert prepared["draft_snapshot"]["source_files"][0]["path"] == "main.py"
    assert prepared["artifact_create_payload"] is None

    state = await artifact_coding_session_get_state(
        {
            "tenant_id": str(tenant.id),
            "user_id": str(user.id),
            "chat_session_id": prepared["chat_session_id"],
        }
    )

    assert state["artifact_id"] == str(artifact.id)
    assert state["artifact_create_payload"] is None
    assert state["artifact_update_payload"]["artifact_id"] == str(artifact.id)
    assert state["artifact_update_payload"]["patch"]["runtime"]["entry_module_path"] == "main.py"
