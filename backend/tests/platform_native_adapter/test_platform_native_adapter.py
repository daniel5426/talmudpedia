from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.services import platform_native_tools


@pytest.mark.asyncio
async def test_native_adapter_passes_runtime_context_and_hides_debug_meta(monkeypatch):
    captured = {}

    async def fake_handler(runtime):
        captured["builtin_key"] = runtime.builtin_key
        captured["action"] = runtime.action
        captured["organization_id"] = runtime.runtime_context.get("organization_id")
        return {"status": "ok"}

    class _FakeSession:
        async def __aenter__(self):
            return object()
        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    monkeypatch.setitem(platform_native_tools._ACTION_HANDLERS, "agents.list", fake_handler)

    result = await platform_native_tools.platform_native_platform_agents(
        {
            "action": "agents.list",
            "payload": {"limit": 5},
            "__tool_runtime_context__": {"organization_id": "tenant-1", "scopes": ["*"]},
        }
    )

    assert result["errors"] == []
    assert result["result"]["status"] == "ok"
    assert captured == {"builtin_key": "platform-agents", "action": "agents.list", "organization_id": "tenant-1"}
    assert "trace_version" not in result["meta"]


@pytest.mark.asyncio
async def test_native_adapter_rejects_removed_alias_actions(monkeypatch):
    class _FakeSession:
        async def __aenter__(self):
            return object()
        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())

    result = await platform_native_tools.platform_native_platform_agents(
        {
            "action": "create_agent",
            "payload": {},
            "__tool_runtime_context__": {"organization_id": "tenant-1", "scopes": ["*"]},
        }
    )

    assert result["errors"][0]["code"] == "SCOPE_DENIED"
    assert result["action"] == "create_agent"


@pytest.mark.asyncio
async def test_native_rag_create_job_dispatches_background_execution(monkeypatch):
    job_id = uuid4()
    organization_id = uuid4()
    user_id = uuid4()
    captured = {}
    original_create_task = asyncio.create_task
    scheduled: list[asyncio.Task] = []

    class _FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_create_job(self, *, ctx, executable_pipeline_id, input_params):
        captured["organization_id"] = str(ctx.organization_id)
        captured["executable_pipeline_id"] = str(executable_pipeline_id)
        captured["input_params"] = input_params
        return {
            "operation": {
                "id": str(job_id),
                "kind": "pipeline_job",
                "status": "queued",
            }
        }

    async def fake_dispatch_pipeline_job_background(dispatched_job_id, *, artifact_queue_class):
        captured["dispatched_job_id"] = str(dispatched_job_id)
        captured["artifact_queue_class"] = artifact_queue_class

    def fake_create_task(coro):
        task = original_create_task(coro)
        scheduled.append(task)
        return task

    monkeypatch.setattr(platform_native_tools, "get_session", lambda: _FakeSession())
    monkeypatch.setattr("app.services.platform_native.rag.RagAdminService.create_job", fake_create_job)
    monkeypatch.setattr(
        "app.services.platform_native.rag.dispatch_pipeline_job_background",
        fake_dispatch_pipeline_job_background,
    )
    monkeypatch.setattr("app.services.platform_native.rag.asyncio.create_task", fake_create_task)

    result = await platform_native_tools.platform_native_platform_rag(
        {
            "action": "rag.create_job",
            "payload": {
                "executable_pipeline_id": str(uuid4()),
                "input_params": {"query_input_1": {"text": "Explain Gemara"}},
            },
            "__tool_runtime_context__": {"organization_id": str(organization_id), "user_id": str(user_id), "scopes": ["*"]},
        }
    )
    if scheduled:
        await asyncio.gather(*scheduled)

    assert result["errors"] == []
    assert result["result"]["operation"]["id"] == str(job_id)
    assert captured["organization_id"] == str(organization_id)
    assert captured["artifact_queue_class"] == "artifact_prod_background"
    assert captured["dispatched_job_id"] == str(job_id)
