from __future__ import annotations

import json

import httpx
import pytest

from app.services.published_app_draft_dev_runtime_client import (
    PublishedAppDraftDevRuntimeClient,
    PublishedAppDraftDevRuntimeClientConfig,
    PublishedAppDraftDevRuntimeClientError,
)


def _client() -> PublishedAppDraftDevRuntimeClient:
    return PublishedAppDraftDevRuntimeClient(
        PublishedAppDraftDevRuntimeClientConfig(
            controller_url="http://sandbox-controller.local",
            controller_token="dev-token",
            request_timeout_seconds=15,
            local_preview_base_url="http://127.0.0.1:5173",
            embedded_local_enabled=False,
        )
    )


@pytest.mark.asyncio
async def test_stream_opencode_events_uses_no_read_timeout_by_default(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200
        reason_phrase = "OK"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aread(self) -> bytes:
            return b""

        async def aiter_lines(self):
            yield f"data: {json.dumps({'event': 'run.completed', 'payload': {'status': 'completed'}})}"

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, headers=None, params=None):
            captured["method"] = method
            captured["url"] = url
            captured["params"] = params
            return _FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    monkeypatch.delenv("APPS_DRAFT_DEV_CONTROLLER_STREAM_READ_TIMEOUT_SECONDS", raising=False)

    client = _client()
    events = [item async for item in client.stream_opencode_events(sandbox_id="sandbox-1", run_ref="run-ref-1")]
    assert events and events[0]["event"] == "run.completed"

    timeout = captured.get("timeout")
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.read is None


@pytest.mark.asyncio
async def test_stream_opencode_events_reports_exception_class_when_message_empty(monkeypatch: pytest.MonkeyPatch):
    class _SilentStreamError(Exception):
        def __str__(self) -> str:
            return ""

    class _FakeResponse:
        async def __aenter__(self):
            raise _SilentStreamError()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, headers=None, params=None):
            return _FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    client = _client()
    with pytest.raises(PublishedAppDraftDevRuntimeClientError) as exc_info:
        _ = [item async for item in client.stream_opencode_events(sandbox_id="sandbox-1", run_ref="run-ref-1")]
    assert "SilentStreamError" in str(exc_info.value)
