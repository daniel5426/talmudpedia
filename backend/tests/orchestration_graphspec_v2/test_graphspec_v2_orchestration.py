from uuid import UUID, uuid4

import pytest

from app.agent.executors.orchestration import JoinNodeExecutor, ReplanNodeExecutor, SpawnRunNodeExecutor
from app.agent.graph.compiler import AgentCompiler
from app.agent.graph.schema import AgentGraph
from app.db.postgres.models.agents import Agent, AgentStatus
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.orchestration import OrchestratorPolicy, OrchestratorTargetAllowlist


def _node(node_id: str, node_type: str, config: dict | None = None) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "position": {"x": 0, "y": 0},
        "config": config or {},
    }


def _edge(edge_id: str, source: str, target: str, source_handle: str | None = None) -> dict:
    payload = {"id": edge_id, "source": source, "target": target}
    if source_handle is not None:
        payload["source_handle"] = source_handle
    return payload


def _graph_v2(nodes: list[dict], edges: list[dict] | None = None, spec_version: str = "2.0") -> AgentGraph:
    graph_edges = edges
    if graph_edges is None:
        graph_edges = []
        full_nodes = [_node("start", "start")] + nodes + [_node("end", "end")]
        for idx in range(len(full_nodes) - 1):
            graph_edges.append(_edge(f"e{idx}", full_nodes[idx]["id"], full_nodes[idx + 1]["id"]))
    else:
        full_nodes = [_node("start", "start")] + nodes + [_node("end", "end")]
    return AgentGraph(spec_version=spec_version, nodes=full_nodes, edges=graph_edges)


