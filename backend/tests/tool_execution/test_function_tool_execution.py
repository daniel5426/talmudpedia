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

    assert result["context"]["echo"]["x"] == 1
    assert result["context"]["echo"]["context"] == {}


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
async def test_function_tool_propagates_delegation_context(monkeypatch):
    captured = {}

    @register_tool_function("unit_test_capture_delegation_context")
    def unit_test_capture_delegation_context(payload):
        captured.update(payload)
        return {"ok": True}

    tool_id = uuid4()
    config_schema = {"implementation": {"type": "function", "function_name": "unit_test_capture_delegation_context"}}
    tool = make_tool(tool_id, config_schema)
    db = FakeDB(tool)

    executor = ToolNodeExecutor(tenant_id=None, db=db)

    async def has_columns(_self):
        return True

    monkeypatch.setattr(ToolNodeExecutor, "_has_artifact_columns", has_columns)

    await executor.execute(
        {"context": {"args": {"action": "agents.list"}}},
        {"tool_id": str(tool_id)},
        {
            "node_id": "tool-node",
            "tenant_id": "tenant-123",
            "grant_id": "grant-123",
            "principal_id": "principal-123",
            "requested_scopes": ["agents.read"],
            "agent_slug": "platform-architect",
            "mode": "debug",
        },
    )

    assert captured["context"]["tenant_id"] == "tenant-123"
    assert captured["context"]["grant_id"] == "grant-123"
    assert captured["context"]["principal_id"] == "principal-123"
    assert captured["context"]["requested_scopes"] == ["agents.read"]
    assert captured["context"]["agent_slug"] == "platform-architect"
    assert captured["context"]["mode"] == "debug"


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
    assert (
        "Absolute paths are not allowed" in result["context"]["error"]
        or "File path is required" in result["context"]["error"]
    )


@pytest.mark.asyncio
async def test_strict_function_tool_rejects_missing_required_field_before_dispatch(monkeypatch):
    captured = {"called": False}

    @register_tool_function("unit_test_strict_objective")
    def unit_test_strict_objective(payload):
        captured["called"] = True
        return {"ok": True, "payload": payload}

    tool_id = uuid4()
    config_schema = {
        "implementation": {"type": "function", "function_name": "unit_test_strict_objective"},
        "execution": {"strict_input_schema": True},
    }
    tool = make_tool(
        tool_id,
        config_schema,
        schema={
            "input": {
                "type": "object",
                "properties": {"objective": {"type": "string"}},
                "required": ["objective"],
                "additionalProperties": False,
            }
        },
    )
    db = FakeDB(tool)
    executor = ToolNodeExecutor(tenant_id=None, db=db)

    async def has_columns(_self):
        return True

    monkeypatch.setattr(ToolNodeExecutor, "_has_artifact_columns", has_columns)

    result = await executor.execute(
        {"context": {"run_id": "run-1", "args": {"instructions": "wrong key"}}},
        {"tool_id": str(tool_id)},
        {"node_id": "tool-node"},
    )

    assert captured["called"] is False
    assert result["context"]["code"] == "TOOL_INPUT_VALIDATION_FAILED"
    assert any("objective" in item["message"] for item in result["context"]["validation_errors"])


@pytest.mark.asyncio
async def test_strict_function_tool_rejects_unknown_fields_before_dispatch(monkeypatch):
    captured = {"called": False}

    @register_tool_function("unit_test_strict_no_extras")
    def unit_test_strict_no_extras(payload):
        captured["called"] = True
        return {"ok": True, "payload": payload}

    tool_id = uuid4()
    config_schema = {
        "implementation": {"type": "function", "function_name": "unit_test_strict_no_extras"},
        "execution": {"strict_input_schema": True},
    }
    tool = make_tool(
        tool_id,
        config_schema,
        schema={
            "input": {
                "type": "object",
                "properties": {"objective": {"type": "string"}},
                "required": ["objective"],
                "additionalProperties": False,
            }
        },
    )
    db = FakeDB(tool)
    executor = ToolNodeExecutor(tenant_id=None, db=db)

    async def has_columns(_self):
        return True

    monkeypatch.setattr(ToolNodeExecutor, "_has_artifact_columns", has_columns)

    result = await executor.execute(
        {"context": {"run_id": "run-1", "args": {"objective": "valid", "title": "extra"}}},
        {"tool_id": str(tool_id)},
        {"node_id": "tool-node"},
    )

    assert captured["called"] is False
    assert result["context"]["code"] == "TOOL_INPUT_VALIDATION_FAILED"
    assert any("Additional properties are not allowed" in item["message"] for item in result["context"]["validation_errors"])


@pytest.mark.asyncio
async def test_strict_function_tool_ignores_executor_runtime_metadata_before_dispatch(monkeypatch):
    captured = {"payload": None}

    @register_tool_function("unit_test_strict_runtime_metadata")
    def unit_test_strict_runtime_metadata(payload):
        captured["payload"] = payload
        return {"ok": True, "payload": payload}

    tool_id = uuid4()
    config_schema = {
        "implementation": {"type": "function", "function_name": "unit_test_strict_runtime_metadata"},
        "execution": {"strict_input_schema": True},
    }
    tool = make_tool(
        tool_id,
        config_schema,
        schema={
            "input": {
                "type": "object",
                "properties": {"objective": {"type": "string"}},
                "required": ["objective"],
                "additionalProperties": False,
            }
        },
    )
    db = FakeDB(tool)
    executor = ToolNodeExecutor(tenant_id=None, db=db)

    async def has_columns(_self):
        return True

    monkeypatch.setattr(ToolNodeExecutor, "_has_artifact_columns", has_columns)

    result = await executor.execute(
        {
            "context": {
                "objective": "valid objective",
                "run_id": "run-1",
                "tenant_id": "tenant-1",
                "agent_id": "agent-1",
                "thread_id": "thread-1",
            }
        },
        {"tool_id": str(tool_id)},
        {"node_id": "tool-node"},
    )

    assert result["context"]["ok"] is True
    assert captured["payload"] is not None
    assert captured["payload"]["objective"] == "valid objective"
    assert "agent_id" not in captured["payload"]
    assert "tenant_id" not in captured["payload"]
