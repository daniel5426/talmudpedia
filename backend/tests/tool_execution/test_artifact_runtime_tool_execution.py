import uuid
from types import SimpleNamespace

import pytest

from app.api.dependencies import get_current_principal
from app.agent.executors.tool import ToolNodeExecutor
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.services.artifact_runtime.revision_service import ArtifactRevisionService
from main import app


async def _seed_tenant_context(db_session):
    tenant = Tenant(id=uuid.uuid4(), name="Tool Tenant", slug=f"tool-{uuid.uuid4().hex[:8]}")
    user = User(id=uuid.uuid4(), email=f"tool-{uuid.uuid4().hex[:6]}@example.com", role="admin")
    org_unit = OrgUnit(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="Tool Org",
        slug=f"tool-org-{uuid.uuid4().hex[:6]}",
        type=OrgUnitType.org,
    )
    membership = OrgMembership(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user.id,
        org_unit_id=org_unit.id,
        role=OrgRole.owner,
        status=MembershipStatus.active,
    )
    db_session.add_all([tenant, user, org_unit, membership])
    await db_session.commit()
    return tenant, user


def _override_principal(tenant_id, user):
    async def _inner():
        return {
            "type": "user",
            "user": user,
            "user_id": str(user.id),
            "tenant_id": str(tenant_id),
            "scopes": ["tools.write"],
        }

    return _inner


async def _create_published_artifact(db_session, tenant_id, created_by):
    revisions = ArtifactRevisionService(db_session)
    artifact = await revisions.create_artifact(
        tenant_id=tenant_id,
        created_by=created_by,
        display_name="Tool Artifact",
        description=None,
        kind="tool_impl",
        source_files=[{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'ok': True}\n"}],
        entry_module_path="main.py",
        python_dependencies=[],
        runtime_target="cloudflare_workers",
        capabilities={},
        config_schema={},
        tool_contract={
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "side_effects": [],
            "execution_mode": "interactive",
            "tool_ui": {},
        },
    )
    await revisions.publish_latest_draft(artifact)
    await db_session.commit()
    return artifact


@pytest.mark.asyncio
async def test_tool_publish_pins_artifact_revision_id(client, db_session):
    tenant, user = await _seed_tenant_context(db_session)
    artifact = await _create_published_artifact(db_session, tenant.id, user.id)
    app.dependency_overrides[get_current_principal] = _override_principal(tenant.id, user)

    async def fake_ensure_deployment(self, *, revision, namespace, tenant_id=None):
        return SimpleNamespace(
            worker_name="prod-worker",
            deployment_id="dep-1",
            version_id="ver-1",
            build_hash=revision.build_hash,
        )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "app.services.artifact_runtime.deployment_service.ArtifactDeploymentService.ensure_deployment",
        fake_ensure_deployment,
    )

    try:
        create_response = await client.post(
            "/tools",
            json={
                "name": "Runtime Tool",
                "slug": f"runtime-tool-{uuid.uuid4().hex[:6]}",
                "description": "Tool backed by an artifact",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "scope": "tenant",
                "artifact_id": str(artifact.id),
            },
        )
        assert create_response.status_code == 200, create_response.text
        tool_id = create_response.json()["id"]

        publish_response = await client.post(f"/tools/{tool_id}/publish")
        assert publish_response.status_code == 200, publish_response.text
        assert publish_response.json()["artifact_revision_id"] == str(artifact.latest_published_revision_id)
    finally:
        monkeypatch.undo()
        app.dependency_overrides.pop(get_current_principal, None)


@pytest.mark.asyncio
async def test_tool_executor_routes_tenant_artifact_tools_through_shared_runtime(monkeypatch):
    tenant_id = uuid.uuid4()
    revision_id = uuid.uuid4()
    tool_id = uuid.uuid4()
    captured = {}

    async def fake_load_tool(self, tool_id_arg):
        assert tool_id_arg == tool_id
        return SimpleNamespace(
            id=tool_id,
            name="Artifact Tool",
            slug="artifact-tool",
            config_schema={},
            implementation_type="artifact",
            status="published",
            is_active=True,
            artifact_id=str(uuid.uuid4()),
            artifact_version=None,
            artifact_revision_id=revision_id,
        )

    async def fake_execute_live_run(self, **kwargs):
        captured["runtime"] = kwargs
        return SimpleNamespace(status="completed", result_payload={"answer": 42}, error_payload=None)

    monkeypatch.setattr(ToolNodeExecutor, "_load_tool", fake_load_tool)
    monkeypatch.setattr(
        "app.agent.executors.tool.ArtifactExecutionService.execute_live_run",
        fake_execute_live_run,
    )

    executor = ToolNodeExecutor(tenant_id=tenant_id, db=None)
    result = await executor.execute(
        {},
        {"tool_id": str(tool_id), "input": {"question": "life"}},
        {"mode": "production", "run_id": "run-1", "agent_id": "agent-1", "agent_slug": "demo"},
    )

    assert result == {"answer": 42}
    assert captured["runtime"]["domain"].value == "tool"
    assert captured["runtime"]["queue_class"] == "artifact_prod_interactive"
    assert captured["runtime"]["revision_id"] == revision_id


@pytest.mark.asyncio
async def test_tool_executor_rejects_non_uuid_artifact_bindings(monkeypatch):
    tool_id = uuid.uuid4()

    async def fake_load_tool(self, tool_id_arg):
        assert tool_id_arg == tool_id
        return SimpleNamespace(
            id=tool_id,
            name="Legacy Tool",
            slug="legacy-tool",
            config_schema={},
            implementation_type="artifact",
            status="published",
            is_active=True,
            artifact_id="builtin/platform_sdk",
            artifact_version=None,
            artifact_revision_id=None,
        )

    monkeypatch.setattr(ToolNodeExecutor, "_load_tool", fake_load_tool)

    executor = ToolNodeExecutor(tenant_id=uuid.uuid4(), db=None)
    with pytest.raises(ValueError, match="UUID artifact id"):
        await executor.execute({}, {"tool_id": str(tool_id), "input": {"x": 1}}, {"mode": "production"})
