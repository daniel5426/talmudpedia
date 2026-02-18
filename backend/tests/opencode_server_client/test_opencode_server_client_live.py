import os
from uuid import uuid4

import pytest

from app.services.opencode_server_client import OpenCodeServerClient, OpenCodeServerClientConfig


def _env_truthy(name: str, default: str = "0") -> bool:
    raw = (os.getenv(name) or default).strip().lower()
    return raw in {"1", "true", "yes", "on"}


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _env_truthy("OPENCODE_LIVE_TEST"),
    reason="Set OPENCODE_LIVE_TEST=1 to run against a live OpenCode server.",
)
async def test_live_opencode_roundtrip_message():
    base_url = (os.getenv("APPS_CODING_AGENT_OPENCODE_BASE_URL") or "http://127.0.0.1:8788").strip()
    client = OpenCodeServerClient(
        OpenCodeServerClientConfig(
            enabled=True,
            base_url=base_url,
            api_key=(os.getenv("APPS_CODING_AGENT_OPENCODE_API_KEY") or "").strip() or None,
            request_timeout_seconds=float((os.getenv("APPS_CODING_AGENT_OPENCODE_REQUEST_TIMEOUT_SECONDS") or "40").strip()),
            connect_timeout_seconds=float((os.getenv("APPS_CODING_AGENT_OPENCODE_CONNECT_TIMEOUT_SECONDS") or "5").strip()),
            health_cache_seconds=3,
        )
    )
    await client.ensure_healthy(force=True)

    model_id = (os.getenv("OPENCODE_LIVE_MODEL_ID") or "").strip()
    run_ref = await client.start_run(
        run_id=str(uuid4()),
        app_id="live-test-app",
        sandbox_id="live-test-sandbox",
        workspace_path=os.getenv("OPENCODE_LIVE_WORKSPACE_PATH", "/tmp"),
        model_id=model_id,
        prompt="Reply with exactly: OK",
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
    )

    events = [event async for event in client.stream_run_events(run_ref=run_ref)]
    assert events, "Expected at least one event from OpenCode."
    assert any(item.get("event") == "assistant.delta" for item in events), f"Unexpected events: {events!r}"
    assert any(item.get("event") == "run.completed" for item in events), f"Unexpected events: {events!r}"


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _env_truthy("OPENCODE_LIVE_TEST") or not _env_truthy("OPENCODE_LIVE_FULL_TASK"),
    reason="Set OPENCODE_LIVE_TEST=1 and OPENCODE_LIVE_FULL_TASK=1 for end-to-end filesystem task validation.",
)
async def test_live_opencode_edits_workspace_file(tmp_path):
    base_url = (os.getenv("APPS_CODING_AGENT_OPENCODE_BASE_URL") or "http://127.0.0.1:8788").strip()
    client = OpenCodeServerClient(
        OpenCodeServerClientConfig(
            enabled=True,
            base_url=base_url,
            api_key=(os.getenv("APPS_CODING_AGENT_OPENCODE_API_KEY") or "").strip() or None,
            request_timeout_seconds=float((os.getenv("APPS_CODING_AGENT_OPENCODE_REQUEST_TIMEOUT_SECONDS") or "60").strip()),
            connect_timeout_seconds=float((os.getenv("APPS_CODING_AGENT_OPENCODE_CONNECT_TIMEOUT_SECONDS") or "5").strip()),
            health_cache_seconds=3,
        )
    )
    await client.ensure_healthy(force=True)

    model_id = (os.getenv("OPENCODE_LIVE_MODEL_ID") or "").strip()
    target = tmp_path / "opencode-smoke.txt"
    prompt = (
        "In the workspace root, edit ./opencode-smoke.txt and replace `status=before` with `status=after`.\n"
        "Use tools to make the change and verify it.\n"
        "Then reply exactly: done"
    )
    max_attempts = 2
    last_events: list[dict[str, object]] = []
    for _ in range(max_attempts):
        target.write_text("status=before\n", encoding="utf-8")
        run_ref = await client.start_run(
            run_id=str(uuid4()),
            app_id="live-test-app",
            sandbox_id="live-test-sandbox",
            workspace_path=str(tmp_path),
            model_id=model_id,
            prompt=prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        events = [event async for event in client.stream_run_events(run_ref=run_ref)]
        last_events = [item for item in events if isinstance(item, dict)]
        if (
            any(item.get("event") == "tool.started" for item in last_events)
            and any(item.get("event") == "tool.completed" for item in last_events)
            and any(item.get("event") == "assistant.delta" for item in last_events)
            and any(item.get("event") == "run.completed" for item in last_events)
            and "status=after" in target.read_text(encoding="utf-8")
        ):
            return

    assert False, f"Expected file edit + completion after {max_attempts} attempts. events={last_events!r}"
