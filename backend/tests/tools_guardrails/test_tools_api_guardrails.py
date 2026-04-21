from uuid import uuid4

import pytest

from app.api.dependencies import get_current_principal
from app.core.security import create_access_token
from app.db.postgres.models.identity import Organization, User
from app.db.postgres.models.registry import (
    ToolDefinitionScope,
    ToolImplementationType,
    ToolRegistry,
    ToolStatus,
    ToolVersion,
)


async def _seed_tenant_and_user(db_session):
    suffix = uuid4().hex[:8]
    tenant = Organization(name=f"Organization {suffix}", slug=f"tenant-{suffix}")
    user = User(email=f"owner-{suffix}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.commit()
    await db_session.refresh(tenant)
    await db_session.refresh(user)
    return tenant, user


def _headers(user: User, tenant: Organization) -> dict[str, str]:
    token = create_access_token(
        subject=str(user.id),
        organization_id=str(tenant.id),
        org_role="owner",
    )
    return {"Authorization": f"Bearer {token}", "X-Organization-ID": str(tenant.id)}


def _detail_message(response) -> str:
    detail = response.json()["detail"]
    if isinstance(detail, dict):
        return str(detail.get("message") or "")
    return str(detail or "")


async def _override_tools_principal(app, *, tenant: Organization, user: User) -> None:
    async def override_get_current_principal():
        return {
            "type": "user",
            "user": user,
            "user_id": str(user.id),
            "organization_id": str(tenant.id),
            "organization_id": str(tenant.id),
            "scopes": ["tools.read", "tools.write", "*"],
        }

    app.dependency_overrides[get_current_principal] = override_get_current_principal


async def _seed_tool(db_session, organization_id):
    suffix = uuid4().hex[:8]
    tool = ToolRegistry(
        organization_id=organization_id,
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


async def _seed_agent_bound_tool(db_session, organization_id):
    suffix = uuid4().hex[:8]
    tool = ToolRegistry(
        organization_id=organization_id,
        name=f"Agent Bound Tool {suffix}",
        slug=f"agent-tool-{suffix}",
        description="agent-bound tool",
        scope=ToolDefinitionScope.TENANT,
        schema={"input": {"type": "object"}, "output": {"type": "object"}},
        config_schema={"implementation": {"type": "agent_call", "target_agent_id": str(uuid4())}},
        status=ToolStatus.DRAFT,
        implementation_type=ToolImplementationType.AGENT_CALL,
        ownership="agent_bound",
        managed_by="agents",
        source_object_type="agent",
        source_object_id=str(uuid4()),
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
    from main import app
    await _override_tools_principal(app, tenant=tenant, user=user)

    payload = {
        "name": "Global Attempt",
        "description": "should fail",
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "implementation_type": "HTTP",
        "implementation_config": {"type": "http", "method": "POST", "url": "https://example.com"},
        "scope": "global",
    }

    try:
        response = await client.post("/tools", json=payload, headers=_headers(user, tenant))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "tenant-scoped" in _detail_message(response)


@pytest.mark.asyncio
async def test_create_tool_rejects_direct_published_status(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    from main import app
    await _override_tools_principal(app, tenant=tenant, user=user)

    payload = {
        "name": "Published Attempt",
        "description": "should fail",
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "implementation_type": "HTTP",
        "implementation_config": {"type": "http", "method": "POST", "url": "https://example.com"},
        "status": "PUBLISHED",
    }

    try:
        response = await client.post("/tools", json=payload, headers=_headers(user, tenant))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "publish endpoint" in _detail_message(response).lower()


@pytest.mark.asyncio
async def test_create_tool_defaults_execution_validation_mode_to_strict(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    from main import app
    await _override_tools_principal(app, tenant=tenant, user=user)

    payload = {
        "name": "Strict Default",
        "description": "should default",
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "implementation_type": "HTTP",
        "implementation_config": {"type": "http", "method": "POST", "url": "https://example.com"},
    }

    try:
        response = await client.post("/tools", json=payload, headers=_headers(user, tenant))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["execution_config"]["validation_mode"] == "strict"


@pytest.mark.asyncio
async def test_create_tool_rejects_removed_strict_input_schema_flag(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    from main import app
    await _override_tools_principal(app, tenant=tenant, user=user)

    payload = {
        "name": "Legacy Strict Flag",
        "description": "should fail",
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "implementation_type": "HTTP",
        "implementation_config": {"type": "http", "method": "POST", "url": "https://example.com"},
        "execution_config": {"strict_input_schema": True},
    }

    try:
        response = await client.post("/tools", json=payload, headers=_headers(user, tenant))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "validation_mode" in _detail_message(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("implementation_type", ["ARTIFACT", "RAG_PIPELINE"])
async def test_create_tool_rejects_domain_owned_types(client, db_session, implementation_type: str):
    tenant, user = await _seed_tenant_and_user(db_session)
    from main import app
    await _override_tools_principal(app, tenant=tenant, user=user)

    payload = {
        "name": f"{implementation_type} Attempt",
        "description": "should fail",
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {"type": "object", "properties": {}},
        "implementation_type": implementation_type,
        "implementation_config": {"type": implementation_type.lower()},
    }

    try:
        response = await client.post("/tools", json=payload, headers=_headers(user, tenant))
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "domain-owned" in _detail_message(response)


@pytest.mark.asyncio
async def test_update_cannot_publish_directly_and_publish_endpoint_still_works(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    tool = await _seed_tool(db_session, tenant.id)
    headers = _headers(user, tenant)
    from main import app
    await _override_tools_principal(app, tenant=tenant, user=user)

    try:
        denied = await client.put(
            f"/tools/{tool.id}",
            json={"status": "PUBLISHED"},
            headers=headers,
        )
        assert denied.status_code == 422
        assert "/publish" in _detail_message(denied)

        published = await client.post(f"/tools/{tool.id}/publish", json={}, headers=headers)
        assert published.status_code == 200
        body = published.json()
        assert body["status"] == "PUBLISHED"
    finally:
        app.dependency_overrides.clear()
    versions = (
        await db_session.execute(
            ToolVersion.__table__.select().where(ToolVersion.tool_id == tool.id)
        )
    ).fetchall()
    assert len(versions) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path_suffix", "expected_detail"),
    [
        ("put", "", "managed by its owning domain"),
        ("post", "/publish", "owning domain"),
        ("delete", "", "owning domain"),
    ],
)
async def test_agent_bound_tools_reject_registry_lifecycle_actions(client, db_session, method: str, path_suffix: str, expected_detail: str):
    tenant, user = await _seed_tenant_and_user(db_session)
    tool = await _seed_agent_bound_tool(db_session, tenant.id)
    headers = _headers(user, tenant)
    from main import app
    await _override_tools_principal(app, tenant=tenant, user=user)

    try:
        if method == "put":
            response = await client.put(f"/tools/{tool.id}{path_suffix}", json={"name": "nope"}, headers=headers)
        elif method == "post":
            response = await client.post(f"/tools/{tool.id}{path_suffix}", json={}, headers=headers)
        else:
            response = await client.delete(f"/tools/{tool.id}{path_suffix}", headers=headers)
    finally:
        app.dependency_overrides.clear()

    expected_status = 400 if method == "delete" else 422
    assert response.status_code == expected_status
    assert expected_detail in _detail_message(response)