async def _seed_policy_fixture(
    db_session,
    *,
    target_status: AgentStatus = AgentStatus.published,
    include_allowlist: bool = True,
    allowed_scope_subset: list[str] | None = None,
    max_depth: int = 3,
    max_fanout: int = 8,
    max_children_total: int = 32,
):
    tenant = Tenant(name="orch-v2-tenant", slug=f"orch-v2-{uuid4().hex[:8]}")
    user = User(email=f"orch-v2-{uuid4().hex[:8]}@example.com", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    orchestrator = Agent(
        tenant_id=tenant.id,
        name="Orchestrator",
        slug=f"orchestrator-v2-{uuid4().hex[:8]}",
        status=AgentStatus.published,
        graph_definition={"nodes": [], "edges": []},
    )
    target = Agent(
        tenant_id=tenant.id,
        name="Target",
        slug=f"target-v2-{uuid4().hex[:8]}",
        status=target_status,
        graph_definition={"nodes": [], "edges": []},
    )
    db_session.add_all([orchestrator, target])
    await db_session.flush()

    policy = OrchestratorPolicy(
        tenant_id=tenant.id,
        orchestrator_agent_id=orchestrator.id,
        enforce_published_only=True,
        allowed_scope_subset=allowed_scope_subset or ["agents.execute"],
        max_depth=max_depth,
        max_fanout=max_fanout,
        max_children_total=max_children_total,
    )
    db_session.add(policy)

    if include_allowlist:
        db_session.add(
            OrchestratorTargetAllowlist(
                tenant_id=tenant.id,
                orchestrator_agent_id=orchestrator.id,
                target_agent_id=target.id,
            )
        )

    await db_session.commit()
    return {"tenant": tenant, "orchestrator": orchestrator, "target": target}


@pytest.mark.asyncio
async def test_v2_nodes_require_spec_version_2():
    compiler = AgentCompiler()
    graph = _graph_v2(
        nodes=[
            _node(
                "spawn",
                "spawn_run",
                {
                    "target_agent_slug": "child-a",
                    "scope_subset": ["agents.execute"],
                },
            )
        ],
        spec_version="1.0",
    )
    errors = await compiler.validate(graph)
    messages = [e.message for e in errors]
    assert any("require spec_version='2.0'" in msg for msg in messages)


@pytest.mark.asyncio
async def test_v2_compile_rejects_non_allowlisted_target(db_session):
    fx = await _seed_policy_fixture(db_session, include_allowlist=False)
    compiler = AgentCompiler(db=db_session, tenant_id=fx["tenant"].id)
    graph = _graph_v2(
        nodes=[
            _node(
                "spawn",
                "spawn_run",
                {
                    "target_agent_id": str(fx["target"].id),
                    "scope_subset": ["agents.execute"],
                },
            )
        ],
    )

    errors = await compiler.validate(graph, agent_id=fx["orchestrator"].id)
    messages = [e.message for e in errors]
    assert any("no target allowlist entries" in msg or "not allowlisted" in msg for msg in messages)


@pytest.mark.asyncio
async def test_v2_compile_rejects_unpublished_target(db_session):
    fx = await _seed_policy_fixture(db_session, target_status=AgentStatus.draft, include_allowlist=True)
    compiler = AgentCompiler(db=db_session, tenant_id=fx["tenant"].id)
    graph = _graph_v2(
        nodes=[
            _node(
                "spawn",
                "spawn_run",
                {
                    "target_agent_id": str(fx["target"].id),
                    "scope_subset": ["agents.execute"],
                },
            )
        ],
    )

    errors = await compiler.validate(graph, agent_id=fx["orchestrator"].id)
    assert any("not published" in e.message for e in errors)


@pytest.mark.asyncio
async def test_v2_compile_rejects_scope_subset_overflow(db_session):
    fx = await _seed_policy_fixture(db_session, allowed_scope_subset=["agents.execute"])
    compiler = AgentCompiler(db=db_session, tenant_id=fx["tenant"].id)
    graph = _graph_v2(
        nodes=[
            _node(
                "spawn",
                "spawn_run",
                {
                    "target_agent_id": str(fx["target"].id),
                    "scope_subset": ["agents.execute", "tools.write"],
                },
            )
        ],
    )

    errors = await compiler.validate(graph, agent_id=fx["orchestrator"].id)
    assert any("scope_subset exceeds orchestrator policy capability set" in e.message for e in errors)


@pytest.mark.asyncio
async def test_v2_compile_enforces_static_safety_limits(db_session):
    fx = await _seed_policy_fixture(
        db_session,
        max_depth=1,
        max_fanout=2,
        max_children_total=2,
    )
    compiler = AgentCompiler(db=db_session, tenant_id=fx["tenant"].id)
    group_targets = [
        {"target_agent_id": str(fx["target"].id), "mapped_input_payload": {"n": 1}},
        {"target_agent_id": str(fx["target"].id), "mapped_input_payload": {"n": 2}},
        {"target_agent_id": str(fx["target"].id), "mapped_input_payload": {"n": 3}},
    ]
    graph = _graph_v2(
        nodes=[
            _node(
                "spawn_a",
                "spawn_group",
                {
                    "targets": group_targets,
                    "scope_subset": ["agents.execute"],
                    "join_mode": "all",
                },
            ),
            _node(
                "spawn_b",
                "spawn_group",
                {
                    "targets": group_targets,
                    "scope_subset": ["agents.execute"],
                    "join_mode": "all",
                },
            ),
        ],
    )

    errors = await compiler.validate(graph, agent_id=fx["orchestrator"].id)
    messages = [e.message for e in errors]
    assert any("max_fanout" in msg for msg in messages)
    assert any("max_children_total" in msg for msg in messages)
    assert any("max_depth" in msg for msg in messages)


@pytest.mark.asyncio
async def test_v2_compile_rejects_join_missing_group_contract():
    compiler = AgentCompiler()
    graph = _graph_v2(nodes=[_node("joiner", "join", {"mode": "all"})])
    errors = await compiler.validate(graph)
    assert any("join requires orchestration_group_id" in e.message for e in errors)


@pytest.mark.asyncio
async def test_spawn_run_executor_calls_kernel(monkeypatch):
    captured = {}

    async def fake_spawn_run(self, **kwargs):
        captured.update(kwargs)
        return {
            "spawned_run_ids": ["11111111-1111-1111-1111-111111111111"],
            "idempotent": False,
        }

    monkeypatch.setattr(
        "app.services.orchestration_kernel_service.OrchestrationKernelService.spawn_run",
        fake_spawn_run,
    )

    executor = SpawnRunNodeExecutor(tenant_id=None, db=object())
    out = await executor.execute(
        state={},
        config={
            "target_agent_slug": "child-a",
            "scope_subset": ["agents.execute"],
            "mapped_input_payload": {"q": "hello"},
        },
        context={
            "run_id": "22222222-2222-2222-2222-222222222222",
            "node_id": "spawn_node",
        },
    )

    assert captured["caller_run_id"] == UUID("22222222-2222-2222-2222-222222222222")
    assert captured["target_agent_slug"] == "child-a"
    assert captured["scope_subset"] == ["agents.execute"]
    assert captured["idempotency_key"].startswith("spawn_node:")
    assert out["run_id"] == "11111111-1111-1111-1111-111111111111"


@pytest.mark.asyncio
async def test_join_and_replan_executors_route_next(monkeypatch):
    async def fake_join(self, **kwargs):
        return {"status": "running", "complete": False}

    async def fake_replan(self, **kwargs):
        return {"needs_replan": True, "failed_count": 1}

    monkeypatch.setattr(
        "app.services.orchestration_kernel_service.OrchestrationKernelService.join",
        fake_join,
    )
    monkeypatch.setattr(
        "app.services.orchestration_kernel_service.OrchestrationKernelService.evaluate_and_replan",
        fake_replan,
    )

    join = JoinNodeExecutor(tenant_id=None, db=object())
    join_out = await join.execute(
        state={"_node_outputs": {"spawn_group_1": {"orchestration_group_id": "33333333-3333-3333-3333-333333333333"}}},
        config={},
        context={"run_id": "44444444-4444-4444-4444-444444444444"},
    )
    assert join_out["next"] == "pending"

    replan = ReplanNodeExecutor(tenant_id=None, db=object())
    replan_out = await replan.execute(
        state={"_node_outputs": {"spawn_1": {"spawned_run_ids": ["55555555-5555-5555-5555-555555555555"]}}},
        config={},
        context={"run_id": "66666666-6666-6666-6666-666666666666"},
    )
    assert replan_out["next"] == "replan"


@pytest.mark.asyncio
async def test_v2_compile_accepts_fail_fast_and_best_effort_modes():
    compiler = AgentCompiler()
    join_cfg = {
        "mode": "fail_fast",
        "orchestration_group_id": "77777777-7777-7777-7777-777777777777",
    }
    graph = _graph_v2(
        nodes=[_node("joiner", "join", join_cfg)],
        edges=[
            _edge("e-start", "start", "joiner"),
            _edge("e-completed", "joiner", "end", "completed"),
            _edge("e-completed-errors", "joiner", "end", "completed_with_errors"),
            _edge("e-failed", "joiner", "end", "failed"),
            _edge("e-timeout", "joiner", "end", "timed_out"),
            _edge("e-pending", "joiner", "end", "pending"),
        ],
    )

    errors = await compiler.validate(graph)
    assert not any("Unsupported join mode" in e.message for e in errors)


@pytest.mark.asyncio
async def test_v2_compile_rejects_when_option_a_is_disabled(monkeypatch):
    monkeypatch.setenv("ORCHESTRATION_OPTION_A_ENABLED", "0")
    compiler = AgentCompiler(tenant_id=uuid4())
    graph = _graph_v2(
        nodes=[
            _node(
                "spawn",
                "spawn_run",
                {
                    "target_agent_slug": "child-a",
                    "scope_subset": ["agents.execute"],
                },
            )
        ],
    )

    errors = await compiler.validate(graph)
    assert any("disabled by feature flag" in e.message for e in errors)
