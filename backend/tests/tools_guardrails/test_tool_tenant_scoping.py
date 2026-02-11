from uuid import uuid4

import pytest

from app.agent.executors.tool import ToolNodeExecutor
from app.agent.resolution import ResolutionError, ToolResolver
from app.db.postgres.models.identity import Tenant
from app.db.postgres.models.registry import (
    ToolDefinitionScope,
    ToolImplementationType,
    ToolRegistry,
    ToolStatus,
)


async def _seed_tenant(db_session, prefix: str) -> Tenant:
    tenant = Tenant(name=f"Tenant {prefix}", slug=f"tenant-{prefix}-{uuid4().hex[:6]}")
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


async def _seed_tool(db_session, *, tenant_id, scope: ToolDefinitionScope, slug_prefix: str) -> ToolRegistry:
    suffix = uuid4().hex[:8]
    tool = ToolRegistry(
        tenant_id=tenant_id,
        name=f"{slug_prefix}-tool-{suffix}",
        slug=f"{slug_prefix}-tool-{suffix}",
        description="tenant scoping test tool",
        scope=scope,
        schema={"input": {"type": "object"}, "output": {"type": "object"}},
        config_schema={"implementation": {"type": "http", "method": "POST", "url": "https://example.com/tool"}},
        status=ToolStatus.PUBLISHED,
        implementation_type=ToolImplementationType.HTTP,
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


@pytest.mark.asyncio
async def test_tool_resolver_enforces_tenant_scope(db_session):
    tenant_a = await _seed_tenant(db_session, "a")
    tenant_b = await _seed_tenant(db_session, "b")

    tenant_b_tool = await _seed_tool(
        db_session,
        tenant_id=tenant_b.id,
        scope=ToolDefinitionScope.TENANT,
        slug_prefix="tenant-b",
    )
    global_tool = await _seed_tool(
        db_session,
        tenant_id=None,
        scope=ToolDefinitionScope.GLOBAL,
        slug_prefix="global",
    )

    resolver = ToolResolver(db_session, tenant_a.id)

    with pytest.raises(ResolutionError):
        await resolver.resolve(tenant_b_tool.id)

    resolved = await resolver.resolve(global_tool.id)
    assert resolved["id"] == str(global_tool.id)


@pytest.mark.asyncio
async def test_tool_executor_enforces_tenant_scope(db_session, monkeypatch):
    tenant_a = await _seed_tenant(db_session, "exec-a")
    tenant_b = await _seed_tenant(db_session, "exec-b")

    tenant_b_tool = await _seed_tool(
        db_session,
        tenant_id=tenant_b.id,
        scope=ToolDefinitionScope.TENANT,
        slug_prefix="exec-tenant-b",
    )
    global_tool = await _seed_tool(
        db_session,
        tenant_id=None,
        scope=ToolDefinitionScope.GLOBAL,
        slug_prefix="exec-global",
    )

    async def has_columns(_self):
        return True

    async def fake_http_tool(_self, _tool, input_data, _implementation_config, _context):
        return {"ok": True, "echo": input_data}

    monkeypatch.setattr(ToolNodeExecutor, "_has_artifact_columns", has_columns)
    monkeypatch.setattr(ToolNodeExecutor, "_execute_http_tool", fake_http_tool)

    executor = ToolNodeExecutor(tenant_id=tenant_a.id, db=db_session)

    with pytest.raises(ValueError, match="not found"):
        await executor.execute(
            state={"context": {"x": 1}},
            config={"tool_id": str(tenant_b_tool.id)},
            context={"node_id": "tool-node"},
        )

    result = await executor.execute(
        state={"context": {"x": 1}},
        config={"tool_id": str(global_tool.id)},
        context={"node_id": "tool-node"},
    )
    assert result["tool_outputs"][0]["ok"] is True
    assert result["context"]["echo"] == {"x": 1}
