from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agent.executors.tool import ToolNodeExecutor
from app.services.tool_function_registry import register_tool_function


class FakeResult:
    def __init__(self, tool):
        self._tool = tool

    def scalar_one_or_none(self):
        return self._tool


class FakeDB:
    def __init__(self, tool):
        self._tool = tool

    async def execute(self, _stmt):
        return FakeResult(self._tool)


def make_tool(tool_id, config_schema, implementation_type="FUNCTION"):
    return SimpleNamespace(
        id=tool_id,
        name="function_tool",
        slug="function_tool",
        description="",
        schema={"input": {"type": "object"}},
        config_schema=config_schema,
        is_active=True,
        is_system=False,
        artifact_id=None,
        artifact_version=None,
        implementation_type=implementation_type,
    )


@pytest.mark.asyncio
async def test_function_tool_execution(monkeypatch):
    @register_tool_function("unit_test_echo")
    def unit_test_echo(payload):
        return {"echo": payload}

    tool_id = uuid4()
    config_schema = {"implementation": {"type": "function", "function_name": "unit_test_echo"}}
    tool = make_tool(tool_id, config_schema)
    db = FakeDB(tool)

    executor = ToolNodeExecutor(tenant_id=None, db=db)

    async def has_columns(_self):
        return True

    monkeypatch.setattr(ToolNodeExecutor, "_has_artifact_columns", has_columns)

    result = await executor.execute(
        {"context": {"x": 1}},
        {"tool_id": str(tool_id)},
        {"node_id": "tool-node"},
    )

    assert result["context"]["echo"] == {"x": 1}


@pytest.mark.asyncio
async def test_function_tool_missing_name(monkeypatch):
    tool_id = uuid4()
    config_schema = {"implementation": {"type": "function", "function_name": "does_not_exist"}}
    tool = make_tool(tool_id, config_schema)
    db = FakeDB(tool)

    executor = ToolNodeExecutor(tenant_id=None, db=db)

    async def has_columns(_self):
        return True

    monkeypatch.setattr(ToolNodeExecutor, "_has_artifact_columns", has_columns)

    with pytest.raises(RuntimeError):
        await executor.execute(
            {"context": {"x": 1}},
            {"tool_id": str(tool_id)},
            {"node_id": "tool-node"},
        )
