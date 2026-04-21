from datetime import datetime, timezone

import pytest

from app.db.postgres.models.audit import AuditLog, AuditResult
from app.db.postgres.models.rbac import Action, ActorType, ResourceType
from tests.published_apps._helpers import admin_headers, seed_admin_tenant_and_agent


@pytest.mark.asyncio
async def test_settings_audit_list_count_and_detail(client, db_session):
    tenant, owner, org_unit, _ = await seed_admin_tenant_and_agent(db_session)
    log = AuditLog(
        organization_id=tenant.id,
        org_unit_id=org_unit.id,
        actor_id=owner.id,
        actor_type=ActorType.USER,
        actor_email=owner.email,
        action=Action.READ,
        resource_type=ResourceType.AUDIT,
        resource_id="resource-1",
        resource_name="Resource One",
        result=AuditResult.SUCCESS,
        timestamp=datetime.now(timezone.utc),
        before_state={"old": 1},
        after_state={"new": 2},
    )
    db_session.add(log)
    await db_session.commit()

    headers = admin_headers(str(owner.id), str(tenant.id), str(org_unit.id))

    list_resp = await client.get("/api/settings/audit-logs", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()[0]["resource_id"] == "resource-1"

    count_resp = await client.get("/api/settings/audit-logs/count", headers=headers)
    assert count_resp.status_code == 200
    assert count_resp.json()["count"] == 1

    detail_resp = await client.get(f"/api/settings/audit-logs/{log.id}", headers=headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["before_state"] == {"old": 1}
