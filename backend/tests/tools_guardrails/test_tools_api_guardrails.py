from uuid import uuid4

import pytest

from app.core.security import create_access_token
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.registry import (
    ToolDefinitionScope,
    ToolImplementationType,
    ToolRegistry,
    ToolStatus,
    ToolVersion,
)


async def _seed_tenant_and_user(db_session):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"Tenant {suffix}", slug=f"tenant-{suffix}")
    user = User(email=f"owner-{suffix}@example.com", role="user")
    db_session.add_all([tenant, user])
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(user)
    return tenant, user


def _headers(user: User, tenant: Tenant) -> dict[str, str]:
    token = create_access_token(
        subject=str(user.id),
        tenant_id=str(tenant.id),
        org_role="owner",
    )
    return {"Authorization": f"Bearer {token}", "X-Tenant-ID": str(tenant.id)}


async def _seed_tool(db_session, tenant_id):
    suffix = uuid4().hex[:8]
    tool = ToolRegistry(
        tenant_id=tenant_id,
        name=f"Guardrail Tool {suffix}",
        slug=f"guardrail-tool-{suffix}",
        description="guardrail test tool",
        scope=ToolDefinitionScope.TENANT,
        schema={"input": {"type": "object"}, "output": {"type": "object"}},
        config_schema={"implementation": {"type": "http", "url": "https://example.com", "method": "POST"}},
        status=ToolStatus.DRAFT,
        implementation_type=ToolImplementationType.HTTP,
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


@pytest.mark.asyncio
async def test_create_tool_rejects_non_tenant_scope(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)

    payload = {
        "name": "Global Attempt",
        "slug": f"global-attempt-{uuid4().hex[:8]}",
        "description": "should fail",
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "implementation_type": "HTTP",
        "implementation_config": {"type": "http", "method": "POST", "url": "https://example.com"},
        "scope": "global",
    }

    response = await client.post("/tools", json=payload, headers=_headers(user, tenant))

    assert response.status_code == 400
    assert "tenant-scoped" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_tool_rejects_direct_published_status(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)

    payload = {
        "name": "Published Attempt",
        "slug": f"published-attempt-{uuid4().hex[:8]}",
        "description": "should fail",
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "implementation_type": "HTTP",
        "implementation_config": {"type": "http", "method": "POST", "url": "https://example.com"},
        "status": "PUBLISHED",
    }

    response = await client.post("/tools", json=payload, headers=_headers(user, tenant))

    assert response.status_code == 400
    assert "publish endpoint" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_cannot_publish_directly_and_publish_endpoint_still_works(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    tool = await _seed_tool(db_session, tenant.id)
    headers = _headers(user, tenant)

    denied = await client.put(
        f"/tools/{tool.id}",
        json={"status": "PUBLISHED"},
        headers=headers,
    )
    assert denied.status_code == 400
    assert "/publish" in denied.json()["detail"]

    published = await client.post(f"/tools/{tool.id}/publish", json={}, headers=headers)
    assert published.status_code == 200
    body = published.json()
    assert body["status"] == "PUBLISHED"

    versions = (
        await db_session.execute(
            ToolVersion.__table__.select().where(ToolVersion.tool_id == tool.id)
        )
    ).fetchall()
    assert len(versions) == 1
