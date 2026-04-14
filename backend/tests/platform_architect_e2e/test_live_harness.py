from __future__ import annotations

import json
import os
from pathlib import Path

from scripts.platform_architect_live_harness import _seed_local_dev_auth_defaults
from app.services.platform_architect_live_harness import (
    ArchitectLiveHarnessConfig,
    ArchitectLiveRunBundle,
    ArchitectLiveTask,
    PlatformArchitectLiveHarness,
    load_live_tasks,
    read_processed_task_ids,
    write_processed_task_ids,
    write_run_bundle,
    write_run_bundle_summary,
)


def test_live_harness_config_reads_new_env_names(monkeypatch):
    monkeypatch.setenv("PLATFORM_ARCHITECT_BASE_URL", "http://localhost:9999")
    monkeypatch.setenv("PLATFORM_ARCHITECT_API_KEY", "token-123")
    monkeypatch.setenv("PLATFORM_ARCHITECT_TENANT_ID", "tenant-123")
    monkeypatch.setenv("PLATFORM_ARCHITECT_AGENT_ID", "agent-123")
    monkeypatch.setenv("PLATFORM_ARCHITECT_TIMEOUT_SECONDS", "123")
    config = ArchitectLiveHarnessConfig.from_env()
    assert config.base_url == "http://localhost:9999"
    assert config.api_key == "token-123"
    assert config.tenant_id == "tenant-123"
    assert config.architect_agent_id == "agent-123"
    assert config.timeout_s == 123


def test_live_harness_config_uses_port_for_default_base_url(monkeypatch):
    monkeypatch.delenv("PLATFORM_ARCHITECT_BASE_URL", raising=False)
    monkeypatch.delenv("TEST_BASE_URL", raising=False)
    monkeypatch.setenv("PORT", "8026")
    monkeypatch.setenv("PLATFORM_ARCHITECT_API_KEY", "token-123")
    monkeypatch.setenv("PLATFORM_ARCHITECT_TENANT_ID", "tenant-123")
    config = ArchitectLiveHarnessConfig.from_env()
    assert config.base_url == "http://localhost:8026"


def test_load_live_tasks_supports_json_array(tmp_path: Path):
    task_file = tmp_path / "tasks.json"
    task_file.write_text(
        json.dumps(
            [
                {"id": "t1", "prompt": "first"},
                {"id": "t2", "prompt": "second", "runtime_context": {"x": 1}, "timeout_s": 99},
            ]
        ),
        encoding="utf-8",
    )
    tasks = load_live_tasks(task_file)
    assert [task.id for task in tasks] == ["t1", "t2"]
    assert tasks[1].runtime_context == {"x": 1}
    assert tasks[1].timeout_s == 99


def test_load_live_tasks_supports_jsonl(tmp_path: Path):
    task_file = tmp_path / "tasks.jsonl"
    task_file.write_text(
        "\n".join(
            [
                json.dumps({"id": "t1", "prompt": "first"}),
                json.dumps({"prompt": "second"}),
            ]
        ),
        encoding="utf-8",
    )
    tasks = load_live_tasks(task_file)
    assert tasks[0].id == "t1"
    assert tasks[1].id == "task-2"
    assert tasks[1].prompt == "second"


def test_write_run_bundle_and_processed_state(tmp_path: Path):
    bundle = ArchitectLiveRunBundle(
        task_id="Create Agent",
        prompt="create an agent",
        run_id="run-123",
        agent_id="agent-123",
        status="completed",
        started_at="2026-04-15T00:00:00+00:00",
        ended_at="2026-04-15T00:00:03+00:00",
        runtime_context={"architect_mode": "full_access"},
        final_run={"status": "completed"},
        run_tree={"nodes": []},
        run_events=[{"event": "tool.started", "data": {"tool": "platform-agents"}}],
        assistant_text="done",
        event_summary={
            "event_names": {"tool.started": 1, "tool.completed": 1},
            "tool_starts": [{"tool": "platform-agents", "span_id": "span-1", "input": {"action": "agents.list"}}],
            "tool_ends": [{"tool": "platform-agents", "span_id": "span-1", "output": {"items": []}, "error": None, "event": "tool.completed"}],
        },
    )
    output_path = write_run_bundle(bundle, output_dir=tmp_path)
    summary_path = write_run_bundle_summary(bundle, output_dir=tmp_path)
    assert output_path.exists()
    assert summary_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["task_id"] == "Create Agent"
    assert payload["run_id"] == "run-123"
    assert summary_payload["task_id"] == "Create Agent"
    assert summary_payload["event_stats"]["event_count"] == 1
    assert summary_payload["tool_calls"][0]["tool"] == "platform-agents"

    state_path = tmp_path / "processed.json"
    write_processed_task_ids(state_path, {"b", "a"})
    assert read_processed_task_ids(state_path) == {"a", "b"}


def test_seed_local_dev_auth_defaults_mints_token(monkeypatch):
    monkeypatch.delenv("PLATFORM_ARCHITECT_API_KEY", raising=False)
    monkeypatch.delenv("TEST_API_KEY", raising=False)
    monkeypatch.delenv("PLATFORM_ARCHITECT_TENANT_ID", raising=False)
    monkeypatch.delenv("TEST_TENANT_ID", raising=False)

    monkeypatch.setattr(
        "scripts.platform_architect_live_harness._mint_local_dev_jwt",
        lambda: ("jwt-123", "tenant-123"),
    )

    _seed_local_dev_auth_defaults()

    assert os.getenv("TEST_API_KEY") == "jwt-123"
    assert os.getenv("TEST_TENANT_ID") == "tenant-123"


def test_start_run_defaults_architect_mode_and_execution_mode():
    class Harness(PlatformArchitectLiveHarness):
        def resolve_architect_agent_id(self) -> str:
            return "agent-123"

        def _request(self, method: str, path: str, *, json_body=None, timeout: int = 30):
            assert method == "POST"
            assert path == "/agents/agent-123/run"
            assert json_body["context"]["architect_mode"] == "full_access"
            assert json_body["context"]["execution_mode"] == "debug"
            return {"run_id": "run-123"}

    harness = Harness(
        ArchitectLiveHarnessConfig(
            base_url="http://localhost:8026",
            api_key="token-123",
            tenant_id="tenant-123",
        )
    )
    assert harness.start_run(prompt="hello") == "run-123"
