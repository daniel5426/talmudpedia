from app.services.published_app_coding_agent_runtime_sandbox import PublishedAppCodingAgentRuntimeSandboxMixin


def test_workspace_write_detector_ignores_read_only_shell_command() -> None:
    payload = {
        "tool": "bash",
        "input": {
            "command": "git status",
            "description": "Check git status for uncommitted changes",
        },
    }

    assert PublishedAppCodingAgentRuntimeSandboxMixin._is_workspace_write_tool_event(
        event="tool.started",
        payload=payload,
    ) is False


def test_workspace_write_detector_flags_mutating_shell_command() -> None:
    payload = {
        "tool": "bash",
        "input": {
            "command": "sed -i 's/old/new/' src/index.css",
        },
    }

    assert PublishedAppCodingAgentRuntimeSandboxMixin._is_workspace_write_tool_event(
        event="tool.started",
        payload=payload,
    ) is True


def test_workspace_write_detector_flags_explicit_write_tool() -> None:
    payload = {"tool": "apply_patch", "input": {"patch": "*** Begin Patch"}}

    assert PublishedAppCodingAgentRuntimeSandboxMixin._is_workspace_write_tool_event(
        event="tool.completed",
        payload=payload,
    ) is True
