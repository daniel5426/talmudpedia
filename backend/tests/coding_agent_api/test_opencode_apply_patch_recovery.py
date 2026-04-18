from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.services.published_app_coding_agent_engines.opencode_engine import OpenCodePublishedAppCodingAgentEngine


def _opencode_run() -> AgentRun:
    return AgentRun(
        id=uuid4(),
        status=RunStatus.queued,
        input_params={
            "input": "update app",
            "messages": [{"role": "user", "content": "update app"}],
            "context": {
                "opencode_session_id": "sess-apply-fail",
                "opencode_workspace_path": "/workspace/apply-fail",
                "preview_sandbox_id": "sandbox-apply-fail",
                "resolved_model_id": "openai/gpt-5",
            },
        },
    )


@pytest.mark.asyncio
async def test_opencode_engine_accepts_apply_patch_completion_without_applied_files(db_session):
    run = _opencode_run()
    app = SimpleNamespace(id=uuid4())

    class _FakeOpenCodeClient:
        async def submit_turn(self, *, session_id, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, recovery_messages=None, selected_agent_contract=None, defer_until_stream=False):
            return "run-ref-apply-fail"

        async def stream_turn_events(self, *, session_id, turn_ref, sandbox_id=None, workspace_path=None):
            assert session_id == "sess-apply-fail"
            assert turn_ref == "run-ref-apply-fail"
            assert workspace_path == "/workspace/apply-fail"
            yield {
                "event": "tool.failed",
                "payload": {
                    "tool": "apply_patch",
                    "error": "Patch apply failed",
                    "output": {"error": "Patch apply failed", "code": "PATCH_HUNK_MISMATCH"},
                },
            }
            yield {
                "event": "tool.completed",
                "payload": {
                    "tool": "apply_patch",
                    "output": {"ok": True},
                },
            }
            yield {"event": "run.completed", "payload": {"status": "completed"}}

    engine = OpenCodePublishedAppCodingAgentEngine(db=db_session, client=_FakeOpenCodeClient())
    events = [event async for event in engine.stream(ctx=SimpleNamespace(app=app, run=run, resume_payload=None))]

    assert any(item.event == "tool.failed" for item in events)
    assert any(item.event == "tool.completed" for item in events)
    assert run.status == RunStatus.completed


@pytest.mark.asyncio
async def test_opencode_engine_allows_non_patch_edit_recovery_after_apply_patch_failure(db_session):
    run = _opencode_run()
    app = SimpleNamespace(id=uuid4())

    class _FakeOpenCodeClient:
        async def submit_turn(self, *, session_id, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, recovery_messages=None, selected_agent_contract=None, defer_until_stream=False):
            return "run-ref-edit-recover"

        async def stream_turn_events(self, *, session_id, turn_ref, sandbox_id=None, workspace_path=None):
            assert session_id == "sess-apply-fail"
            assert turn_ref == "run-ref-edit-recover"
            assert workspace_path == "/workspace/apply-fail"
            yield {
                "event": "tool.failed",
                "payload": {
                    "tool": "apply_patch",
                    "error": "Patch apply failed",
                    "output": {"error": "Patch apply failed", "code": "PATCH_HUNK_MISMATCH"},
                },
            }
            yield {
                "event": "tool.completed",
                "payload": {
                    "tool": "write",
                    "output": {"path": "src/App.tsx"},
                },
            }
            yield {"event": "run.completed", "payload": {"status": "completed"}}

    engine = OpenCodePublishedAppCodingAgentEngine(db=db_session, client=_FakeOpenCodeClient())
    events = [event async for event in engine.stream(ctx=SimpleNamespace(app=app, run=run, resume_payload=None))]

    assert any(item.event == "tool.failed" for item in events)
    assert any(item.event == "tool.completed" for item in events)
    assert run.status == RunStatus.completed


