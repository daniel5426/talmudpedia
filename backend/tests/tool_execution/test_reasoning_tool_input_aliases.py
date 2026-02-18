from types import SimpleNamespace

from app.agent.executors.standard import ReasoningNodeExecutor


def _make_executor() -> ReasoningNodeExecutor:
    return ReasoningNodeExecutor(tenant_id=None, db=None)


def test_coerce_tool_input_maps_path_aliases() -> None:
    executor = _make_executor()
    tool = SimpleNamespace(
        schema={
            "input": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            }
        }
    )

    coerced = executor._coerce_tool_input(
        {
            "file_path": "src/App.tsx",
            "content": "export const App = () => null;",
        },
        tool,
    )

    assert coerced["path"] == "src/App.tsx"


def test_coerce_tool_input_maps_nested_path_aliases() -> None:
    executor = _make_executor()
    tool = SimpleNamespace(
        schema={
            "input": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            }
        }
    )

    coerced = executor._coerce_tool_input(
        {
            "input": {"filePath": "src/components/Button.tsx"},
            "content": "export function Button() { return <button/>; }",
        },
        tool,
    )

    assert coerced["path"] == "src/components/Button.tsx"


def test_coerce_tool_input_maps_parameters_wrapper_path_aliases() -> None:
    executor = _make_executor()
    tool = SimpleNamespace(
        schema={
            "input": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            }
        }
    )

    coerced = executor._coerce_tool_input(
        {
            "parameters": {"relativePath": "src/layout/Sidebar.tsx"},
            "content": "export const Sidebar = () => null;",
        },
        tool,
    )

    assert coerced["path"] == "src/layout/Sidebar.tsx"


def test_coerce_tool_input_maps_json_string_value_path_aliases() -> None:
    executor = _make_executor()
    tool = SimpleNamespace(
        schema={
            "input": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            }
        }
    )

    coerced = executor._coerce_tool_input(
        {
            "value": "{\"filePath\":\"src/theme/colors.ts\",\"content\":\"export const primary='red';\"}",
        },
        tool,
    )

    assert coerced["path"] == "src/theme/colors.ts"


def test_coerce_tool_input_maps_content_aliases() -> None:
    executor = _make_executor()
    tool = SimpleNamespace(
        schema={
            "input": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            }
        }
    )

    coerced = executor._coerce_tool_input(
        {
            "input": {"filePath": "src/theme/colors.ts", "code": "export const primary='blue';"},
        },
        tool,
    )

    assert coerced["path"] == "src/theme/colors.ts"
    assert coerced["content"] == "export const primary='blue';"


def test_coerce_tool_input_maps_rename_aliases() -> None:
    executor = _make_executor()
    tool = SimpleNamespace(
        schema={
            "input": {
                "type": "object",
                "properties": {
                    "from_path": {"type": "string"},
                    "to_path": {"type": "string"},
                },
                "required": ["from_path", "to_path"],
            }
        }
    )

    coerced = executor._coerce_tool_input(
        {
            "fromPath": "src/OldName.tsx",
            "toPath": "src/NewName.tsx",
        },
        tool,
    )

    assert coerced["from_path"] == "src/OldName.tsx"
    assert coerced["to_path"] == "src/NewName.tsx"
