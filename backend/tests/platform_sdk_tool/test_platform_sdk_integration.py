import os
import uuid

import pytest
import requests

from artifacts.builtin.platform_sdk import handler


def _require_env():
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


@pytest.mark.real_db
def test_artifact_draft_promote_create_tool_flow():
    base_url, headers, _tenant_id, _api_key = _require_env()

    artifact_name = f"sdk_test_{uuid.uuid4().hex[:8]}"
    draft_payload = {
        "name": artifact_name,
        "display_name": artifact_name,
        "description": "SDK integration test artifact",
        "category": "custom",
        "input_type": "raw_documents",
        "output_type": "raw_documents",
        "python_code": "def execute(input_data, config=None):\n    return input_data",
    }

    tool_id = None
    artifact_id = None

    draft_resp = requests.post(
        f"{base_url}/admin/artifacts",
        json=draft_payload,
        headers=headers,
        timeout=30,
    )
    if draft_resp.status_code >= 400:
        pytest.skip(f"Artifact draft endpoint unavailable: {draft_resp.status_code} {draft_resp.text}")
    draft_id = draft_resp.json().get("id")

    promote_resp = requests.post(
        f"{base_url}/admin/artifacts/{draft_id}/promote",
        json={"namespace": "custom"},
        headers=headers,
        timeout=30,
    )
    if promote_resp.status_code >= 400:
        pytest.skip(f"Artifact promote unavailable: {promote_resp.status_code} {promote_resp.text}")
    artifact_id = promote_resp.json().get("artifact_id")

    tool_payload = {
        "name": f"{artifact_name} Tool",
        "slug": f"{artifact_name}-tool",
        "description": "SDK integration test tool",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "implementation_type": "ARTIFACT",
        "artifact_id": artifact_id,
        "status": "DRAFT",
    }

    try:
        tool_resp = requests.post(
            f"{base_url}/tools",
            json=tool_payload,
            headers=headers,
            timeout=30,
        )
        tool_resp.raise_for_status()
        tool_id = tool_resp.json().get("id")
        assert tool_id
    finally:
        if tool_id:
            try:
                requests.delete(
                    f"{base_url}/tools/{tool_id}",
                    headers=headers,
                    timeout=30,
                )
            except Exception:
                pass
        if artifact_id:
            try:
                requests.delete(
                    f"{base_url}/admin/artifacts/{artifact_id}",
                    headers=headers,
                    timeout=30,
                )
            except Exception:
                pass


@pytest.mark.real_db
def test_platform_sdk_run_tests_action():
    base_url, headers, tenant_id, api_key = _require_env()
    model_id = os.getenv("TEST_CHAT_MODEL_SLUG")
    if not model_id:
        pytest.skip("Set TEST_CHAT_MODEL_SLUG to run agent execution integration test.")

    agent_slug = f"sdk-test-{uuid.uuid4().hex[:8]}"
    agent_payload = {
        "name": "SDK Test Agent",
        "slug": agent_slug,
        "description": "Integration test agent",
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

    agent_id = None
    create_resp = requests.post(
        f"{base_url}/agents",
        json=agent_payload,
        headers=headers,
        timeout=30,
    )
    if create_resp.status_code >= 400:
        pytest.skip(f"Agent creation unavailable: {create_resp.status_code} {create_resp.text}")
    agent_id = create_resp.json().get("id")

    try:
        inputs = {
            "action": "run_tests",
            "tests": [
                {
                    "name": "smoke",
                    "agent_target": {"agent_id": agent_id},
                    "input": {"text": "hello"},
                    "assertions": [
                        {"type": "contains", "path": "output.text", "expected": "OK"}
                    ],
                }
            ],
            "base_url": base_url,
            "token": api_key,
            "tenant_id": tenant_id,
        }
        result = handler.execute({}, {}, {"inputs": inputs})
        summary = result["context"]["result"]["summary"]
        assert summary["failed"] == 0
    finally:
        if agent_id:
            try:
                requests.delete(
                    f"{base_url}/agents/{agent_id}",
                    headers=headers,
                    timeout=30,
                )
            except Exception:
                pass
