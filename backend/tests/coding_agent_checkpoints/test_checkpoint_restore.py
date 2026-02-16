from uuid import UUID, uuid4

import pytest

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeService
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


async def _create_app_and_draft_revision(client, headers: dict[str, str], agent_id: str) -> tuple[str, str]:
    create_resp = await client.post(
        "/admin/apps",
        headers=headers,
        json={
            "name": "Coding Agent Checkpoint App",
            "agent_id": agent_id,
            "template_key": "chat-classic",
            "auth_enabled": True,
            "auth_providers": ["password"],
        },
    )
    assert create_resp.status_code == 200
    app_id = create_resp.json()["id"]

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    draft_revision_id = state_resp.json()["current_draft_revision"]["id"]
    return app_id, draft_revision_id


async def _insert_checkpointed_run(
    db_session,
    *,
    tenant_id,
    agent_id,
    user_id,
    app_id: str,
    base_revision_id: str,
    checkpoint_revision_id: str,
) -> AgentRun:
    run = AgentRun(
        tenant_id=tenant_id,
        agent_id=agent_id,
        user_id=user_id,
        initiator_user_id=user_id,
        status=RunStatus.completed,
        input_params={"input": "checkpoint"},
        surface=CODING_AGENT_SURFACE,
        published_app_id=UUID(app_id),
        base_revision_id=UUID(base_revision_id),
        result_revision_id=UUID(base_revision_id),
        checkpoint_revision_id=UUID(checkpoint_revision_id),
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


@pytest.mark.asyncio
async def test_coding_agent_checkpoints_list_and_restore(client, db_session, monkeypatch):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, draft_revision_id = await _create_app_and_draft_revision(client, headers, str(agent.id))

    async def _fake_sync_session(self, *, app, revision, user_id, files, entry_file):
        return None

    monkeypatch.setattr(PublishedAppDraftDevRuntimeService, "sync_session", _fake_sync_session)

    run = await _insert_checkpointed_run(
        db_session,
        tenant_id=tenant.id,
        agent_id=agent.id,
        user_id=user.id,
        app_id=app_id,
        base_revision_id=draft_revision_id,
        checkpoint_revision_id=draft_revision_id,
    )

    checkpoints_resp = await client.get(f"/admin/apps/{app_id}/coding-agent/checkpoints?limit=10", headers=headers)
    assert checkpoints_resp.status_code == 200
    checkpoints = checkpoints_resp.json()
    assert checkpoints
    checkpoint = checkpoints[0]
    assert checkpoint["checkpoint_id"] == draft_revision_id
    assert checkpoint["run_id"] == str(run.id)

    restore_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/checkpoints/{draft_revision_id}/restore",
        headers=headers,
        json={"run_id": str(run.id)},
    )
    assert restore_resp.status_code == 200
    restore_payload = restore_resp.json()
    restored_revision_id = restore_payload["revision"]["id"]
    assert restore_payload["checkpoint_id"] == draft_revision_id
    assert restore_payload["run_id"] == str(run.id)
    assert restored_revision_id != draft_revision_id

    state_resp = await client.get(f"/admin/apps/{app_id}/builder/state", headers=headers)
    assert state_resp.status_code == 200
    assert state_resp.json()["current_draft_revision"]["id"] == restored_revision_id

    await db_session.refresh(run)
    assert str(run.result_revision_id) == restored_revision_id
    assert str(run.checkpoint_revision_id) == draft_revision_id


@pytest.mark.asyncio
async def test_coding_agent_restore_checkpoint_not_found(client, db_session):
    tenant, user, org_unit, agent = await seed_admin_tenant_and_agent(db_session)
    headers = admin_headers(str(user.id), str(tenant.id), str(org_unit.id))
    app_id, _ = await _create_app_and_draft_revision(client, headers, str(agent.id))

    missing_checkpoint_id = str(uuid4())
    restore_resp = await client.post(
        f"/admin/apps/{app_id}/coding-agent/checkpoints/{missing_checkpoint_id}/restore",
        headers=headers,
        json={},
    )
    assert restore_resp.status_code == 404
