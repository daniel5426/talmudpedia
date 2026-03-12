from __future__ import annotations

import os
import uuid
from typing import Any, Dict

import pytest
import requests

from app.system_artifacts.platform_sdk import handler
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


def _unwrap_data(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    if isinstance(payload, dict):
        return payload
    return {}


def _fetch_artifact(base_url: str, headers: Dict[str, str], artifact_id: str) -> Dict[str, Any]:
    response = requests.get(
        f"{base_url}/admin/artifacts/{artifact_id}",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return _unwrap_data(response.json())


def _normalize_artifact(record: Dict[str, Any]) -> Dict[str, Any]:
    runtime = record.get("runtime") if isinstance(record.get("runtime"), dict) else {}
    return {
        "slug": record.get("slug"),
        "display_name": record.get("display_name"),
        "description": record.get("description"),
        "kind": record.get("kind"),
        "entry_module_path": runtime.get("entry_module_path"),
        "runtime_target": runtime.get("runtime_target"),
    }


def _delete_artifact(base_url: str, headers: Dict[str, str], artifact_id: str) -> None:
    try:
        requests.delete(
            f"{base_url}/admin/artifacts/{artifact_id}",
            headers=headers,
            timeout=30,
        )
    except Exception:
        pass


def _create_artifact_for_tools(base_url: str, headers: Dict[str, str], name_prefix: str) -> str:
    payload = {
        "slug": f"{name_prefix}-artifact",
        "display_name": f"{name_prefix}-artifact",
        "description": "Tool backing artifact",
        "kind": "tool_impl",
        "runtime": {
            "source_files": [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return inputs"}],
            "entry_module_path": "main.py",
            "python_dependencies": [],
            "runtime_target": "cloudflare_workers",
        },
        "capabilities": {"network_access": False},
        "config_schema": {"type": "object"},
        "tool_contract": {
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "side_effects": [],
            "execution_mode": "interactive",
            "tool_ui": {},
        },
    }
    response = requests.post(
        f"{base_url}/admin/artifacts",
        json=payload,
        headers=headers,
        timeout=30,
    )
    if response.status_code >= 400:
        pytest.skip(f"Artifact endpoint unavailable for tool parity: {response.status_code} {response.text}")
    entity = _unwrap_data(response.json())
    artifact_id = entity.get("id")
    assert artifact_id
    return str(artifact_id)


def _fetch_tool(base_url: str, headers: Dict[str, str], tool_id: str) -> Dict[str, Any]:
    response = requests.get(
        f"{base_url}/tools/{tool_id}",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return _unwrap_data(response.json())


def _normalize_tool(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": record.get("name"),
        "slug": record.get("slug"),
        "description": record.get("description"),
        "implementation_type": record.get("implementation_type"),
        "artifact_id": record.get("artifact_id"),
        "status": record.get("status"),
    }


def _delete_tool(base_url: str, headers: Dict[str, str], tool_id: str) -> None:
    try:
        requests.delete(
            f"{base_url}/tools/{tool_id}",
            headers=headers,
            timeout=30,
        )
    except Exception:
        pass


def _require_chat_model() -> str:
    model_id = os.getenv("TEST_CHAT_MODEL_SLUG")
    if not model_id:
        pytest.skip("Set TEST_CHAT_MODEL_SLUG to run cross-surface agent parity tests.")
    return model_id


def _agent_payload(name: str, slug: str, model_id: str) -> Dict[str, Any]:
    return {
        "name": name,
        "slug": slug,
        "description": "Cross-surface parity test agent",
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


def _fetch_agent(base_url: str, headers: Dict[str, str], agent_id: str) -> Dict[str, Any]:
    response = requests.get(
        f"{base_url}/agents/{agent_id}",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return _unwrap_data(response.json())


def _normalize_agent(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": record.get("name"),
        "slug": record.get("slug"),
        "description": record.get("description"),
        "status": record.get("status"),
    }


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
def test_cross_surface_artifacts_create_parity() -> None:
    base_url, headers, tenant_id, api_key = _require_env()

    artifact_slug = f"sdk-parity-{uuid.uuid4().hex[:8]}"
    payload = {
        "slug": artifact_slug,
        "display_name": f"{artifact_slug}-display",
        "description": "Cross-surface parity test artifact",
        "kind": "tool_impl",
        "runtime": {
            "source_files": [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return inputs"}],
            "entry_module_path": "main.py",
            "python_dependencies": ["httpx>=0.27"],
            "runtime_target": "cloudflare_workers",
        },
        "capabilities": {"network_access": False},
        "config_schema": {"type": "object"},
        "tool_contract": {
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "side_effects": [],
            "execution_mode": "interactive",
            "tool_ui": {},
        },
    }

    ui_artifact_id = None
    sdk_artifact_id = None
    tool_artifact_id = None

    try:
        ui_response = requests.post(
            f"{base_url}/admin/artifacts",
            json=payload,
            headers=headers,
            timeout=30,
        )
        if ui_response.status_code >= 400:
            pytest.skip(f"Artifact draft endpoint unavailable: {ui_response.status_code} {ui_response.text}")
        ui_entity = _unwrap_data(ui_response.json())
        ui_artifact_id = ui_entity.get("id")
        assert ui_artifact_id

        sdk_client = ControlPlaneClient(
            base_url=base_url,
            token=api_key,
            tenant_id=tenant_id,
        )
        sdk_result = sdk_client.artifacts.create(payload)
        sdk_entity = _unwrap_data(sdk_result)
        sdk_artifact_id = sdk_entity.get("id")
        assert sdk_artifact_id

        tool_result = handler.execute(
            state={},
            config={},
            context={
                "inputs": {
                    "action": "artifacts.create",
                    "tenant_id": tenant_id,
                    "token": api_key,
                    "base_url": base_url,
                    "payload": payload,
                }
            },
        )
        assert tool_result["context"]["errors"] == []
        tool_entity = _unwrap_data(tool_result["context"]["result"])
        tool_artifact_id = tool_entity.get("id")
        assert tool_artifact_id

        ui_persisted = _fetch_artifact(base_url, headers, str(ui_artifact_id))
        sdk_persisted = _fetch_artifact(base_url, headers, str(sdk_artifact_id))
        tool_persisted = _fetch_artifact(base_url, headers, str(tool_artifact_id))

        expected = _normalize_artifact(payload)
        assert _normalize_artifact(ui_persisted) == expected
        assert _normalize_artifact(sdk_persisted) == expected
        assert _normalize_artifact(tool_persisted) == expected
    finally:
        if ui_artifact_id:
            _delete_artifact(base_url, headers, str(ui_artifact_id))
        if sdk_artifact_id:
            _delete_artifact(base_url, headers, str(sdk_artifact_id))
        if tool_artifact_id:
            _delete_artifact(base_url, headers, str(tool_artifact_id))


@pytest.mark.real_db
def test_cross_surface_tools_create_or_update_create_parity() -> None:
    base_url, headers, tenant_id, api_key = _require_env()
    sdk_client = ControlPlaneClient(base_url=base_url, token=api_key, tenant_id=tenant_id)

    unique = uuid.uuid4().hex[:8]
    backing_artifact_id = None
    ui_tool_id = None
    sdk_tool_id = None
    tool_tool_id = None

    try:
        backing_artifact_id = _create_artifact_for_tools(base_url, headers, f"tool-create-{unique}")
        payload = {
            "name": f"Tool Create {unique}",
            "slug": f"tool-create-{unique}",
            "description": "Cross-surface create parity tool",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "implementation_type": "ARTIFACT",
            "artifact_id": backing_artifact_id,
            "status": "DRAFT",
        }

        ui_response = requests.post(f"{base_url}/tools", json=payload, headers=headers, timeout=30)
        if ui_response.status_code >= 400:
            pytest.skip(f"Tools create endpoint unavailable: {ui_response.status_code} {ui_response.text}")
        ui_tool_id = str(_unwrap_data(ui_response.json()).get("id"))
        assert ui_tool_id

        sdk_tool_id = str(_unwrap_data(sdk_client.tools.create(payload)).get("id"))
        assert sdk_tool_id

        tool_result = handler.execute(
            state={},
            config={},
            context={
                "inputs": {
                    "action": "tools.create_or_update",
                    "tenant_id": tenant_id,
                    "token": api_key,
                    "base_url": base_url,
                    "payload": payload,
                }
            },
        )
        assert tool_result["context"]["errors"] == []
        tool_tool_id = str(_unwrap_data(tool_result["context"]["result"]).get("id"))
        assert tool_tool_id

        expected = _normalize_tool(payload)
        assert _normalize_tool(_fetch_tool(base_url, headers, ui_tool_id)) == expected
        assert _normalize_tool(_fetch_tool(base_url, headers, sdk_tool_id)) == expected
        assert _normalize_tool(_fetch_tool(base_url, headers, tool_tool_id)) == expected
    finally:
        if ui_tool_id:
            _delete_tool(base_url, headers, ui_tool_id)
        if sdk_tool_id:
            _delete_tool(base_url, headers, sdk_tool_id)
        if tool_tool_id:
            _delete_tool(base_url, headers, tool_tool_id)
        if backing_artifact_id:
            _delete_artifact(base_url, headers, backing_artifact_id)


@pytest.mark.real_db
def test_cross_surface_tools_create_or_update_update_parity() -> None:
    base_url, headers, tenant_id, api_key = _require_env()
    sdk_client = ControlPlaneClient(base_url=base_url, token=api_key, tenant_id=tenant_id)

    unique = uuid.uuid4().hex[:8]
    backing_artifact_id = None
    ui_tool_id = None
    sdk_tool_id = None
    tool_tool_id = None

    try:
        backing_artifact_id = _create_artifact_for_tools(base_url, headers, f"tool-update-{unique}")
        seed_payload = {
            "name": f"Tool Update {unique}",
            "slug": f"tool-update-{unique}",
            "description": "seed",
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
            "implementation_type": "ARTIFACT",
            "artifact_id": backing_artifact_id,
            "status": "DRAFT",
        }

        ui_tool_id = str(_unwrap_data(requests.post(f"{base_url}/tools", json=seed_payload, headers=headers, timeout=30).json()).get("id"))
        sdk_tool_id = str(_unwrap_data(sdk_client.tools.create({**seed_payload, "slug": f"tool-update-sdk-{unique}"})).get("id"))
        tool_seed = handler.execute(
            state={},
            config={},
            context={
                "inputs": {
                    "action": "tools.create_or_update",
                    "tenant_id": tenant_id,
                    "token": api_key,
                    "base_url": base_url,
                    "payload": {**seed_payload, "slug": f"tool-update-tool-{unique}"},
                }
            },
        )
        tool_tool_id = str(_unwrap_data(tool_seed["context"]["result"]).get("id"))

        updated_description = f"updated-{unique}"
        ui_update = requests.put(
            f"{base_url}/tools/{ui_tool_id}",
            json={"description": updated_description},
            headers=headers,
            timeout=30,
        )
        if ui_update.status_code >= 400:
            pytest.skip(f"Tools update endpoint unavailable: {ui_update.status_code} {ui_update.text}")

        _unwrap_data(sdk_client.tools.update(sdk_tool_id, {"description": updated_description}))
        tool_update = handler.execute(
            state={},
            config={},
            context={
                "inputs": {
                    "action": "tools.create_or_update",
                    "tenant_id": tenant_id,
                    "token": api_key,
                    "base_url": base_url,
                    "payload": {
                        "tool_id": tool_tool_id,
                        "patch": {"description": updated_description},
                    },
                }
            },
        )
        assert tool_update["context"]["errors"] == []

        assert _fetch_tool(base_url, headers, ui_tool_id).get("description") == updated_description
        assert _fetch_tool(base_url, headers, sdk_tool_id).get("description") == updated_description
        assert _fetch_tool(base_url, headers, tool_tool_id).get("description") == updated_description
    finally:
        if ui_tool_id:
            _delete_tool(base_url, headers, ui_tool_id)
        if sdk_tool_id:
            _delete_tool(base_url, headers, sdk_tool_id)
        if tool_tool_id:
            _delete_tool(base_url, headers, tool_tool_id)
        if backing_artifact_id:
            _delete_artifact(base_url, headers, backing_artifact_id)


@pytest.mark.real_db
def test_cross_surface_agents_create_or_update_create_parity() -> None:
    base_url, headers, tenant_id, api_key = _require_env()
    model_id = _require_chat_model()
    sdk_client = ControlPlaneClient(base_url=base_url, token=api_key, tenant_id=tenant_id)

    unique = uuid.uuid4().hex[:8]
    ui_agent_id = None
    sdk_agent_id = None
    tool_agent_id = None

    try:
        ui_payload = _agent_payload(f"Agent UI {unique}", f"agent-ui-{unique}", model_id)
        sdk_payload = _agent_payload(f"Agent SDK {unique}", f"agent-sdk-{unique}", model_id)
        tool_payload = _agent_payload(f"Agent Tool {unique}", f"agent-tool-{unique}", model_id)

        ui_create = requests.post(f"{base_url}/agents", json=ui_payload, headers=headers, timeout=30)
        if ui_create.status_code >= 400:
            pytest.skip(f"Agents create endpoint unavailable: {ui_create.status_code} {ui_create.text}")
        ui_agent_id = str(_unwrap_data(ui_create.json()).get("id"))
        assert ui_agent_id

        sdk_agent_id = str(_unwrap_data(sdk_client.agents.create(sdk_payload)).get("id"))
        assert sdk_agent_id

        tool_create = handler.execute(
            state={},
            config={},
            context={
                "inputs": {
                    "action": "agents.create_or_update",
                    "tenant_id": tenant_id,
                    "token": api_key,
                    "base_url": base_url,
                    "payload": tool_payload,
                }
            },
        )
        assert tool_create["context"]["errors"] == []
        tool_agent_id = str(_unwrap_data(tool_create["context"]["result"]).get("id"))
        assert tool_agent_id

        assert _normalize_agent(_fetch_agent(base_url, headers, ui_agent_id)) == _normalize_agent(ui_payload)
        assert _normalize_agent(_fetch_agent(base_url, headers, sdk_agent_id)) == _normalize_agent(sdk_payload)
        assert _normalize_agent(_fetch_agent(base_url, headers, tool_agent_id)) == _normalize_agent(tool_payload)
    finally:
        if ui_agent_id:
            _delete_agent(base_url, headers, ui_agent_id)
        if sdk_agent_id:
            _delete_agent(base_url, headers, sdk_agent_id)
        if tool_agent_id:
            _delete_agent(base_url, headers, tool_agent_id)


@pytest.mark.real_db
def test_cross_surface_agents_publish_parity() -> None:
    base_url, headers, tenant_id, api_key = _require_env()
    model_id = _require_chat_model()
    sdk_client = ControlPlaneClient(base_url=base_url, token=api_key, tenant_id=tenant_id)

    unique = uuid.uuid4().hex[:8]
    ui_agent_id = None
    sdk_agent_id = None
    tool_agent_id = None

    try:
        ui_seed = requests.post(
            f"{base_url}/agents",
            json=_agent_payload(f"Publish UI {unique}", f"publish-ui-{unique}", model_id),
            headers=headers,
            timeout=30,
        )
        if ui_seed.status_code >= 400:
            pytest.skip(f"Agents create endpoint unavailable for publish test: {ui_seed.status_code} {ui_seed.text}")
        ui_agent_id = str(_unwrap_data(ui_seed.json()).get("id"))
        sdk_agent_id = str(_unwrap_data(requests.post(
            f"{base_url}/agents",
            json=_agent_payload(f"Publish SDK {unique}", f"publish-sdk-{unique}", model_id),
            headers=headers,
            timeout=30,
        ).json()).get("id"))
        tool_agent_id = str(_unwrap_data(requests.post(
            f"{base_url}/agents",
            json=_agent_payload(f"Publish Tool {unique}", f"publish-tool-{unique}", model_id),
            headers=headers,
            timeout=30,
        ).json()).get("id"))

        ui_publish = requests.post(f"{base_url}/agents/{ui_agent_id}/publish", json={}, headers=headers, timeout=30)
        if ui_publish.status_code >= 400:
            pytest.skip(f"Agents publish endpoint unavailable: {ui_publish.status_code} {ui_publish.text}")

        _unwrap_data(sdk_client.agents.publish(sdk_agent_id))
        tool_publish = handler.execute(
            state={},
            config={},
            context={
                "inputs": {
                    "action": "agents.publish",
                    "tenant_id": tenant_id,
                    "token": api_key,
                    "base_url": base_url,
                    "payload": {"agent_id": tool_agent_id},
                }
            },
        )
        assert tool_publish["context"]["errors"] == []

        ui_status = _fetch_agent(base_url, headers, ui_agent_id).get("status")
        sdk_status = _fetch_agent(base_url, headers, sdk_agent_id).get("status")
        tool_status = _fetch_agent(base_url, headers, tool_agent_id).get("status")
        assert ui_status == "published"
        assert sdk_status == "published"
        assert tool_status == "published"
    finally:
        if ui_agent_id:
            _delete_agent(base_url, headers, ui_agent_id)
        if sdk_agent_id:
            _delete_agent(base_url, headers, sdk_agent_id)
        if tool_agent_id:
            _delete_agent(base_url, headers, tool_agent_id)


@pytest.mark.real_db
def test_cross_surface_tools_publish_parity() -> None:
    base_url, headers, tenant_id, api_key = _require_env()
    sdk_client = ControlPlaneClient(base_url=base_url, token=api_key, tenant_id=tenant_id)

    unique = uuid.uuid4().hex[:8]
    backing_artifact_id = None
    ui_tool_id = None
    sdk_tool_id = None
    tool_tool_id = None

    try:
        backing_artifact_id = _create_artifact_for_tools(base_url, headers, f"tool-publish-{unique}")

        def _tool_seed(slug: str) -> Dict[str, Any]:
            return {
                "name": f"Tool Publish {slug}",
                "slug": slug,
                "description": "tool publish parity",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "implementation_type": "ARTIFACT",
                "artifact_id": backing_artifact_id,
                "status": "DRAFT",
            }

        ui_tool_id = str(_unwrap_data(requests.post(
            f"{base_url}/tools",
            json=_tool_seed(f"tool-publish-ui-{unique}"),
            headers=headers,
            timeout=30,
        ).json()).get("id"))
        sdk_tool_id = str(_unwrap_data(sdk_client.tools.create(_tool_seed(f"tool-publish-sdk-{unique}"))).get("id"))
        tool_tool_id = str(_unwrap_data(handler.execute(
            state={},
            config={},
            context={
                "inputs": {
                    "action": "tools.create_or_update",
                    "tenant_id": tenant_id,
                    "token": api_key,
                    "base_url": base_url,
                    "payload": _tool_seed(f"tool-publish-tool-{unique}"),
                }
            },
        )["context"]["result"]).get("id"))

        ui_publish = requests.post(f"{base_url}/tools/{ui_tool_id}/publish", json={}, headers=headers, timeout=30)
        if ui_publish.status_code >= 400:
            pytest.skip(f"Tools publish endpoint unavailable: {ui_publish.status_code} {ui_publish.text}")

        _unwrap_data(sdk_client.tools.publish(sdk_tool_id))
        tool_publish = handler.execute(
            state={},
            config={},
            context={
                "inputs": {
                    "action": "tools.publish",
                    "tenant_id": tenant_id,
                    "token": api_key,
                    "base_url": base_url,
                    "payload": {"tool_id": tool_tool_id},
                }
            },
        )
        assert tool_publish["context"]["errors"] == []

        assert _fetch_tool(base_url, headers, ui_tool_id).get("status") == "ACTIVE"
        assert _fetch_tool(base_url, headers, sdk_tool_id).get("status") == "ACTIVE"
        assert _fetch_tool(base_url, headers, tool_tool_id).get("status") == "ACTIVE"
    finally:
        if ui_tool_id:
            _delete_tool(base_url, headers, ui_tool_id)
        if sdk_tool_id:
            _delete_tool(base_url, headers, sdk_tool_id)
        if tool_tool_id:
            _delete_tool(base_url, headers, tool_tool_id)
        if backing_artifact_id:
            _delete_artifact(base_url, headers, backing_artifact_id)


@pytest.mark.real_db
def test_cross_surface_artifacts_publish_parity() -> None:
    base_url, headers, tenant_id, api_key = _require_env()
    sdk_client = ControlPlaneClient(base_url=base_url, token=api_key, tenant_id=tenant_id)

    unique = uuid.uuid4().hex[:8]
    ui_artifact_id = None
    sdk_artifact_id = None
    tool_artifact_id = None

    try:
        def _draft_payload(slug: str) -> Dict[str, Any]:
            return {
                "slug": slug,
                "display_name": slug,
                "description": "publish parity draft",
                "kind": "tool_impl",
                "runtime": {
                    "source_files": [{"path": "main.py", "content": "def execute(inputs, config, context):\n    return inputs"}],
                    "entry_module_path": "main.py",
                    "python_dependencies": [],
                    "runtime_target": "cloudflare_workers",
                },
                "capabilities": {"network_access": False},
                "config_schema": {"type": "object"},
                "tool_contract": {
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "side_effects": [],
                    "execution_mode": "interactive",
                    "tool_ui": {},
                },
            }

        ui_artifact_id = str(_unwrap_data(requests.post(
            f"{base_url}/admin/artifacts",
            json=_draft_payload(f"promote-ui-{unique}"),
            headers=headers,
            timeout=30,
        ).json()).get("id"))
        sdk_artifact_id = str(_unwrap_data(sdk_client.artifacts.create(_draft_payload(f"publish-sdk-{unique}"))).get("id"))
        tool_artifact_id = str(_unwrap_data(handler.execute(
            state={},
            config={},
            context={
                "inputs": {
                    "action": "artifacts.create",
                    "tenant_id": tenant_id,
                    "token": api_key,
                    "base_url": base_url,
                    "payload": _draft_payload(f"publish-tool-{unique}"),
                }
            },
        )["context"]["result"]).get("id"))

        ui_promote = requests.post(
            f"{base_url}/admin/artifacts/{ui_artifact_id}/publish",
            headers=headers,
            timeout=30,
        )
        if ui_promote.status_code >= 400:
            pytest.skip(f"Artifacts publish endpoint unavailable: {ui_promote.status_code} {ui_promote.text}")
        ui_promoted_id = str(_unwrap_data(ui_promote.json()).get("artifact_id"))

        sdk_promoted_id = str(_unwrap_data(sdk_client.artifacts.publish(sdk_artifact_id)).get("artifact_id"))
        tool_promote = handler.execute(
            state={},
            config={},
            context={
                "inputs": {
                    "action": "artifacts.publish",
                    "tenant_id": tenant_id,
                    "token": api_key,
                    "base_url": base_url,
                    "payload": {"artifact_id": tool_artifact_id},
                    "objective_flags": {"allow_publish": True},
                }
            },
        )
        assert tool_promote["context"]["errors"] == []
        tool_promoted_id = str(_unwrap_data(tool_promote["context"]["result"]).get("artifact_id"))

        assert ui_promoted_id
        assert sdk_promoted_id
        assert tool_promoted_id
    finally:
        if ui_artifact_id:
            _delete_artifact(base_url, headers, ui_artifact_id)
        if sdk_artifact_id:
            _delete_artifact(base_url, headers, sdk_artifact_id)
        if tool_artifact_id:
            _delete_artifact(base_url, headers, tool_artifact_id)
