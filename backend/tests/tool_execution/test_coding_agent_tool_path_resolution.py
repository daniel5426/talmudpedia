from app.services.published_app_coding_agent_tools import (
    _normalize_command_payload,
    _resolve_content_arg,
    _resolve_from_path_arg,
    _resolve_patch_arg,
    _resolve_path_arg,
    _resolve_to_path_arg,
    validate_coding_agent_required_fields,
)


def test_resolve_path_arg_reads_nested_parameters() -> None:
    payload = {
        "parameters": {
            "file": {
                "relativePath": "src/components/Sidebar.tsx",
            }
        }
    }

    assert _resolve_path_arg(payload) == "src/components/Sidebar.tsx"


def test_resolve_rename_path_args_read_nested_wrappers() -> None:
    payload = {
        "payload": {
            "source": {"path": "src/components/OldSidebar.tsx"},
            "destination": {"toPath": "src/components/NewSidebar.tsx"},
        }
    }

    assert _resolve_from_path_arg(payload) == "src/components/OldSidebar.tsx"
    assert _resolve_to_path_arg(payload) == "src/components/NewSidebar.tsx"


def test_resolve_path_arg_reads_json_string_wrappers() -> None:
    payload = {
        "args": "{\"filePath\":\"src/components/Sidebar.tsx\"}",
    }

    assert _resolve_path_arg(payload) == "src/components/Sidebar.tsx"


def test_resolve_content_arg_reads_nested_aliases() -> None:
    payload = {
        "input": {
            "code": "export const Sidebar = () => null;",
        }
    }

    assert _resolve_content_arg(payload) == "export const Sidebar = () => null;"


def test_validate_write_file_required_fields_accepts_nested_alias_payload() -> None:
    payload = {
        "input": {
            "filePath": "src/components/Sidebar.tsx",
            "code": "export const Sidebar = () => null;",
        }
    }

    missing = validate_coding_agent_required_fields("coding_agent_write_file", payload)

    assert missing == []


def test_validate_write_file_required_fields_accepts_truncated_value_json_payload() -> None:
    payload = {
        "value": "{\"path\":\"src/App.tsx\",\"content\":\"import { useState } from \\\"react\\\";\\nexport default function App() { return <main/>; }",
    }

    missing = validate_coding_agent_required_fields("coding_agent_write_file", payload)

    assert missing == []
    assert _resolve_path_arg(payload) == "src/App.tsx"
    assert _resolve_content_arg(payload).startswith("import { useState } from")


def test_resolve_patch_arg_reads_nested_aliases() -> None:
    payload = {
        "input": {
            "unifiedDiff": "diff --git a/src/App.tsx b/src/App.tsx\n--- a/src/App.tsx\n+++ b/src/App.tsx\n",
        }
    }
    assert _resolve_patch_arg(payload).startswith("diff --git")


def test_validate_apply_patch_required_fields_accepts_value_payload() -> None:
    payload = {
        "value": "{\"patch\":\"diff --git a/src/App.tsx b/src/App.tsx\\n--- a/src/App.tsx\\n+++ b/src/App.tsx\\n\"}",
    }

    missing = validate_coding_agent_required_fields("coding_agent_apply_patch", payload)

    assert missing == []


def test_validate_read_range_required_fields_accepts_nested_path_alias() -> None:
    payload = {
        "input": {
            "filePath": "src/App.tsx",
            "startLine": 1,
            "endLine": 12,
        }
    }

    missing = validate_coding_agent_required_fields("coding_agent_read_file_range", payload)

    assert missing == []


def test_normalize_command_payload_accepts_string_command() -> None:
    command = _normalize_command_payload("npm run build")
    assert command == ["npm", "run", "build"]


def test_normalize_command_payload_rejects_invalid_types() -> None:
    try:
        _normalize_command_payload({"cmd": "npm run build"})
        assert False, "expected ValueError for invalid command payload type"
    except ValueError as exc:
        assert "command must be" in str(exc)
