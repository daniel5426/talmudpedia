import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from langchain_core.messages import AIMessageChunk, ToolMessage

from app.agent.executors.standard import ReasoningNodeExecutor
from app.agent.executors.tool import ToolNodeExecutor
from app.services.model_resolver import ModelResolver


class FakeProvider:
    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0

    async def stream(self, messages, system_prompt=None, **kwargs):
        response = self.responses[self.call_count]
        self.call_count += 1
        for chunk in response:
            yield chunk


class FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class FakeDB:
    def __init__(self, tools):
        self._tools = tools

    async def execute(self, stmt):
        return FakeResult(self._tools)


def make_tool_record(tool_id, name, execution):
    return SimpleNamespace(
        id=tool_id,
        name=name,
        slug=name,
        description="",
        schema={
            "input": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
            }
        },
        config_schema={"execution": execution},
    )


def patch_resolver(monkeypatch, provider):
    async def fake_resolve(self, model_id):
        return provider

    monkeypatch.setattr(ModelResolver, "resolve", fake_resolve)


@pytest.mark.asyncio
async def test_streaming_tool_deltas_execute_and_continue(monkeypatch):
    tool_id = str(uuid4())
    tool_call = {"id": "call-1", "name": "tool_one", "args": json.dumps({"q": "x"})}

    provider = FakeProvider(
        responses=[
            [AIMessageChunk(content="Calling tool", tool_call_chunks=[tool_call])],
            [AIMessageChunk(content="final answer")],
        ]
    )

    patch_resolver(monkeypatch, provider)

    async def fake_execute(self, state, config, context):
        return {"context": {"tool_id": config["tool_id"], "input": state.get("context")}}

    monkeypatch.setattr(ToolNodeExecutor, "execute", fake_execute)

    tool_record = make_tool_record(tool_id, "tool_one", {"is_pure": True})
    db = FakeDB([tool_record])

    executor = ReasoningNodeExecutor(tenant_id=None, db=db)

    result = await executor.execute(
        {"messages": [{"role": "user", "content": "hi"}]},
        {
            "model_id": "model-1",
            "tools": [tool_id],
            "tool_execution_mode": "parallel_safe",
        },
        {"node_id": "agent-1"},
    )

    assert result["state"]["last_agent_output"] == "final answer"
    assert len(result["messages"]) == 3
    assert isinstance(result["messages"][1], ToolMessage)


@pytest.mark.asyncio
async def test_parallel_safe_order_is_deterministic(monkeypatch):
    tool_id_1 = str(uuid4())
    tool_id_2 = str(uuid4())

    tool_calls = [
        {"id": "call-1", "name": "tool_one", "args": json.dumps({"q": "a"})},
        {"id": "call-2", "name": "tool_two", "args": json.dumps({"q": "b"})},
    ]

    provider = FakeProvider(
        responses=[
            [AIMessageChunk(content="", tool_call_chunks=tool_calls)],
            [AIMessageChunk(content="done")],
        ]
    )
    patch_resolver(monkeypatch, provider)

    async def fake_execute(self, state, config, context):
        if config["tool_id"] == tool_id_1:
            await asyncio.sleep(0.05)
        else:
            await asyncio.sleep(0.01)
        return {"context": {"tool_id": config["tool_id"]}}

    monkeypatch.setattr(ToolNodeExecutor, "execute", fake_execute)

    tool_records = [
        make_tool_record(tool_id_1, "tool_one", {"is_pure": True, "concurrency_group": "g1", "max_concurrency": 1}),
        make_tool_record(tool_id_2, "tool_two", {"is_pure": True, "concurrency_group": "g2", "max_concurrency": 1}),
    ]
    db = FakeDB(tool_records)

    executor = ReasoningNodeExecutor(tenant_id=None, db=db)

    result = await executor.execute(
        {"messages": [{"role": "user", "content": "hi"}]},
        {
            "model_id": "model-1",
            "tools": [tool_id_1, tool_id_2],
            "tool_execution_mode": "parallel_safe",
            "max_parallel_tools": 2,
        },
        {"node_id": "agent-2"},
    )

    tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [m.tool_call_id for m in tool_messages] == ["call-1", "call-2"]


