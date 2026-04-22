from __future__ import annotations

import os

import pytest

from talmudpedia_control_sdk import ControlPlaneClient, ControlPlaneSDKError


def _require_env() -> tuple[ControlPlaneClient, str | None]:
    base_url = os.getenv("TEST_BASE_URL")
    token = os.getenv("TEST_API_KEY")
    organization_id = os.getenv("TEST_TENANT_ID")
    tenant_slug = os.getenv("TEST_TENANT_SLUG")
    if not base_url or not token or not organization_id:
        pytest.skip("Set TEST_BASE_URL, TEST_API_KEY, and TEST_TENANT_ID for control SDK HTTP integration tests.")
    client = ControlPlaneClient(base_url=base_url, token=token, organization_id=organization_id)
    return client, tenant_slug


def _call_or_skip(label: str, call):
    try:
        return call()
    except ControlPlaneSDKError as exc:
        pytest.skip(f"{label} unavailable in this env: {exc}")


@pytest.mark.real_db
def test_control_sdk_read_surface_smoke() -> None:
    client, _tenant_slug = _require_env()

    catalog = _call_or_skip("catalog.get_rag_operator_catalog", lambda: client.catalog.get_rag_operator_catalog())
    assert "data" in catalog

    agent_ops = _call_or_skip("catalog.list_agent_nodes", lambda: client.catalog.list_agent_nodes())
    assert "data" in agent_ops

    agents = _call_or_skip("agents.list", lambda: client.agents.list(limit=5))
    assert "data" in agents

    tools = _call_or_skip("tools.list", lambda: client.tools.list(limit=5))
    assert "data" in tools

    models = _call_or_skip("models.list", lambda: client.models.list(limit=5))
    assert "data" in models

    credentials = _call_or_skip("credentials.status", lambda: client.credentials.status())
    assert "data" in credentials

@pytest.mark.real_db
def test_control_sdk_tenant_slug_surfaces_when_available() -> None:
    client, tenant_slug = _require_env()
    if not tenant_slug:
        pytest.skip("Set TEST_TENANT_SLUG to run tenant-slug surface integration tests.")

    artifacts = _call_or_skip("artifacts.list", lambda: client.artifacts.list(tenant_slug=tenant_slug))
    assert "data" in artifacts

    rag_pipelines = _call_or_skip("rag.list_visual_pipelines", lambda: client.rag.list_visual_pipelines(tenant_slug=tenant_slug))
    assert "data" in rag_pipelines

    knowledge_stores = _call_or_skip("knowledge_stores.list", lambda: client.knowledge_stores.list(tenant_slug))
    assert "data" in knowledge_stores
