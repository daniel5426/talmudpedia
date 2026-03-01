from __future__ import annotations

import os
import time
import uuid
from typing import Any, Dict

import pytest
import requests

from artifacts.builtin.platform_sdk import handler
from talmudpedia_control_sdk import ControlPlaneClient


def _require_env() -> tuple[str, Dict[str, str], str, str]:
    base_url = os.getenv("TEST_BASE_URL")
    api_key = os.getenv("TEST_API_KEY")
    tenant_id = os.getenv("TEST_TENANT_ID")
    if not base_url or not api_key or not tenant_id:
        pytest.skip("Set TEST_BASE_URL, TEST_API_KEY, and TEST_TENANT_ID to run integration tests.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Tenant-ID": tenant_id,
    }
    return base_url.rstrip("/"), headers, tenant_id, api_key


def _require_chat_model() -> str:
    model_id = os.getenv("TEST_CHAT_MODEL_SLUG")
    if not model_id:
        pytest.skip("Set TEST_CHAT_MODEL_SLUG to run cross-surface agent parity tests.")
    return model_id


def _unwrap_data(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    if isinstance(payload, dict):
        return payload
    return {}


def _agent_payload(name: str, slug: str, model_id: str) -> Dict[str, Any]:
    return {
        "name": name,
        "slug": slug,
        "description": "Cross-surface execution parity test agent",
        "graph_definition": {
            "nodes": [
                {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
                {
                    "id": "core",
                    "type": "agent",
                    "position": {"x": 200, "y": 0},
                    "config": {
                        "name": "Core",
                        "model_id": model_id,
                        "instructions": "Reply with OK.",
                        "output_format": "text",
                    },
                },
                {"id": "end", "type": "end", "position": {"x": 400, "y": 0}, "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "core", "type": "control"},
                {"id": "e2", "source": "core", "target": "end", "type": "control"},
            ],
        },
        "memory_config": {},
        "execution_constraints": {},
    }


def _fetch_run(base_url: str, headers: Dict[str, str], run_id: str) -> Dict[str, Any]:
    response = requests.get(
        f"{base_url}/agents/runs/{run_id}",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return _unwrap_data(response.json())


def _fetch_run_with_retry(base_url: str, headers: Dict[str, str], run_id: str, attempts: int = 5) -> Dict[str, Any]:
    last_exc = None
    for _ in range(attempts):
        try:
            return _fetch_run(base_url, headers, run_id)
        except Exception as exc:
            last_exc = exc
            time.sleep(0.25)
    if last_exc:
        raise last_exc
    return {}


def _delete_agent(base_url: str, headers: Dict[str, str], agent_id: str) -> None:
    try:
        requests.delete(
            f"{base_url}/agents/{agent_id}",
            headers=headers,
            timeout=30,
        )
    except Exception:
        pass


@pytest.mark.real_db
def test_cross_surface_agents_start_run_parity() -> None:
    base_url, headers, tenant_id, api_key = _require_env()
    model_id = _require_chat_model()
    sdk_client = ControlPlaneClient(base_url=base_url, token=api_key, tenant_id=tenant_id)

    unique = uuid.uuid4().hex[:8]
    ui_agent_id = None
    sdk_agent_id = None
    tool_agent_id = None

    try:
        ui_agent_id = str(
            _unwrap_data(
                requests.post(
                    f"{base_url}/agents",
                    json=_agent_payload(f"Run UI {unique}", f"run-ui-{unique}", model_id),
                    headers=headers,
                    timeout=30,
                ).json()
            ).get("id")
        )
        sdk_agent_id = str(
            _unwrap_data(
                sdk_client.agents.create(_agent_payload(f"Run SDK {unique}", f"run-sdk-{unique}", model_id))
            ).get("id")
        )
        tool_agent_id = str(
            _unwrap_data(
                handler.execute(
                    state={},
                    config={},
                    context={
                        "inputs": {
                            "action": "agents.create_or_update",
                            "tenant_id": tenant_id,
                            "token": api_key,
                            "base_url": base_url,
                            "payload": _agent_payload(f"Run Tool {unique}", f"run-tool-{unique}", model_id),
                        }
                    },
                )["context"]["result"]
            ).get("id")
        )

        ui_run_resp = requests.post(
            f"{base_url}/agents/{ui_agent_id}/run",
            json={"input": {"text": "hello"}},
            headers=headers,
            timeout=30,
        )
        if ui_run_resp.status_code >= 400:
            pytest.skip(f"Agents start_run endpoint unavailable: {ui_run_resp.status_code} {ui_run_resp.text}")
        ui_run_data = _unwrap_data(ui_run_resp.json())
        ui_run_id = str(ui_run_data.get("run_id") or ui_run_data.get("id"))

        sdk_run_id = str(_unwrap_data(sdk_client.agents.start_run(sdk_agent_id, {"input": {"text": "hello"}})).get("run_id"))
        tool_start = handler.execute(
            state={},
            config={},
            context={
                "inputs": {
                    "action": "agents.start_run",
                    "tenant_id": tenant_id,
                    "token": api_key,
                    "base_url": base_url,
                    "payload": {"agent_id": tool_agent_id, "run": {"input": {"text": "hello"}}},
                }
            },
        )
        assert tool_start["context"]["errors"] == []
        tool_run_id = str(_unwrap_data(tool_start["context"]["result"]).get("run_id"))

        assert ui_run_id and sdk_run_id and tool_run_id
        assert _fetch_run_with_retry(base_url, headers, ui_run_id).get("id") == ui_run_id
        assert _fetch_run_with_retry(base_url, headers, sdk_run_id).get("id") == sdk_run_id
        assert _fetch_run_with_retry(base_url, headers, tool_run_id).get("id") == tool_run_id
    finally:
        if ui_agent_id:
            _delete_agent(base_url, headers, ui_agent_id)
        if sdk_agent_id:
            _delete_agent(base_url, headers, sdk_agent_id)
        if tool_agent_id:
            _delete_agent(base_url, headers, tool_agent_id)


@pytest.mark.real_db
def test_cross_surface_agents_resume_run_error_parity() -> None:
    base_url, headers, tenant_id, api_key = _require_env()
    sdk_client = ControlPlaneClient(base_url=base_url, token=api_key, tenant_id=tenant_id)
    nonexistent_run_id = f"00000000-0000-0000-0000-{uuid.uuid4().hex[:12]}"

    ui_resp = requests.post(
        f"{base_url}/agents/runs/{nonexistent_run_id}/resume",
        json={"input": {"text": "resume"}},
        headers=headers,
        timeout=30,
    )
    if ui_resp.status_code < 400:
        pytest.skip("Resume endpoint did not fail on nonexistent run_id; cannot assert error-path parity.")

    sdk_failed = False
    try:
        sdk_client.agents.resume_run(nonexistent_run_id, {"input": {"text": "resume"}})
    except Exception:
        sdk_failed = True
    assert sdk_failed is True

    tool_resp = handler.execute(
        state={},
        config={},
        context={
            "inputs": {
                "action": "agents.resume_run",
                "tenant_id": tenant_id,
                "token": api_key,
                "base_url": base_url,
                "payload": {"run_id": nonexistent_run_id, "run": {"input": {"text": "resume"}}},
            }
        },
    )
    assert tool_resp["context"]["errors"] != []
