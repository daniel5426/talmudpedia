from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.services.published_app_coding_agent_tools  # noqa: F401
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


def make_tool(tool_id, config_schema, implementation_type="FUNCTION", schema=None):
    return SimpleNamespace(
        id=tool_id,
        name="function_tool",
        slug="function_tool",
        description="",
        schema=schema or {"input": {"type": "object"}},
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


@pytest.mark.asyncio
async def test_function_tool_merges_args_with_context(monkeypatch):
    captured = {}

    @register_tool_function("unit_test_capture_payload")
    def unit_test_capture_payload(payload):
        captured.update(payload)
        return {"ok": True}

    tool_id = uuid4()
    config_schema = {"implementation": {"type": "function", "function_name": "unit_test_capture_payload"}}
    tool = make_tool(tool_id, config_schema)
    db = FakeDB(tool)

    executor = ToolNodeExecutor(tenant_id=None, db=db)

    async def has_columns(_self):
        return True

    monkeypatch.setattr(ToolNodeExecutor, "_has_artifact_columns", has_columns)

    await executor.execute(
        {
            "context": {
                "run_id": "run-123",
                "args": {"path": "src/Sidebar.tsx", "content": "next"},
            }
        },
        {"tool_id": str(tool_id)},
        {"node_id": "tool-node"},
    )

    assert captured["run_id"] == "run-123"
    assert captured["path"] == "src/Sidebar.tsx"
    assert captured["content"] == "next"


@pytest.mark.asyncio
async def test_function_tool_merges_json_string_args_with_context(monkeypatch):
    captured = {}

    @register_tool_function("unit_test_capture_json_args_payload")
    def unit_test_capture_json_args_payload(payload):
        captured.update(payload)
        return {"ok": True}

    tool_id = uuid4()
    config_schema = {"implementation": {"type": "function", "function_name": "unit_test_capture_json_args_payload"}}
    tool = make_tool(tool_id, config_schema)
    db = FakeDB(tool)

    executor = ToolNodeExecutor(tenant_id=None, db=db)

    async def has_columns(_self):
        return True

    monkeypatch.setattr(ToolNodeExecutor, "_has_artifact_columns", has_columns)

    await executor.execute(
        {
            "context": {
                "run_id": "run-json-456",
                "args": "{\"path\":\"src/Sidebar.tsx\",\"content\":\"next-json\"}",
            }
        },
        {"tool_id": str(tool_id)},
        {"node_id": "tool-node"},
    )

    assert captured["run_id"] == "run-json-456"
    assert captured["path"] == "src/Sidebar.tsx"
    assert captured["content"] == "next-json"


@pytest.mark.asyncio
async def test_function_tool_merges_input_wrapper_with_context(monkeypatch):
    captured = {}

    @register_tool_function("unit_test_capture_input_wrapper_payload")
    def unit_test_capture_input_wrapper_payload(payload):
        captured.update(payload)
        return {"ok": True}

    tool_id = uuid4()
    config_schema = {"implementation": {"type": "function", "function_name": "unit_test_capture_input_wrapper_payload"}}
    tool = make_tool(tool_id, config_schema)
    db = FakeDB(tool)

    executor = ToolNodeExecutor(tenant_id=None, db=db)

    async def has_columns(_self):
        return True

    monkeypatch.setattr(ToolNodeExecutor, "_has_artifact_columns", has_columns)

    await executor.execute(
        {
            "context": {
                "run_id": "run-input-789",
                "input": {"filePath": "src/Sidebar.tsx", "code": "next-from-input"},
            }
        },
        {"tool_id": str(tool_id)},
        {"node_id": "tool-node"},
    )

    assert captured["run_id"] == "run-input-789"
    assert captured["filePath"] == "src/Sidebar.tsx"
    assert captured["code"] == "next-from-input"


@pytest.mark.asyncio
async def test_coding_agent_function_tool_missing_required_fields_returns_validation_failure(monkeypatch):
    tool_id = uuid4()
    config_schema = {"implementation": {"type": "function", "function_name": "coding_agent_read_file"}}
    tool = make_tool(
        tool_id,
        config_schema,
        schema={
            "input": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            }
        },
    )
    db = FakeDB(tool)
    executor = ToolNodeExecutor(tenant_id=None, db=db)

    async def has_columns(_self):
        return True

    monkeypatch.setattr(ToolNodeExecutor, "_has_artifact_columns", has_columns)

    result = await executor.execute(
        {"context": {"run_id": "run-1", "args": {}}},
        {"tool_id": str(tool_id)},
        {"node_id": "tool-node"},
    )

    assert result["context"]["code"] == "TOOL_INPUT_VALIDATION_FAILED"
    assert result["context"]["fields"] == ["path"]
    assert "Missing required fields" in result["context"]["error"]
    assert "received_keys" in result["context"]


@pytest.mark.asyncio
async def test_coding_agent_function_tool_policy_error_is_normalized(monkeypatch):
    tool_id = uuid4()
    config_schema = {"implementation": {"type": "function", "function_name": "coding_agent_read_file"}}
    tool = make_tool(
        tool_id,
        config_schema,
        schema={
            "input": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            }
        },
    )
    db = FakeDB(tool)
    executor = ToolNodeExecutor(tenant_id=None, db=db)

    async def has_columns(_self):
        return True

    monkeypatch.setattr(ToolNodeExecutor, "_has_artifact_columns", has_columns)

    result = await executor.execute(
        {"context": {"run_id": "run-1", "args": {"path": "/etc/passwd"}}},
        {"tool_id": str(tool_id)},
        {"node_id": "tool-node"},
    )

    assert result["context"]["code"] == "BUILDER_PATCH_POLICY_VIOLATION"
    assert result["context"]["field"] == "path"
    assert "Absolute paths are not allowed" in result["context"]["error"]
