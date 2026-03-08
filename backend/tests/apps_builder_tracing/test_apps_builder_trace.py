from __future__ import annotations

import json

from app.services.apps_builder_trace import apps_builder_trace
from app.services.published_app_coding_pipeline_trace import pipeline_trace


def _read_lines(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_apps_builder_trace_writes_jsonl(monkeypatch, tmp_path):
    trace_path = tmp_path / "apps-builder-trace.jsonl"
    monkeypatch.setenv("APPS_BUILDER_TRACE_ENABLED", "1")
    monkeypatch.setenv("APPS_BUILDER_TRACE_FILE", str(trace_path))

    apps_builder_trace(
        "sandbox.start.requested",
        domain="sandbox.e2b",
        app_id="app-1",
        session_id="session-1",
    )

    events = _read_lines(trace_path)
    assert len(events) == 1
    assert events[0]["event"] == "sandbox.start.requested"
    assert events[0]["domain"] == "sandbox.e2b"
    assert events[0]["app_id"] == "app-1"
    assert events[0]["session_id"] == "session-1"
    assert events[0]["pid"] > 0


def test_pipeline_trace_is_mirrored_to_apps_builder_trace(monkeypatch, tmp_path):
    shared_trace_path = tmp_path / "apps-builder-trace.jsonl"
    legacy_trace_path = tmp_path / "coding-agent-trace.jsonl"
    monkeypatch.setenv("APPS_BUILDER_TRACE_ENABLED", "1")
    monkeypatch.setenv("APPS_BUILDER_TRACE_FILE", str(shared_trace_path))
    monkeypatch.setenv("APPS_CODING_AGENT_PIPELINE_TRACE_ENABLED", "1")
    monkeypatch.setenv("APPS_CODING_AGENT_PIPELINE_TRACE_FILE", str(legacy_trace_path))

    pipeline_trace(
        "runtime.create_run.started",
        pipeline="runtime",
        app_id="app-1",
        run_id="run-1",
    )

    shared_events = _read_lines(shared_trace_path)
    legacy_events = _read_lines(legacy_trace_path)
    assert len(shared_events) == 1
    assert shared_events[0]["event"] == "runtime.create_run.started"
    assert shared_events[0]["domain"] == "coding_agent.runtime"
    assert shared_events[0]["run_id"] == "run-1"
    assert len(legacy_events) == 1
    assert legacy_events[0]["event"] == "runtime.create_run.started"
    assert legacy_events[0]["pipeline"] == "runtime"
