from __future__ import annotations

from datetime import datetime, UTC
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routers import artifacts as artifacts_router
from app.api.routers import orchestration_internal
from app.api.routers.agents import create_agent, list_agents
from app.api.schemas.artifacts import ArtifactLanguage, ArtifactRuntimeConfig, ToolArtifactContract
from app.api.routers.rag_pipelines import create_visual_pipeline
from app.api.schemas.agents import CreateAgentRequest, GraphDefinitionSchema
from app.db.postgres.models.agents import Agent
from app.db.postgres.models.identity import Tenant, User
from app.services import platform_native_tools
from app.services.control_plane.agents_admin_service import AgentAdminService
from app.services.control_plane.contracts import ListQuery


@pytest.mark.asyncio
async def test_agents_list_matches_service_route_and_native_tool(db_session, monkeypatch):
    tenant = Tenant(name="Agents Tenant", slug=f"agents-{uuid4().hex[:8]}")
    user = User(email=f"agents-{uuid4().hex[:8]}@example.com", hashed_password="x", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()
    db_session.add(
        Agent(
            tenant_id=tenant.id,
            name="Route Agent",
            slug="route-agent",
            graph_definition={
                "nodes": [
                    {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
                    {"id": "end", "type": "end", "position": {"x": 1, "y": 1}, "config": {}},
                ],
                "edges": [{"id": "e1", "source": "start", "target": "end", "type": "control"}],
            },
        )
    )
    await db_session.commit()

    async def _no_backfill(*args, **kwargs):
        return False

    monkeypatch.setattr(
        "app.api.routers.agents.OrganizationBootstrapService.ensure_organization_default_agents_if_missing",
        _no_backfill,
    )
    monkeypatch.setattr(
        "app.api.routers.agents.OrganizationBootstrapService.ensure_project_default_agents_if_missing",
        _no_backfill,
    )

    ctx = {"tenant_id": tenant.id, "user": user, "auth_token": None, "scopes": ["*"], "is_service": False}
    service_page = await AgentAdminService(db_session).list_agents(
        ctx=list_agents.__globals__["_control_plane_ctx_from_agent_context"](ctx),
        query=ListQuery(limit=20, skip=0, view="summary"),
    )

    route_result = await list_agents(status=None, skip=0, limit=20, view="summary", context=ctx, db=db_session)

    class _FakeSession:
        async def __aenter__(self):
            return db_session
        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    native_result = await platform_native_tools.platform_native_platform_agents(
        {
            "action": "agents.list",
            "payload": {"limit": 20, "view": "summary"},
            "__tool_runtime_context__": {"tenant_id": str(tenant.id), "user_id": str(user.id), "scopes": ["*"]},
        }
    )

    service_names = [item["name"] for item in service_page.items]
    route_names = [item["name"] for item in route_result["items"]]
    native_names = [item["name"] for item in native_result["result"]["items"]]

    assert service_names == ["Route Agent"]
    assert route_names == service_names
    assert native_names == service_names


@pytest.mark.asyncio
async def test_create_agent_route_uses_service_validation(db_session):
    tenant = Tenant(name="Create Tenant", slug=f"create-{uuid4().hex[:8]}")
    user = User(email=f"create-{uuid4().hex[:8]}@example.com", hashed_password="x", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()
    ctx = {"tenant_id": tenant.id, "user": user, "auth_token": None, "scopes": ["*"], "is_service": False}

    with pytest.raises(HTTPException) as exc_info:
        await create_agent(
            request=CreateAgentRequest(
                name="   ",
                slug="",
                description=None,
                graph_definition=GraphDefinitionSchema(nodes=[], edges=[]),
                memory_config=None,
                execution_constraints=None,
            ),
            _={},
            context=ctx,
            db=db_session,
        )

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_artifact_create_route_delegates_to_admin_service(monkeypatch):
    tenant = SimpleNamespace(id=uuid4(), slug="tenant-a")
    user = SimpleNamespace(id=uuid4(), email="artifact@example.com")
    captured = {}

    async def fake_create(self, *, ctx, params):
        captured["tenant_id"] = ctx.tenant_id
        captured["display_name"] = params.display_name
        return {
            "id": str(uuid4()),
            "display_name": params.display_name,
            "description": params.description,
            "kind": "tool_impl",
            "owner_type": "tenant",
            "type": "draft",
            "version": "draft",
            "config_schema": {},
            "runtime": {
                "language": "python",
                "source_files": [],
                "entry_module_path": "main.py",
                "dependencies": [],
                "runtime_target": "cloudflare_workers",
            },
            "capabilities": {},
            "agent_contract": None,
            "rag_contract": None,
            "tool_contract": {"input_schema": {}, "output_schema": {}, "side_effects": [], "execution_mode": "interactive", "tool_ui": {}},
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "system_key": None,
        }

    async def fake_link(**kwargs):
        return None

    class _FakeDb:
        async def commit(self):
            return None

    monkeypatch.setattr("app.api.routers.artifacts.ArtifactAdminService.create_artifact", fake_create)
    monkeypatch.setattr("app.api.routers.artifacts._link_artifact_coding_scope_to_saved_artifact", fake_link)

    request = artifacts_router.ArtifactCreate(
        display_name="Artifact A",
        description=None,
        kind=artifacts_router.ArtifactKind.TOOL_IMPL,
        runtime=ArtifactRuntimeConfig(
            language=ArtifactLanguage.PYTHON,
            source_files=[],
            entry_module_path="main.py",
            dependencies=[],
            runtime_target="cloudflare_workers",
        ),
        tool_contract=ToolArtifactContract(input_schema={}, output_schema={}),
    )
    response = await artifacts_router.create_artifact_draft(
        request=request,
        tenant_slug=None,
        _={},
        artifact_ctx=(tenant, user, _FakeDb()),
    )

    assert captured["tenant_id"] == tenant.id
    assert response.display_name == "Artifact A"


@pytest.mark.asyncio
async def test_orchestration_join_route_unwraps_service_operation(monkeypatch):
    async def fake_join(self, **kwargs):
        return {"operation": {"id": "group-1", "kind": "orchestration_group", "status": "completed"}, "result": {"joined": True}}

    monkeypatch.setattr("app.api.routers.orchestration_internal.OrchestrationAdminService.join", fake_join)

    class _Kernel:
        async def _require_run(self, run_id):
            return SimpleNamespace(tenant_id=uuid4())

    monkeypatch.setattr("app.api.routers.orchestration_internal.OrchestrationKernelService", lambda db: _Kernel())
    monkeypatch.setattr("app.api.routers.orchestration_internal._assert_tenant", lambda principal, tenant_id: None)
    monkeypatch.setattr("app.api.routers.orchestration_internal._assert_option_b_enabled", lambda tenant_id: None)

    result = await orchestration_internal.join(
        request=orchestration_internal.JoinRequest(
            caller_run_id=uuid4(),
            orchestration_group_id=uuid4(),
            mode=None,
            quorum_threshold=None,
            timeout_s=None,
        ),
        principal={"tenant_id": str(uuid4()), "scopes": ["*"]},
        _={},
        db=object(),
    )

    assert result == {"joined": True}


@pytest.mark.asyncio
async def test_rag_create_route_delegates_to_admin_service(monkeypatch):
    tenant = SimpleNamespace(id=uuid4(), slug="tenant-rag")
    user = SimpleNamespace(id=uuid4(), email="rag@example.com")
    captured = {}

    async def fake_create(self, *, ctx, params):
        captured["tenant_id"] = ctx.tenant_id
        captured["name"] = params.name
        return {"id": "pipe-1", "status": "created"}

    async def fake_get_pipeline_context(tenant_slug, current_user=None, db=None, context=None):
        return tenant, user, db

    async def fake_permission(*args, **kwargs):
        return True

    monkeypatch.setattr("app.api.routers.rag_pipelines.RagAdminService.create_pipeline", fake_create)
    monkeypatch.setattr("app.api.routers.rag_pipelines.get_pipeline_context", fake_get_pipeline_context)
    monkeypatch.setattr("app.api.routers.rag_pipelines.require_pipeline_permission", fake_permission)
    monkeypatch.setattr("app.api.routers.rag_pipelines.log_simple_action", fake_permission)

    request = create_visual_pipeline.__globals__["CreatePipelineRequest"](
        name="Pipe A",
        description=None,
        pipeline_type="retrieval",
        nodes=[],
        edges=[],
        org_unit_id=None,
    )
    result = await create_visual_pipeline(
        request=request,
        http_request=SimpleNamespace(),
        tenant_slug=None,
        context={"user": user, "scopes": ["*"], "auth_token": None},
        _={},
        db=object(),
    )

    assert captured["tenant_id"] == tenant.id
    assert result == {"id": "pipe-1", "status": "created"}
