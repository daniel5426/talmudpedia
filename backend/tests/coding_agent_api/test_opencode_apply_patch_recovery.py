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
                "coding_run_sandbox_id": "sandbox-apply-fail",
                "coding_run_sandbox_workspace_path": "/workspace/apply-fail",
                "resolved_model_id": "openai/gpt-5",
            },
        },
    )


@pytest.mark.asyncio
async def test_opencode_engine_accepts_apply_patch_completion_without_applied_files(db_session):
    run = _opencode_run()
    app = SimpleNamespace(id=uuid4())

    class _FakeOpenCodeClient:
        async def start_run(self, *, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, messages):
            return "run-ref-apply-fail"

        async def stream_run_events(self, *, run_ref):
            assert run_ref == "run-ref-apply-fail"
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
        async def start_run(self, *, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, messages):
            return "run-ref-edit-recover"

        async def stream_run_events(self, *, run_ref):
            assert run_ref == "run-ref-edit-recover"
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
        async def start_run(self, *, run_id, app_id, sandbox_id, workspace_path, model_id, prompt, messages):
            return "run-ref-disabled-strict"

        async def stream_run_events(self, *, run_ref):
            assert run_ref == "run-ref-disabled-strict"
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
