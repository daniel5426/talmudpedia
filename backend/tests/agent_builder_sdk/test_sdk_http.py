import os
import uuid

import pytest
import requests

from sdk import Client, AgentGraphBuilder, GraphSpecValidator


def _require_http(base_url: str, headers: dict) -> list[dict]:
    try:
        resp = requests.get(f"{base_url.rstrip('/')}/agents/nodes/catalog", headers=headers, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
        return list(payload.get("nodes") or []) if isinstance(payload, dict) else []
    except Exception:
        pytest.skip("HTTP API not reachable for SDK tests. Set TEST_BASE_URL and ensure server is running.")


@pytest.mark.real_db
def test_sdk_catalog_parity():
    client = Client.from_env()
    catalog = _require_http(client.base_url, client.headers)
    client.connect()

    api_types = {spec.get("type") for spec in catalog if spec.get("type")}
    sdk_types = {spec.get("type") for spec in client._agent_nodes.catalog if spec.get("type")}
    assert api_types == sdk_types


@pytest.mark.real_db
def test_sdk_create_and_execute_agent():
    client = Client.from_env()
    _ = _require_http(client.base_url, client.headers)

    chat_model = os.getenv("TEST_CHAT_MODEL_SLUG")
    if not chat_model:
        pytest.skip("Set TEST_CHAT_MODEL_SLUG for SDK execution test.")

    client.connect()
    builder = AgentGraphBuilder("sdk-test")
    start = client.agent_nodes.control.Start()
    agent_node = client.agent_nodes.reasoning.Agent(model_id=chat_model)
    end = client.agent_nodes.control.End(output_message="done")
    builder.add(start, agent_node, end)
    builder.connect(start, agent_node)
    builder.connect(agent_node, end)

    slug = f"sdk-{uuid.uuid4().hex[:8]}"
    agent_id = builder.create(client, slug=slug)
    try:
        response = builder.execute(client, agent_id=agent_id, input_text="hello")
        assert "run_id" in response
    finally:
        try:
            requests.delete(f"{client.base_url.rstrip('/')}/agents/{agent_id}", headers=client.headers, timeout=10)
        except Exception:
            pass


@pytest.mark.real_db
def test_graph_spec_validator_catches_schema_errors():
    client = Client.from_env()
    catalog = _require_http(client.base_url, client.headers)
    validator = GraphSpecValidator(catalog)
    graph = {
        "nodes": [
            {"id": "agent", "type": "agent", "position": {"x": 0, "y": 0}, "config": {}},
        ],
        "edges": [],
    }
    errors = validator.validate_graph(graph)
    assert errors
