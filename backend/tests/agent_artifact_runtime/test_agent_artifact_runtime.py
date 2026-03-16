import uuid
from types import SimpleNamespace

import pytest

from app.agent.executors.artifact import ArtifactNodeExecutor
from app.agent.graph.compiler import AgentCompiler
from app.agent.graph.schema import AgentEdge, AgentGraph, AgentNode, AgentNodePosition
from app.db.postgres.models.identity import MembershipStatus, OrgMembership, OrgRole, OrgUnit, OrgUnitType, Tenant, User
from app.services.artifact_runtime.revision_service import ArtifactRevisionService


async def _seed_tenant_context(db_session):
    tenant = Tenant(id=uuid.uuid4(), name="Agent Tenant", slug=f"agent-{uuid.uuid4().hex[:8]}")
    user = User(id=uuid.uuid4(), email=f"agent-{uuid.uuid4().hex[:6]}@example.com", role="admin")
    org_unit = OrgUnit(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="Agent Org",
        slug=f"agent-org-{uuid.uuid4().hex[:6]}",
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


async def _create_artifact(db_session, tenant_id, created_by, *, publish: bool):
    revisions = ArtifactRevisionService(db_session)
    artifact = await revisions.create_artifact(
        tenant_id=tenant_id,
        created_by=created_by,
        display_name="Agent Artifact",
        description=None,
        kind="agent_node",
        source_files=[{"path": "main.py", "content": "def execute(inputs, config, context):\n    return {'ok': True}\n"}],
        entry_module_path="main.py",
        python_dependencies=[],
        runtime_target="cloudflare_workers",
        capabilities={"network_access": False},
        config_schema={},
        agent_contract={
            "state_reads": [],
            "state_writes": [],
            "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
            "output_schema": {"type": "object"},
            "node_ui": {"icon": "Sparkles"},
        },
    )
    if publish:
        await revisions.publish_latest_draft(artifact)
    await db_session.commit()
    return artifact


def _build_graph(artifact_type: str) -> AgentGraph:
    return AgentGraph(
        nodes=[
            AgentNode(id="start", type="start", position=AgentNodePosition(x=0, y=0), config={}),
            AgentNode(
                id="artifact",
                type=artifact_type,
                position=AgentNodePosition(x=1, y=0),
                config={"label": "Tenant Artifact"},
                input_mappings={"query": "{{ input }}"},
            ),
            AgentNode(id="end", type="end", position=AgentNodePosition(x=2, y=0), config={}),
        ],
        edges=[
            AgentEdge(id="e1", source="start", target="artifact"),
            AgentEdge(id="e2", source="artifact", target="end"),
        ],
    )


@pytest.mark.asyncio
async def test_agent_compiler_pins_published_artifact_revision_in_production(db_session):
    tenant, user = await _seed_tenant_context(db_session)
    artifact = await _create_artifact(db_session, tenant.id, user.id, publish=True)
    compiler = AgentCompiler(tenant_id=tenant.id, db=db_session)

    graph_ir = await compiler.compile(
        uuid.uuid4(),
        1,
        _build_graph(str(artifact.id)),
        config={"mode": "production"},
        input_params={"input": "hello"},
    )

    artifact_node = next(node for node in graph_ir.nodes if node.id == "artifact")
    assert artifact_node.config["_artifact_id"] == str(artifact.id)
    assert artifact_node.config["_artifact_revision_id"] == str(artifact.latest_published_revision_id)


@pytest.mark.asyncio
async def test_agent_compiler_rejects_draft_only_artifact_in_production(db_session):
    tenant, user = await _seed_tenant_context(db_session)
    artifact = await _create_artifact(db_session, tenant.id, user.id, publish=False)
    compiler = AgentCompiler(tenant_id=tenant.id, db=db_session)

    with pytest.raises(ValueError, match="Artifact resolution failed"):
        await compiler.compile(
            uuid.uuid4(),
            1,
            _build_graph(str(artifact.id)),
            config={"mode": "production"},
            input_params={"input": "hello"},
        )


@pytest.mark.asyncio
async def test_artifact_node_executor_routes_tenant_artifacts_through_shared_runtime(monkeypatch):
    tenant_id = uuid.uuid4()
    revision_id = uuid.uuid4()
    captured = {}

    async def fake_resolve(self, *, artifact_id, pinned_revision_id, require_published):
        captured["resolved"] = {
            "artifact_id": str(artifact_id),
            "pinned_revision_id": str(pinned_revision_id) if pinned_revision_id else None,
            "require_published": require_published,
        }
        return SimpleNamespace(
            id=revision_id,
            agent_contract={
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                }
            },
        )

    async def fake_execute_live_run(self, **kwargs):
        captured["runtime"] = kwargs
        return SimpleNamespace(status="completed", result_payload={"tool_outputs": ["ok"]}, error_payload=None)

    monkeypatch.setattr(ArtifactNodeExecutor, "_resolve_tenant_revision", fake_resolve)
    monkeypatch.setattr(
        "app.agent.executors.artifact.ArtifactExecutionService.execute_live_run",
        fake_execute_live_run,
    )

    executor = ArtifactNodeExecutor(tenant_id=tenant_id, db=None)
    result = await executor.execute(
        {"input": "hello"},
        {
            "_artifact_id": str(uuid.uuid4()),
            "_artifact_revision_id": str(revision_id),
            "input_mappings": {"query": "{{ input }}"},
        },
        {"mode": "production", "run_id": "run-1", "agent_id": "agent-1", "agent_slug": "demo"},
    )

    assert result == {"tool_outputs": ["ok"]}
    assert captured["resolved"]["require_published"] is True
    assert captured["runtime"]["domain"].value == "agent"
    assert captured["runtime"]["queue_class"] == "artifact_prod_interactive"
    assert captured["runtime"]["input_payload"] == {"query": "hello"}
