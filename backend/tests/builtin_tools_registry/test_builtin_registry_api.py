from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.rag import PipelineType, VisualPipeline
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
    user = User(email=f"owner-{suffix}@example.com", role="admin")
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


async def _ensure_builtin_template(
    db_session,
    *,
    builtin_key: str,
    implementation_type: ToolImplementationType,
    implementation: dict,
    execution: dict | None = None,
) -> ToolRegistry:
    existing = (
        await db_session.execute(
            select(ToolRegistry).where(
                ToolRegistry.tenant_id == None,
                ToolRegistry.builtin_key == builtin_key,
            )
        )
    ).scalars().first()
    if existing is not None:
        return existing

    suffix = uuid4().hex[:8]
    template = ToolRegistry(
        tenant_id=None,
        name=f"Template {builtin_key}",
        slug=f"template-{builtin_key}-{suffix}",
        description="unit template",
        scope=ToolDefinitionScope.GLOBAL,
        schema={"input": {"type": "object"}, "output": {"type": "object"}},
        config_schema={"implementation": implementation, "execution": execution or {}},
        status=ToolStatus.PUBLISHED,
        version="1.0.0",
        implementation_type=implementation_type,
        artifact_id=None,
        artifact_version=None,
        builtin_key=builtin_key,
        builtin_template_id=None,
        is_builtin_template=False,
        is_active=True,
        is_system=True,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


async def _seed_retrieval_pipeline(db_session, tenant_id) -> VisualPipeline:
    pipeline = VisualPipeline(
        tenant_id=tenant_id,
        name=f"Retrieval {uuid4().hex[:6]}",
        description="retrieval pipeline",
        nodes=[],
        edges=[],
        pipeline_type=PipelineType.RETRIEVAL,
        is_published=True,
    )
    db_session.add(pipeline)
    await db_session.commit()
    await db_session.refresh(pipeline)
    return pipeline


async def _create_http_tool(client, user: User, tenant: Tenant, slug_suffix: str) -> dict:
    response = await client.post(
        "/tools",
        json={
            "name": f"HTTP Tool {slug_suffix}",
            "slug": f"http-tool-{slug_suffix}",
            "description": "test",
            "input_schema": {"type": "object", "properties": {}},
            "output_schema": {"type": "object", "properties": {}},
            "implementation_type": "HTTP",
            "implementation_config": {"type": "http", "url": "https://example.com", "method": "GET"},
        },
        headers=_headers(user, tenant),
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_tool_dto_exposes_derived_config_and_ownership_metadata(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)

    system_tool = await _ensure_builtin_template(
        db_session,
        builtin_key=f"system_{uuid4().hex[:8]}",
        implementation_type=ToolImplementationType.FUNCTION,
        implementation={"type": "function", "function_name": "echo"},
        execution={"timeout_s": 15},
    )
    manual_tool = await _create_http_tool(client, user, tenant, "dto")

    response = await client.get("/tools", headers=_headers(user, tenant))
    assert response.status_code == 200

    by_id = {item["id"]: item for item in response.json()["tools"]}
    manual_payload = by_id[manual_tool["id"]]
    system_payload = by_id[str(system_tool.id)]

    assert manual_payload["implementation_config"] == {
        "type": "http",
        "url": "https://example.com",
        "method": "GET",
    }
    assert manual_payload["execution_config"] == {}
    assert manual_payload["ownership"] == "manual"
    assert manual_payload["managed_by"] == "tools"
    assert manual_payload["source_object_type"] is None
    assert manual_payload["source_object_id"] is None
    assert manual_payload["can_edit_in_registry"] is True
    assert manual_payload["can_publish_in_registry"] is True
    assert manual_payload["can_delete_in_registry"] is True

    assert system_payload["implementation_config"]["function_name"] == "echo"
    assert system_payload["execution_config"]["timeout_s"] == 15
    assert system_payload["ownership"] == "system"
    assert system_payload["managed_by"] == "system"
    assert system_payload["can_edit_in_registry"] is False
    assert system_payload["can_publish_in_registry"] is False
    assert system_payload["can_delete_in_registry"] is False


@pytest.mark.asyncio
async def test_list_builtin_templates_returns_only_global_templates(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)

    key = f"unit_list_{uuid4().hex[:8]}"
    template = await _ensure_builtin_template(
        db_session,
        builtin_key=key,
        implementation_type=ToolImplementationType.HTTP,
        implementation={"type": "http", "url": "https://example.com", "method": "GET"},
    )

    instance = ToolRegistry(
        tenant_id=tenant.id,
        name="Tenant Builtin Instance",
        slug=f"tenant-builtin-instance-{uuid4().hex[:8]}",
        description="instance",
        scope=ToolDefinitionScope.TENANT,
        schema={"input": {"type": "object"}, "output": {"type": "object"}},
        config_schema={"implementation": {"type": "http", "url": "https://tenant.example.com", "method": "GET"}},
        status=ToolStatus.DRAFT,
        version="1.0.0",
        implementation_type=ToolImplementationType.HTTP,
        builtin_key=key,
        builtin_template_id=template.id,
        is_builtin_template=False,
        is_active=True,
        is_system=False,
    )
    db_session.add(instance)
    await db_session.commit()

    response = await client.get("/tools/builtins/templates", headers=_headers(user, tenant))
    assert response.status_code == 200

    body = response.json()
    ids = {item["id"] for item in body["tools"]}
    assert str(template.id) in ids
    assert str(instance.id) not in ids
    assert all(item["is_builtin_template"] is False for item in body["tools"])
    assert all(item["tenant_id"] is None for item in body["tools"])

    tools_response = await client.get("/tools", headers=_headers(user, tenant))
    assert tools_response.status_code == 200
    listed_ids = {item["id"] for item in tools_response.json()["tools"]}
    assert str(template.id) in listed_ids
    assert str(instance.id) not in listed_ids


@pytest.mark.asyncio
async def test_builtin_instance_endpoints_removed_return_404(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    key = f"removed_{uuid4().hex[:8]}"
    await _ensure_builtin_template(
        db_session,
        builtin_key=key,
        implementation_type=ToolImplementationType.HTTP,
        implementation={"type": "http", "url": "https://example.com", "method": "GET"},
    )

    create_resp = await client.post(
        f"/tools/builtins/templates/{key}/instances",
        json={"name": "nope"},
        headers=_headers(user, tenant),
    )
    assert create_resp.status_code == 404

    list_resp = await client.get("/tools/builtins/instances", headers=_headers(user, tenant))
    assert list_resp.status_code == 404

    random_tool_id = uuid4()
    patch_resp = await client.patch(
        f"/tools/builtins/instances/{random_tool_id}",
        json={"name": "still-nope"},
        headers=_headers(user, tenant),
    )
    assert patch_resp.status_code == 404

    publish_resp = await client.post(
        f"/tools/builtins/instances/{random_tool_id}/publish",
        json={},
        headers=_headers(user, tenant),
    )
    assert publish_resp.status_code == 404


@pytest.mark.asyncio
async def test_generic_tool_management_allows_cleanup_of_legacy_builtin_rows(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    key = f"legacy_instance_{uuid4().hex[:8]}"
    template = await _ensure_builtin_template(
        db_session,
        builtin_key=key,
        implementation_type=ToolImplementationType.HTTP,
        implementation={"type": "http", "url": "https://example.com", "method": "GET"},
    )

    instance = ToolRegistry(
        tenant_id=tenant.id,
        name="Legacy Built-in Instance",
        slug=f"legacy-builtin-instance-{uuid4().hex[:8]}",
        description="legacy row",
        scope=ToolDefinitionScope.TENANT,
        schema={"input": {"type": "object"}, "output": {"type": "object"}},
        config_schema={"implementation": {"type": "http", "url": "https://tenant.example.com", "method": "GET"}},
        status=ToolStatus.DRAFT,
        version="1.0.0",
        implementation_type=ToolImplementationType.HTTP,
        builtin_key=key,
        builtin_template_id=template.id,
        is_builtin_template=False,
        is_active=True,
        is_system=False,
    )
    db_session.add(instance)
    await db_session.commit()

    update_resp = await client.put(
        f"/tools/{instance.id}",
        json={"description": "updated"},
        headers=_headers(user, tenant),
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["description"] == "updated"

    delete_resp = await client.delete(
        f"/tools/{instance.id}",
        headers=_headers(user, tenant),
    )
    assert delete_resp.status_code == 200


@pytest.mark.asyncio
async def test_rag_pipeline_registry_create_is_rejected_as_domain_owned(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    pipeline = await _seed_retrieval_pipeline(db_session, tenant.id)

    response = await client.post(
        "/tools",
        json={
            "name": "invalid retrieval",
            "slug": f"invalid-retrieval-{uuid4().hex[:8]}",
            "description": "invalid",
            "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
            "output_schema": {"type": "object", "properties": {"results": {"type": "array"}}},
            "implementation_type": "RAG_PIPELINE",
            "implementation_config": {"type": "rag_pipeline", "pipeline_id": str(pipeline.id)},
        },
        headers=_headers(user, tenant),
    )
    assert response.status_code == 400
    assert "domain-owned" in response.json()["detail"]


@pytest.mark.asyncio
async def test_pipeline_bound_tool_row_rejects_registry_update(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    pipeline = await _seed_retrieval_pipeline(db_session, tenant.id)

    tool = ToolRegistry(
        tenant_id=tenant.id,
        name=f"pipeline-bound-{uuid4().hex[:6]}",
        slug=f"pipeline-bound-{uuid4().hex[:8]}",
        description="managed row",
        scope=ToolDefinitionScope.TENANT,
        schema={"input": {"type": "object"}, "output": {"type": "object"}},
        config_schema={"implementation": {"type": "rag_pipeline", "pipeline_id": str(pipeline.id)}},
        status=ToolStatus.DRAFT,
        version="1.0.0",
        implementation_type=ToolImplementationType.RAG_PIPELINE,
        visual_pipeline_id=pipeline.id,
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)

    update = await client.put(
        f"/tools/{tool.id}",
        json={"description": "should fail"},
        headers=_headers(user, tenant),
    )
    assert update.status_code == 400
    assert "managed by its owning artifact or pipeline" in update.json()["detail"]


@pytest.mark.asyncio
async def test_publish_pipeline_bound_tool_from_registry_is_rejected(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    pipeline = await _seed_retrieval_pipeline(db_session, tenant.id)

    tool = ToolRegistry(
        tenant_id=tenant.id,
        name=f"invalid-publish-{uuid4().hex[:6]}",
        slug=f"invalid-publish-{uuid4().hex[:8]}",
        description="invalid publish",
        scope=ToolDefinitionScope.TENANT,
        schema={"input": {"type": "object"}, "output": {"type": "object"}},
        config_schema={"implementation": {"type": "rag_pipeline", "pipeline_id": str(pipeline.id)}},
        status=ToolStatus.DRAFT,
        version="1.0.0",
        implementation_type=ToolImplementationType.RAG_PIPELINE,
        visual_pipeline_id=pipeline.id,
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)

    publish_response = await client.post(
        f"/tools/{tool.id}/publish",
        json={},
        headers=_headers(user, tenant),
    )
    assert publish_response.status_code == 400
    assert "owning artifact or pipeline" in publish_response.json()["detail"]


@pytest.mark.asyncio
async def test_pipeline_bound_tool_row_reports_managed_metadata(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)
    pipeline = await _seed_retrieval_pipeline(db_session, tenant.id)

    tool = ToolRegistry(
        tenant_id=tenant.id,
        name=f"pipeline-metadata-{uuid4().hex[:6]}",
        slug=f"pipeline-metadata-{uuid4().hex[:8]}",
        description="managed metadata",
        scope=ToolDefinitionScope.TENANT,
        schema={"input": {"type": "object"}, "output": {"type": "object"}},
        config_schema={
            "implementation": {"type": "rag_pipeline", "pipeline_id": str(pipeline.id)},
            "execution": {"timeout_s": 30},
        },
        status=ToolStatus.DRAFT,
        version="1.0.0",
        implementation_type=ToolImplementationType.RAG_PIPELINE,
        visual_pipeline_id=pipeline.id,
        is_active=True,
        is_system=False,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)

    response = await client.get(f"/tools/{tool.id}", headers=_headers(user, tenant))
    assert response.status_code == 200
    body = response.json()
    assert body["ownership"] == "pipeline_bound"
    assert body["managed_by"] == "pipelines"
    assert body["source_object_type"] == "pipeline"
    assert body["source_object_id"] == str(pipeline.id)
    assert body["implementation_config"]["pipeline_id"] == str(pipeline.id)
    assert body["execution_config"]["timeout_s"] == 30
    assert body["can_edit_in_registry"] is False
    assert body["can_publish_in_registry"] is False
    assert body["can_delete_in_registry"] is False