@pytest.mark.asyncio
async def test_timeout_is_enforced(monkeypatch):
    tool_id = str(uuid4())
    tool_call = {"id": "call-1", "name": "tool_one", "args": json.dumps({"q": "x"})}

    provider = FakeProvider(
        responses=[
            [AIMessageChunk(content="", tool_call_chunks=[tool_call])],
            [AIMessageChunk(content="done")],
        ]
    )
    patch_resolver(monkeypatch, provider)

    async def fake_execute(self, state, config, context):
        await asyncio.sleep(0.05)
        return {"context": {"tool_id": config["tool_id"]}}

    monkeypatch.setattr(ToolNodeExecutor, "execute", fake_execute)

    tool_record = make_tool_record(tool_id, "tool_one", {"is_pure": True, "timeout_s": 0.01})
    db = FakeDB([tool_record])

    executor = ReasoningNodeExecutor(tenant_id=None, db=db)

    result = await executor.execute(
        {"messages": [{"role": "user", "content": "hi"}]},
        {
            "model_id": "model-1",
            "tools": [tool_id],
            "tool_execution_mode": "sequential",
        },
        {"node_id": "agent-3"},
    )

    assert result["tool_outputs"][0]["error"].startswith("Tool call timed out")


@pytest.mark.asyncio
async def test_json_tool_call_fallback(monkeypatch):
    tool_id = str(uuid4())
    tool_payload = {"tool_id": tool_id, "input": {"q": "x"}}
    tool_json = json.dumps(tool_payload)

    provider = FakeProvider(
        responses=[[AIMessageChunk(content=tool_json)], [AIMessageChunk(content="done")]]
    )
    patch_resolver(monkeypatch, provider)

    async def fake_execute(self, state, config, context):
        return {"context": {"tool_id": config["tool_id"], "input": state.get("context")}}

    monkeypatch.setattr(ToolNodeExecutor, "execute", fake_execute)

    tool_record = make_tool_record(tool_id, "tool_one", {"is_pure": False})
    db = FakeDB([tool_record])

    executor = ReasoningNodeExecutor(tenant_id=None, db=db)

    result = await executor.execute(
        {"messages": [{"role": "user", "content": "hi"}]},
        {
            "model_id": "model-1",
            "tools": [tool_id],
        },
        {"node_id": "agent-4"},
    )

    assert result["tool_outputs"]
    assert result["state"]["last_agent_output"] == "done"


@pytest.mark.asyncio
async def test_max_iterations_enforced(monkeypatch):
    tool_id = str(uuid4())
    tool_call = {"id": "call-1", "name": "tool_one", "args": json.dumps({"q": "x"})}

    provider = FakeProvider(responses=[[AIMessageChunk(content="", tool_call_chunks=[tool_call])]])
    patch_resolver(monkeypatch, provider)

    async def fake_execute(self, state, config, context):
        return {"context": {"tool_id": config["tool_id"]}}

    monkeypatch.setattr(ToolNodeExecutor, "execute", fake_execute)

    tool_record = make_tool_record(tool_id, "tool_one", {"is_pure": True})
    db = FakeDB([tool_record])

    executor = ReasoningNodeExecutor(tenant_id=None, db=db)

    result = await executor.execute(
        {"messages": [{"role": "user", "content": "hi"}]},
        {
            "model_id": "model-1",
            "tools": [tool_id],
            "max_tool_iterations": 1,
        },
        {"node_id": "agent-5"},
    )

    assert result.get("error") == "Max tool iterations reached"


@pytest.mark.asyncio
async def test_concurrency_group_limit(monkeypatch):
    tool_id_1 = str(uuid4())
    tool_id_2 = str(uuid4())

    tool_calls = [
        {"id": "call-1", "name": "tool_one", "args": json.dumps({"q": "a"})},
        {"id": "call-2", "name": "tool_two", "args": json.dumps({"q": "b"})},
    ]

    provider = FakeProvider(
        responses=[
            [AIMessageChunk(content="", tool_call_chunks=tool_calls)],
            [AIMessageChunk(content="done")],
        ]
    )
    patch_resolver(monkeypatch, provider)

    active = {"count": 0, "max": 0}

    async def fake_execute(self, state, config, context):
        active["count"] += 1
        active["max"] = max(active["max"], active["count"])
        await asyncio.sleep(0.02)
        active["count"] -= 1
        return {"context": {"tool_id": config["tool_id"]}}

    monkeypatch.setattr(ToolNodeExecutor, "execute", fake_execute)

    tool_records = [
        make_tool_record(tool_id_1, "tool_one", {"is_pure": True, "concurrency_group": "g1", "max_concurrency": 1}),
        make_tool_record(tool_id_2, "tool_two", {"is_pure": True, "concurrency_group": "g1", "max_concurrency": 1}),
    ]
    db = FakeDB(tool_records)

    executor = ReasoningNodeExecutor(tenant_id=None, db=db)

    await executor.execute(
        {"messages": [{"role": "user", "content": "hi"}]},
        {
            "model_id": "model-1",
            "tools": [tool_id_1, tool_id_2],
            "tool_execution_mode": "parallel_safe",
            "max_parallel_tools": 2,
        },
        {"node_id": "agent-6"},
    )

    assert active["max"] == 1
