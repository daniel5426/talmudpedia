import pytest
import pytest_asyncio

from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.registry import ModelRegistry, ModelCapabilityType
from app.services.registry_seeding import seed_platform_sdk_tool

from artifacts.builtin.platform_sdk import handler as platform_sdk_handler
import types
from types import SimpleNamespace
from app.core.internal_token import create_service_token, decode_service_token


@pytest.fixture(autouse=True)
def register_standard_ops():
    from app.agent.executors.standard import register_standard_operators
    register_standard_operators()


@pytest_asyncio.fixture
async def architect_env(db_session):
    tenant = Tenant(name="Architect Tenant", slug="architect-tenant")
    user = User(email="architect@example.com", full_name="Architect Tester", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    model = ModelRegistry(
        tenant_id=tenant.id,
        name="Test Chat",
        slug="test-chat",
        description="Test chat model",
        capability_type=ModelCapabilityType.CHAT,
        is_active=True,
        is_default=True,
    )
    db_session.add(model)
    await db_session.commit()
    return tenant, user


@pytest.mark.asyncio
async def test_architect_agent_execute_plan_flow(db_session, architect_env, monkeypatch):
    """Directly exercise the SDK tool with a single deploy_agent step."""
    await seed_platform_sdk_tool(db_session)

    plan = {
        "action": "execute_plan",
        "steps": [
            {
                "action": "deploy_agent",
                "payload": {"name": "Child", "slug": "child", "graph_definition": {"nodes": [], "edges": []}},
            }
        ],
    }

    def fake_fetch(client, payload):
        return {
            "summary": {
                "rag": {"total": 0, "categories": {}, "examples": {}, "fields": []},
                "agent": {"total": 0, "categories": {}, "examples": {}, "fields": []},
            }
        }

    captured = {}

    def fake_execute(client, steps, dry_run):
        captured["steps"] = steps
        captured["dry_run"] = dry_run
        return {"steps": [{"action": "deploy_agent", "status": "ok"}]}, []

    def fake_validate(client, steps):
        return {"valid": True, "issues": []}, []

    monkeypatch.setattr(platform_sdk_handler, "_fetch_catalog", fake_fetch)
    monkeypatch.setattr(platform_sdk_handler, "_execute_plan", fake_execute)
    monkeypatch.setattr(platform_sdk_handler, "_validate_plan", fake_validate)

    state = {"state": {"last_agent_output": plan}}
    result = platform_sdk_handler.execute(state=state, config={}, context={})

    assert captured["steps"] == plan["steps"]
    assert captured["dry_run"] is False
    assert result["context"]["action"] == "execute_plan"


@pytest.mark.asyncio
async def test_architect_agent_respond_flow(db_session, architect_env, monkeypatch):
    """Ensure respond actions bypass execution."""
    await seed_platform_sdk_tool(db_session)

    response = {"action": "respond", "message": "No build required."}

    def fake_fetch(client, payload):
        return {
            "summary": {
                "rag": {"total": 0, "categories": {}, "examples": {}, "fields": []},
                "agent": {"total": 0, "categories": {}, "examples": {}, "fields": []},
            }
        }

    def fail_execute(*args, **kwargs):
        raise AssertionError("execute_plan should not be called for respond action")

    monkeypatch.setattr(platform_sdk_handler, "_fetch_catalog", fake_fetch)
    monkeypatch.setattr(platform_sdk_handler, "_execute_plan", fail_execute)

    state = {"state": {"last_agent_output": response}}
    result = platform_sdk_handler.execute(state=state, config={}, context={})

    assert result["context"]["action"] == "respond"
    assert result["context"]["result"]["message"] == "No build required."


@pytest.mark.asyncio
async def test_architect_agent_dry_run_passthrough(db_session, architect_env, monkeypatch):
    await seed_platform_sdk_tool(db_session)

    plan = {"action": "execute_plan", "steps": [], "dry_run": True}

    def fake_fetch(client, payload):
        return {
            "summary": {
                "rag": {"total": 0, "categories": {}, "examples": {}, "fields": []},
                "agent": {"total": 0, "categories": {}, "examples": {}, "fields": []},
            }
        }

    captured = {}

    def fake_execute(client, steps, dry_run):
        captured["dry_run"] = dry_run
        return {"steps": []}, []

    def fake_validate(client, steps):
        return {"valid": True, "issues": []}, []

    monkeypatch.setattr(platform_sdk_handler, "_fetch_catalog", fake_fetch)
    monkeypatch.setattr(platform_sdk_handler, "_execute_plan", fake_execute)
    monkeypatch.setattr(platform_sdk_handler, "_validate_plan", fake_validate)

    state = {"state": {"last_agent_output": plan}}
    result = platform_sdk_handler.execute(state=state, config={}, context={})
    assert captured["dry_run"] is True
    assert result["context"]["action"] == "execute_plan"


@pytest.mark.asyncio
async def test_architect_agent_handles_multiple_builds(db_session, architect_env, monkeypatch):
    """
    Validate the architect agent forwards complex plans that include:
    - at least 3 agent deployments
    - at least 2 rag pipeline deployments
    - each graph containing 5-10 nodes to mirror realistic workloads
    """
    await seed_platform_sdk_tool(db_session)

    def _graph(name: str, nodes: int):
        return {
            "name": name,
            "nodes": [{"id": f"n{i}", "type": "noop"} for i in range(nodes)],
            "edges": [{"source": f"n{i}", "target": f"n{i+1}"} for i in range(nodes - 1)],
        }

    plan = {
        "action": "execute_plan",
        "steps": [
            {"action": "deploy_agent", "payload": _graph("AgentA", 5)},
            {"action": "deploy_agent", "payload": _graph("AgentB", 6)},
            {"action": "deploy_agent", "payload": _graph("AgentC", 7)},
            {"action": "deploy_rag_pipeline", "payload": _graph("RagOne", 5)},
            {"action": "deploy_rag_pipeline", "payload": _graph("RagTwo", 8)},
        ],
    }

    def fake_fetch(client, payload):
        return {
            "summary": {
                "rag": {"total": 10, "categories": {}, "examples": {}, "fields": []},
                "agent": {"total": 10, "categories": {}, "examples": {}, "fields": []},
            }
        }

    captured = {}

    def fake_execute(client, steps, dry_run):
        captured["steps"] = steps
        captured["dry_run"] = dry_run
        return {"steps": [{"action": s.get("action"), "status": "ok"} for s in steps]}, []

    def fake_validate(client, steps):
        return {"valid": True, "issues": []}, []

    monkeypatch.setattr(platform_sdk_handler, "_fetch_catalog", fake_fetch)
    monkeypatch.setattr(platform_sdk_handler, "_execute_plan", fake_execute)
    monkeypatch.setattr(platform_sdk_handler, "_validate_plan", fake_validate)
    state = {"state": {"last_agent_output": plan}}
    result = platform_sdk_handler.execute(state=state, config={}, context={})

    assert captured["dry_run"] is False
    assert len(captured["steps"]) == 5

    # Validate counts by action type
    agent_steps = [s for s in captured["steps"] if s.get("action") == "deploy_agent"]
    rag_steps = [s for s in captured["steps"] if s.get("action") == "deploy_rag_pipeline"]
    assert len(agent_steps) >= 3
    assert len(rag_steps) >= 2

    # Validate node counts (5-10) in each payload
    for step in agent_steps + rag_steps:
        payload = step.get("payload") or step.get("graph_json")
        assert payload and "nodes" in payload
        assert 5 <= len(payload["nodes"]) <= 10

    # Tool output echoes the execute_plan action
    assert result["context"]["action"] == "execute_plan"


def _fake_response(payload=None):
    return SimpleNamespace(
        status_code=200,
        json=lambda: payload or {"ok": True},
        raise_for_status=lambda: None,
    )


def test_platform_sdk_handler_makes_real_deploy_calls(monkeypatch):
    """
    Ensure the SDK handler attempts HTTP calls for deploy_agent and deploy_rag_pipeline
    with the expected URLs and payloads.
    """
    captured = []

    def fake_post(url, json=None, headers=None, *args, **kwargs):
        captured.append({"url": url, "json": json, "headers": headers})
        return _fake_response({"url": url})

    monkeypatch.setattr(platform_sdk_handler.requests, "post", fake_post)

    plan = {
        "action": "execute_plan",
        "steps": [
            {
                "action": "deploy_agent",
                "payload": {"nodes": [{"id": "a", "type": "noop"}], "edges": []},
            },
            {
                "action": "deploy_rag_pipeline",
                "payload": {"nodes": [{"id": "b", "type": "noop"}], "edges": []},
            },
        ],
    }

    state = {"state": {"last_agent_output": plan}}
    platform_sdk_handler.execute(state=state, config={}, context={"token": "t", "tenant_id": "tenant", "user_id": "u"})

    urls = [c["url"] for c in captured]
    assert any(u.endswith("/api/agents") for u in urls)
    assert any("visual-pipelines" in u for u in urls)


@pytest.mark.asyncio
async def test_service_token_encode_decode(monkeypatch):
    monkeypatch.setenv("PLATFORM_SERVICE_SECRET", "test-secret")
    token = create_service_token(tenant_id="tenant-123")
    payload = decode_service_token(token)
    assert payload["tenant_id"] == "tenant-123"
    assert payload["role"] == "platform-service"


@pytest.mark.asyncio
async def test_catalog_fetch_with_service_token(client, db_session, monkeypatch):
    monkeypatch.setenv("PLATFORM_SERVICE_SECRET", "test-secret")
    tenant = Tenant(name="Service Tenant", slug="service-tenant")
    db_session.add(tenant)
    await db_session.commit()

    token = create_service_token(tenant_id=str(tenant.id))
    resp = await client.get(
        "/admin/pipelines/catalog",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_agent_deploy_with_service_token(client, db_session, monkeypatch):
    monkeypatch.setenv("PLATFORM_SERVICE_SECRET", "test-secret")
    tenant = Tenant(name="Service Tenant 2", slug="service-tenant-2")
    db_session.add(tenant)
    await db_session.commit()

    token = create_service_token(tenant_id=str(tenant.id))
    payload = {
        "name": "Service Agent",
        "slug": "service-agent",
        "graph_definition": {"nodes": [], "edges": []},
    }
    resp = await client.post(
        "/agents",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
