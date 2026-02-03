import json

import pytest
import pytest_asyncio

from langchain_core.messages import AIMessage

from app.agent.core.interfaces import LLMProvider
from app.agent.execution.service import AgentExecutorService
from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.registry import ModelRegistry, ModelCapabilityType
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.services.model_resolver import ModelResolver
from app.services.registry_seeding import seed_platform_sdk_tool, seed_platform_architect_agent

from artifacts.builtin.platform_sdk import handler as platform_sdk_handler


class FakeProvider(LLMProvider):
    def __init__(self, content: str):
        self._content = content

    async def generate(self, messages, system_prompt=None, **kwargs):
        return AIMessage(content=self._content)

    async def stream(self, messages, system_prompt=None, **kwargs):
        yield self._content


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
    tenant, user = architect_env

    await seed_platform_sdk_tool(db_session)
    agent = await seed_platform_architect_agent(db_session)
    assert agent is not None

    plan = {
        "action": "execute_plan",
        "steps": [
            {
                "action": "deploy_agent",
                "payload": {"name": "Child", "slug": "child", "graph_definition": {"nodes": [], "edges": []}},
            }
        ],
    }

    async def fake_resolve(self, model_id, policy_override=None):
        return FakeProvider(json.dumps(plan))

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)

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

    monkeypatch.setattr(platform_sdk_handler, "_fetch_catalog", fake_fetch)
    monkeypatch.setattr(platform_sdk_handler, "_execute_plan", fake_execute)

    executor = AgentExecutorService(db=db_session)
    run_id = await executor.start_run(
        agent.id,
        input_params={"messages": [{"role": "user", "content": "Build a simple agent"}]},
        user_id=user.id,
        background=False,
    )

    async for _ in executor.run_and_stream(run_id, db_session):
        pass

    db_session.expire_all()
    run = await db_session.get(AgentRun, run_id)
    assert run.status == RunStatus.completed
    assert captured["steps"] == plan["steps"]
    assert run.output_result["context"]["action"] == "execute_plan"


@pytest.mark.asyncio
async def test_architect_agent_respond_flow(db_session, architect_env, monkeypatch):
    tenant, user = architect_env

    await seed_platform_sdk_tool(db_session)
    agent = await seed_platform_architect_agent(db_session)
    assert agent is not None

    response = {"action": "respond", "message": "No build required."}

    async def fake_resolve(self, model_id, policy_override=None):
        return FakeProvider(json.dumps(response))

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)

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

    executor = AgentExecutorService(db=db_session)
    run_id = await executor.start_run(
        agent.id,
        input_params={"messages": [{"role": "user", "content": "Just explain"}]},
        user_id=user.id,
        background=False,
    )

    async for _ in executor.run_and_stream(run_id, db_session):
        pass

    db_session.expire_all()
    run = await db_session.get(AgentRun, run_id)
    assert run.status == RunStatus.completed
    assert run.output_result["context"]["action"] == "respond"
    assert run.output_result["context"]["result"]["message"] == "No build required."


@pytest.mark.asyncio
async def test_architect_agent_dry_run_passthrough(db_session, architect_env, monkeypatch):
    tenant, user = architect_env

    await seed_platform_sdk_tool(db_session)
    agent = await seed_platform_architect_agent(db_session)
    assert agent is not None

    plan = {"action": "execute_plan", "steps": [], "dry_run": True}

    async def fake_resolve(self, model_id, policy_override=None):
        return FakeProvider(json.dumps(plan))

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)

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

    monkeypatch.setattr(platform_sdk_handler, "_fetch_catalog", fake_fetch)
    monkeypatch.setattr(platform_sdk_handler, "_execute_plan", fake_execute)

    executor = AgentExecutorService(db=db_session)
    run_id = await executor.start_run(
        agent.id,
        input_params={"messages": [{"role": "user", "content": "dry run"}]},
        user_id=user.id,
        background=False,
    )

    async for _ in executor.run_and_stream(run_id, db_session):
        pass

    assert captured["dry_run"] is True
