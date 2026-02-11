from __future__ import annotations

from uuid import UUID, uuid4

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
    ToolVersion,
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
                ToolRegistry.is_builtin_template == True,
            )
        )
    ).scalar_one_or_none()
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
        is_builtin_template=True,
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
    assert all(item["is_builtin_template"] is True for item in body["tools"])
    assert all(item["tenant_id"] is None for item in body["tools"])


@pytest.mark.asyncio
async def test_create_builtin_instance_enforces_tenant_scope(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)

    key = f"unit_create_{uuid4().hex[:8]}"
    template = await _ensure_builtin_template(
        db_session,
        builtin_key=key,
        implementation_type=ToolImplementationType.HTTP,
        implementation={"type": "http", "url": "https://example.com", "method": "GET"},
    )

    payload = {
        "name": "Tenant HTTP Instance",
        "description": "tenant-specific",
        "implementation_config": {"type": "http", "url": "https://tenant.example.com", "method": "GET"},
    }

    response = await client.post(
        f"/tools/builtins/templates/{key}/instances",
        json=payload,
        headers=_headers(user, tenant),
    )
    assert response.status_code == 200

    body = response.json()
    assert body["tenant_id"] == str(tenant.id)
    assert body["builtin_key"] == key
    assert body["is_builtin_template"] is False
    assert body["is_builtin_instance"] is True
    assert body["builtin_template_id"] == str(template.id)
    assert body["status"] == "DRAFT"

    saved = (
        await db_session.execute(select(ToolRegistry).where(ToolRegistry.id == body["id"]))
    ).scalar_one()
    assert saved.tenant_id == tenant.id


@pytest.mark.asyncio
async def test_builtin_instance_schema_type_are_immutable_via_general_put(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)

    key = f"unit_immutable_{uuid4().hex[:8]}"
    await _ensure_builtin_template(
        db_session,
        builtin_key=key,
        implementation_type=ToolImplementationType.HTTP,
        implementation={"type": "http", "url": "https://example.com", "method": "GET"},
    )

    create_response = await client.post(
        f"/tools/builtins/templates/{key}/instances",
        json={"name": "immutable-instance"},
        headers=_headers(user, tenant),
    )
    assert create_response.status_code == 200
    instance_id = create_response.json()["id"]

    denied = await client.put(
        f"/tools/{instance_id}",
        json={
            "input_schema": {"type": "object", "properties": {"x": {"type": "string"}}},
            "implementation_type": "FUNCTION",
        },
        headers=_headers(user, tenant),
    )
    assert denied.status_code == 400
    assert "immutable schema/type" in denied.json()["detail"].lower()


@pytest.mark.asyncio
async def test_publish_builtin_retrieval_instance_with_tenant_pipeline(client, db_session):
    tenant, user = await _seed_tenant_and_user(db_session)

    await _ensure_builtin_template(
        db_session,
        builtin_key="retrieval_pipeline",
        implementation_type=ToolImplementationType.RAG_RETRIEVAL,
        implementation={"type": "rag_retrieval", "pipeline_id": ""},
    )
    pipeline = await _seed_retrieval_pipeline(db_session, tenant.id)

    create_response = await client.post(
        "/tools/builtins/templates/retrieval_pipeline/instances",
        json={
            "name": "tenant retrieval",
            "implementation_config": {"type": "rag_retrieval", "pipeline_id": str(pipeline.id)},
        },
        headers=_headers(user, tenant),
    )
    assert create_response.status_code == 200
    instance_id = create_response.json()["id"]

    publish_response = await client.post(
        f"/tools/builtins/instances/{instance_id}/publish",
        json={},
        headers=_headers(user, tenant),
    )
    assert publish_response.status_code == 200
    body = publish_response.json()
    assert body["status"] == "PUBLISHED"
    assert body["is_active"] is True

    versions = (
        await db_session.execute(select(ToolVersion).where(ToolVersion.tool_id == UUID(str(instance_id))))
    ).scalars().all()
    assert len(versions) == 1


@pytest.mark.asyncio
async def test_retrieval_instance_rejects_pipeline_from_other_tenant(client, db_session):
    tenant_a, user_a = await _seed_tenant_and_user(db_session)
    tenant_b, _user_b = await _seed_tenant_and_user(db_session)

    await _ensure_builtin_template(
        db_session,
        builtin_key="retrieval_pipeline",
        implementation_type=ToolImplementationType.RAG_RETRIEVAL,
        implementation={"type": "rag_retrieval", "pipeline_id": ""},
    )
    foreign_pipeline = await _seed_retrieval_pipeline(db_session, tenant_b.id)

    response = await client.post(
        "/tools/builtins/templates/retrieval_pipeline/instances",
        json={
            "name": "invalid retrieval",
            "implementation_config": {"type": "rag_retrieval", "pipeline_id": str(foreign_pipeline.id)},
        },
        headers=_headers(user_a, tenant_a),
    )
    assert response.status_code == 400
    assert "tenant scope" in response.json()["detail"].lower() or "not found" in response.json()["detail"].lower()