@pytest.mark.asyncio
async def test_opencode_engine_can_disable_unrecovered_apply_patch_fail_closed(db_session, monkeypatch):
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_FAIL_ON_UNRECOVERED_APPLY_PATCH", "0")
    run = _opencode_run()
    app = SimpleNamespace(id=uuid4())

    class _FakeOpenCodeClient:
        async def submit_turn(self, *, session_id, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, recovery_messages=None, selected_agent_contract=None, defer_until_stream=False):
            return "run-ref-disabled-strict"

        async def stream_turn_events(self, *, session_id, turn_ref, sandbox_id=None, workspace_path=None):
            assert session_id == "sess-apply-fail"
            assert turn_ref == "run-ref-disabled-strict"
            assert workspace_path == "/workspace/apply-fail"
            yield {
                "event": "tool.failed",
                "payload": {
                    "tool": "apply_patch",
                    "error": "Patch apply failed",
                    "output": {"error": "Patch apply failed", "code": "PATCH_HUNK_MISMATCH"},
                },
            }
            yield {"event": "run.completed", "payload": {"status": "completed"}}

    engine = OpenCodePublishedAppCodingAgentEngine(db=db_session, client=_FakeOpenCodeClient())
    events = [event async for event in engine.stream(ctx=SimpleNamespace(app=app, run=run, resume_payload=None))]

    assert any(item.event == "tool.failed" for item in events)
    assert run.status == RunStatus.completed


@pytest.mark.asyncio
async def test_opencode_engine_stops_consuming_stream_after_terminal_event(db_session):
    run = _opencode_run()
    app = SimpleNamespace(id=uuid4())

    class _FakeOpenCodeClient:
        async def submit_turn(self, *, session_id, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, recovery_messages=None, selected_agent_contract=None, defer_until_stream=False):
            return "run-ref-terminal-stop"

        async def stream_turn_events(self, *, session_id, turn_ref, sandbox_id=None, workspace_path=None):
            assert session_id == "sess-apply-fail"
            assert turn_ref == "run-ref-terminal-stop"
            assert workspace_path == "/workspace/apply-fail"
            yield {"event": "run.completed", "payload": {"status": "completed"}}
            raise AssertionError("OpenCode stream was consumed after terminal event")

    engine = OpenCodePublishedAppCodingAgentEngine(db=db_session, client=_FakeOpenCodeClient())
    events = [event async for event in engine.stream(ctx=SimpleNamespace(app=app, run=run, resume_payload=None))]

    assert events == []
    assert run.status == RunStatus.completed


@pytest.mark.asyncio
async def test_opencode_engine_defaults_to_raw_tool_completed_event_when_output_contains_error(db_session):
    run = _opencode_run()
    app = SimpleNamespace(id=uuid4())

    class _FakeOpenCodeClient:
        async def submit_turn(self, *, session_id, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, recovery_messages=None, selected_agent_contract=None, defer_until_stream=False):
            return "run-ref-raw-tool-event"

        async def stream_turn_events(self, *, session_id, turn_ref, sandbox_id=None, workspace_path=None):
            assert session_id == "sess-apply-fail"
            assert turn_ref == "run-ref-raw-tool-event"
            assert workspace_path == "/workspace/apply-fail"
            yield {
                "event": "tool.completed",
                "payload": {
                    "tool": "read",
                    "output": {"error": "permission denied", "code": "EACCES"},
                },
            }
            yield {"event": "run.completed", "payload": {"status": "completed"}}

    engine = OpenCodePublishedAppCodingAgentEngine(db=db_session, client=_FakeOpenCodeClient())
    events = [event async for event in engine.stream(ctx=SimpleNamespace(app=app, run=run, resume_payload=None))]

    assert any(item.event == "tool.completed" for item in events)
    assert not any(item.event == "tool.failed" for item in events)
    assert run.status == RunStatus.completed


@pytest.mark.asyncio
async def test_opencode_engine_can_enable_normalized_tool_failed_mapping(db_session, monkeypatch):
    monkeypatch.setenv("APPS_CODING_AGENT_OPENCODE_TOOL_EVENT_MODE", "normalized")
    run = _opencode_run()
    app = SimpleNamespace(id=uuid4())

    class _FakeOpenCodeClient:
        async def submit_turn(self, *, session_id, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, recovery_messages=None, selected_agent_contract=None, defer_until_stream=False):
            return "run-ref-normalized-tool-event"

        async def stream_turn_events(self, *, session_id, turn_ref, sandbox_id=None, workspace_path=None):
            assert session_id == "sess-apply-fail"
            assert turn_ref == "run-ref-normalized-tool-event"
            assert workspace_path == "/workspace/apply-fail"
            yield {
                "event": "tool.completed",
                "payload": {
                    "tool": "read",
                    "output": {"error": "permission denied", "code": "EACCES"},
                },
            }
            yield {"event": "run.completed", "payload": {"status": "completed"}}

    engine = OpenCodePublishedAppCodingAgentEngine(db=db_session, client=_FakeOpenCodeClient())
    events = [event async for event in engine.stream(ctx=SimpleNamespace(app=app, run=run, resume_payload=None))]

    assert any(item.event == "tool.failed" for item in events)
    assert run.status == RunStatus.completed
