from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "paused"}
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_OUTPUT_DIR = "backend/artifacts/platform_architect_live"
DEFAULT_TIMEOUT_SECONDS = 300


def _load_local_env_files() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return

    repo_root = Path(__file__).resolve().parents[3]
    for candidate in (repo_root / "backend" / ".env", repo_root / ".env"):
        if candidate.exists():
            load_dotenv(candidate, override=False)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _sanitize_name(value: str, *, fallback: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return fallback
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-")
    return cleaned or fallback


def _extract_assistant_text(run_payload: dict[str, Any]) -> str:
    result = run_payload.get("result")
    if not isinstance(result, dict):
        return ""

    output = result.get("output")
    if isinstance(output, dict):
        text = output.get("text")
        if isinstance(text, str) and text.strip():
            return text

    messages = result.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if not isinstance(message, dict):
                continue
            if str(message.get("role") or "").lower() not in {"assistant", "ai"}:
                continue
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content

    last_output = result.get("last_agent_output")
    return str(last_output or "")


def _summarize_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    tool_starts: list[dict[str, Any]] = []
    tool_ends: list[dict[str, Any]] = []
    event_names: dict[str, int] = {}

    for item in events:
        if not isinstance(item, dict):
            continue
        event_name = str(item.get("event") or item.get("type") or "").strip()
        if event_name:
            event_names[event_name] = event_names.get(event_name, 0) + 1
        name = str(item.get("name") or "")
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        if event_name in {"on_tool_start", "tool.started"}:
            tool_starts.append(
                {
                    "tool": name or data.get("tool") or data.get("name"),
                    "span_id": data.get("span_id"),
                    "input": data.get("input"),
                }
            )
        if event_name in {"on_tool_end", "tool.completed", "tool.failed"}:
            tool_ends.append(
                {
                    "tool": name or data.get("tool") or data.get("name"),
                    "span_id": data.get("span_id"),
                    "output": data.get("output"),
                    "error": data.get("error"),
                    "event": event_name,
                }
            )

    return {
        "event_names": event_names,
        "tool_starts": tool_starts,
        "tool_ends": tool_ends,
    }


def _compact_value(value: Any, *, max_chars: int = 240, max_items: int = 8, depth: int = 0) -> Any:
    if depth >= 3:
        if isinstance(value, (dict, list)):
            return f"<{type(value).__name__}>"
        return value
    if isinstance(value, str):
        text = value.strip()
        return text if len(text) <= max_chars else f"{text[:max_chars]}...[truncated]"
    if isinstance(value, list):
        items = [_compact_value(item, max_chars=max_chars, max_items=max_items, depth=depth + 1) for item in value[:max_items]]
        if len(value) > max_items:
            items.append(f"...[{len(value) - max_items} more items]")
        return items
    if isinstance(value, dict):
        keys = list(value.keys())
        compacted = {
            str(key): _compact_value(value[key], max_chars=max_chars, max_items=max_items, depth=depth + 1)
            for key in keys[:max_items]
        }
        if len(keys) > max_items:
            compacted["__truncated_keys__"] = len(keys) - max_items
        return compacted
    return value


def _summarize_run_tree(run_tree: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(run_tree, dict):
        return {}
    tree = run_tree.get("tree")
    summary: dict[str, Any] = {
        "root_run_id": run_tree.get("root_run_id"),
        "node_count": run_tree.get("node_count"),
    }
    if isinstance(tree, dict):
        children = tree.get("children")
        summary["root"] = {
            "run_id": tree.get("run_id"),
            "status": tree.get("status"),
            "node_id": tree.get("node_id"),
            "child_count": len(children) if isinstance(children, list) else 0,
        }
    return summary


@dataclass(frozen=True)
class ArchitectLiveHarnessConfig:
    base_url: str
    api_key: str
    organization_id: str
    architect_agent_id: str | None = None
    output_dir: str = DEFAULT_OUTPUT_DIR
    timeout_s: int = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> "ArchitectLiveHarnessConfig":
        _load_local_env_files()
        default_base_url = DEFAULT_BASE_URL
        port = str(os.getenv("PORT") or "").strip()
        if port.isdigit():
            default_base_url = f"http://localhost:{port}"
        base_url = (
            os.getenv("PLATFORM_ARCHITECT_BASE_URL")
            or os.getenv("TEST_BASE_URL")
            or default_base_url
        ).rstrip("/")
        api_key = os.getenv("PLATFORM_ARCHITECT_API_KEY") or os.getenv("TEST_API_KEY") or ""
        organization_id= os.getenv("PLATFORM_ARCHITECT_TENANT_ID") or os.getenv("TEST_ORGANIZATION_ID") or ""
        architect_agent_id = os.getenv("PLATFORM_ARCHITECT_AGENT_ID") or None
        output_dir = os.getenv("PLATFORM_ARCHITECT_OUTPUT_DIR") or DEFAULT_OUTPUT_DIR
        timeout_raw = os.getenv("PLATFORM_ARCHITECT_TIMEOUT_SECONDS") or str(DEFAULT_TIMEOUT_SECONDS)
        timeout_s = int(timeout_raw)
        if not api_key:
            raise RuntimeError("Missing PLATFORM_ARCHITECT_API_KEY or TEST_API_KEY")
        if not organization_id:
            raise RuntimeError("Missing PLATFORM_ARCHITECT_TENANT_ID or TEST_ORGANIZATION_ID")
        return cls(
            base_url=base_url,
            api_key=api_key,
            organization_id=organization_id,
            architect_agent_id=architect_agent_id,
            output_dir=output_dir,
            timeout_s=timeout_s,
        )


@dataclass(frozen=True)
class ArchitectLiveTask:
    id: str
    prompt: str
    runtime_context: dict[str, Any] = field(default_factory=dict)
    timeout_s: int | None = None
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, fallback_index: int) -> "ArchitectLiveTask":
        task_id = str(payload.get("id") or f"task-{fallback_index}")
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            raise ValueError(f"Task {task_id} missing prompt")
        runtime_context = payload.get("runtime_context") if isinstance(payload.get("runtime_context"), dict) else {}
        timeout_value = payload.get("timeout_s")
        timeout_s = int(timeout_value) if timeout_value is not None else None
        tags = [str(item) for item in (payload.get("tags") or []) if str(item or "").strip()]
        return cls(id=task_id, prompt=prompt, runtime_context=runtime_context, timeout_s=timeout_s, tags=tags)


@dataclass(frozen=True)
class ArchitectLiveRunBundle:
    task_id: str
    prompt: str
    run_id: str
    agent_id: str
    status: str
    started_at: str
    ended_at: str
    runtime_context: dict[str, Any]
    final_run: dict[str, Any]
    run_tree: dict[str, Any]
    run_events: list[dict[str, Any]]
    assistant_text: str
    event_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_summary_dict(self) -> dict[str, Any]:
        final_run = self.final_run if isinstance(self.final_run, dict) else {}
        lineage = final_run.get("lineage") if isinstance(final_run.get("lineage"), dict) else {}
        return {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "runtime_context": _compact_value(self.runtime_context),
            "assistant_text": self.assistant_text,
            "final_run": {
                "id": final_run.get("id"),
                "status": final_run.get("status"),
                "error": _compact_value(final_run.get("error")),
                "lineage": _compact_value(lineage),
                "context_window": _compact_value(final_run.get("context_window")),
                "run_usage": _compact_value(final_run.get("run_usage")),
            },
            "run_tree": _summarize_run_tree(self.run_tree),
            "event_stats": {
                "event_count": len(self.run_events or []),
                "event_names": (self.event_summary or {}).get("event_names") or {},
            },
            "tool_calls": [
                {
                    "tool": end.get("tool") or start.get("tool"),
                    "span_id": end.get("span_id") or start.get("span_id"),
                    "input": _compact_value(start.get("input")),
                    "output": _compact_value(end.get("output")),
                    "error": _compact_value(end.get("error")),
                    "event": end.get("event"),
                }
                for start, end in zip(
                    (self.event_summary or {}).get("tool_starts") or [],
                    (self.event_summary or {}).get("tool_ends") or [],
                )
            ],
        }


class PlatformArchitectLiveHarness:
    def __init__(self, config: ArchitectLiveHarnessConfig):
        self.config = config

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "X-Organization-ID": self.config.organization_id,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, *, json_body: Any | None = None, timeout: int = 30) -> Any:
        response = requests.request(
            method=method.upper(),
            url=f"{self.config.base_url}{path}",
            headers=self.headers,
            json=json_body,
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            return payload["data"]
        return payload

    def resolve_architect_agent_id(self) -> str:
        if self.config.architect_agent_id:
            return str(self.config.architect_agent_id)
        try:
            payload = self._request("GET", "/agents?limit=100&view=summary")
            items = payload.get("items") if isinstance(payload, dict) else None
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get("system_key") == "platform_architect" and item.get("id"):
                        return str(item["id"])
        except Exception:
            pass
        return self._resolve_architect_agent_id_from_db()

    def _resolve_architect_agent_id_from_db(self) -> str:
        from sqlalchemy import select
        from uuid import UUID

        from app.db.postgres.engine import sessionmaker
        from app.db.postgres.models.agents import Agent

        async def _query() -> str | None:
            async with sessionmaker() as db:
                result = await db.execute(
                    select(Agent.id).where(
                        Agent.system_key == "platform_architect",
                        Agent.organization_id == UUID(str(self.config.organization_id)),
                    )
                )
                value = result.scalar_one_or_none()
                return str(value) if value else None

        import asyncio

        try:
            agent_id = asyncio.run(_query())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                agent_id = loop.run_until_complete(_query())
            finally:
                loop.close()
        if not agent_id:
            raise RuntimeError("platform-architect agent not found via HTTP or DB system_key lookup")
        return agent_id

    def start_run(self, *, prompt: str, runtime_context: dict[str, Any] | None = None, agent_id: str | None = None) -> str:
        target_agent_id = agent_id or self.resolve_architect_agent_id()
        context_payload = dict(runtime_context or {})
        context_payload.setdefault("architect_mode", "full_access")
        context_payload.setdefault("execution_mode", "debug")
        payload = self._request(
            "POST",
            f"/agents/{target_agent_id}/run",
            json_body={"input": prompt, "messages": [], "context": context_payload},
        )
        run_id = payload.get("run_id") or payload.get("id")
        if not run_id:
            raise RuntimeError(f"Missing run_id in architect run response: {payload}")
        return str(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/agents/runs/{run_id}")
        return payload if isinstance(payload, dict) else {}

    def get_run_tree(self, run_id: str) -> dict[str, Any]:
        try:
            payload = self._request("GET", f"/agents/runs/{run_id}/tree")
        except requests.HTTPError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def get_run_events(self, run_id: str, *, after_sequence: int | None = None, limit: int = 1000) -> list[dict[str, Any]]:
        query = f"?limit={limit}"
        if after_sequence is not None:
            query += f"&after_sequence={after_sequence}"
        payload = self._request("GET", f"/agents/runs/{run_id}/events{query}")
        events = payload.get("events") if isinstance(payload, dict) else None
        return list(events or []) if isinstance(events, list) else []

    def wait_for_terminal(self, run_id: str, *, timeout_s: int) -> dict[str, Any]:
        started = time.time()
        last_payload: dict[str, Any] = {}
        while time.time() - started < timeout_s:
            last_payload = self.get_run(run_id)
            status = str(last_payload.get("status") or "").strip().lower()
            if status in TERMINAL_RUN_STATUSES:
                return last_payload
            time.sleep(1.0)
        raise TimeoutError(f"Run {run_id} did not reach terminal state within {timeout_s}s")

    def run_task(self, task: ArchitectLiveTask) -> ArchitectLiveRunBundle:
        agent_id = self.resolve_architect_agent_id()
        started = _now_utc()
        run_id = self.start_run(prompt=task.prompt, runtime_context=task.runtime_context, agent_id=agent_id)
        final_run = self.wait_for_terminal(run_id, timeout_s=task.timeout_s or self.config.timeout_s)
        events = self.get_run_events(run_id)
        ended = _now_utc()
        return ArchitectLiveRunBundle(
            task_id=task.id,
            prompt=task.prompt,
            run_id=run_id,
            agent_id=agent_id,
            status=str(final_run.get("status") or ""),
            started_at=started.isoformat(),
            ended_at=ended.isoformat(),
            runtime_context=dict(task.runtime_context),
            final_run=final_run,
            run_tree=self.get_run_tree(run_id),
            run_events=events,
            assistant_text=_extract_assistant_text(final_run),
            event_summary=_summarize_events(events),
        )


def load_live_tasks(path: str | Path) -> list[ArchitectLiveTask]:
    source = Path(path)
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return []
    tasks: list[ArchitectLiveTask] = []
    if text.startswith("["):
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise ValueError("Task file JSON must be an array")
        for idx, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"Task array item #{idx} must be an object")
            tasks.append(ArchitectLiveTask.from_payload(item, fallback_index=idx))
        return tasks
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        item = json.loads(stripped)
        if not isinstance(item, dict):
            raise ValueError(f"Task line #{idx} must be a JSON object")
        tasks.append(ArchitectLiveTask.from_payload(item, fallback_index=idx))
    return tasks


def write_run_bundle(bundle: ArchitectLiveRunBundle, *, output_dir: str | Path) -> Path:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromisoformat(bundle.started_at).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{stamp}__{_sanitize_name(bundle.task_id, fallback='task')}__{_sanitize_name(bundle.status, fallback='status')}.json"
    target = target_dir / filename
    target.write_text(json.dumps(bundle.to_dict(), indent=2, ensure_ascii=True), encoding="utf-8")
    return target


def write_run_bundle_summary(bundle: ArchitectLiveRunBundle, *, output_dir: str | Path) -> Path:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromisoformat(bundle.started_at).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{stamp}__{_sanitize_name(bundle.task_id, fallback='task')}__{_sanitize_name(bundle.status, fallback='status')}__summary.json"
    target = target_dir / filename
    target.write_text(json.dumps(bundle.to_summary_dict(), indent=2, ensure_ascii=True), encoding="utf-8")
    return target


def read_processed_task_ids(path: str | Path) -> set[str]:
    target = Path(path)
    if not target.exists():
        return set()
    text = target.read_text(encoding="utf-8").strip()
    if not text:
        return set()
    payload = json.loads(text)
    if not isinstance(payload, list):
        raise ValueError("Processed task state file must be a JSON array")
    return {str(item) for item in payload}


def write_processed_task_ids(path: str | Path, task_ids: set[str]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(sorted(task_ids), indent=2, ensure_ascii=True), encoding="utf-8")
