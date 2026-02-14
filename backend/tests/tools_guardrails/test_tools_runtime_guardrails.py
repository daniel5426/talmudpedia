from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.agent.resolution import ResolutionError, ToolResolver
from app.core.security import create_access_token
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.registry import (
    ToolDefinitionScope,
    ToolImplementationType,
    ToolRegistry,
    ToolStatus,
)


@pytest.fixture(autouse=True)
def _enable_builtin_tools(monkeypatch):
    monkeypatch.setenv("BUILTIN_TOOLS_V1", "1")


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


async def _seed_tool(db_session, *, tenant_id, status: ToolStatus = ToolStatus.DRAFT) -> ToolRegistry:
    tool = ToolRegistry(
        tenant_id=tenant_id,
        name=f"runtime-guard-tool-{uuid4().hex[:6]}",
        slug=f"runtime-guard-tool-{uuid4().hex[:8]}",
        description="runtime guard",
        scope=ToolDefinitionScope.TENANT,
        schema={"input": {"type": "object"}, "output": {"type": "object"}},
        config_schema={"implementation": {"type": "http", "url": "https://example.com", "method": "GET"}},
        status=status,
        version="1.0.0",
        implementation_type=ToolImplementationType.HTTP,
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


async def _seed_builtin_template(db_session, builtin_key: str) -> ToolRegistry:
    existing = (
        await db_session.execute(
            select(ToolRegistry).where(
                ToolRegistry.tenant_id == None,
                ToolRegistry.builtin_key == builtin_key,
                ToolRegistry.is_builtin_template == True,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    template = ToolRegistry(
        tenant_id=None,
        name=f"Builtin {builtin_key}",
        slug=f"builtin-template-{builtin_key}-{uuid4().hex[:8]}",
        description="builtin template",
        scope=ToolDefinitionScope.GLOBAL,
        schema={"input": {"type": "object"}, "output": {"type": "object"}},
        config_schema={"implementation": {"type": "http", "url": "https://example.com", "method": "GET"}},
        status=ToolStatus.PUBLISHED,
        version="1.0.0",
        implementation_type=ToolImplementationType.HTTP,
        builtin_key=builtin_key,
        builtin_template_id=None,
        is_builtin_template=True,
        is_active=True,
        is_system=True,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


@pytest.mark.asyncio
async def test_tool_resolver_can_require_published(db_session):
    tenant, _user = await _seed_tenant_and_user(db_session)
    tool = await _seed_tool(db_session, tenant_id=tenant.id, status=ToolStatus.DRAFT)

    resolver = ToolResolver(db_session, tenant.id)

    resolved = await resolver.resolve(tool.id, require_published=False)
    assert resolved["id"] == str(tool.id)

    with pytest.raises(ResolutionError, match="published"):
        await resolver.resolve(tool.id, require_published=True)


@pytest.mark.asyncio
async def test_removed_builtin_instance_routes_return_404(client, db_session):
    tenant_a, user_a = await _seed_tenant_and_user(db_session)

    key = f"tenant-iso-{uuid4().hex[:8]}"
    await _seed_builtin_template(db_session, key)

    listed = await client.get("/tools/builtins/instances", headers=_headers(user_a, tenant_a))
    assert listed.status_code == 404

    random_tool_id = uuid4()
    denied_patch = await client.patch(
        f"/tools/builtins/instances/{random_tool_id}",
        json={"name": "intrusion"},
        headers=_headers(user_a, tenant_a),
    )
    assert denied_patch.status_code == 404

    denied_publish = await client.post(
        f"/tools/builtins/instances/{random_tool_id}/publish",
        json={},
        headers=_headers(user_a, tenant_a),
    )
    assert denied_publish.status_code == 404
