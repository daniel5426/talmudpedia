from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sdk import Client
from talmudpedia_control_sdk import ControlPlaneSDKError

from .shared import control_client, request_options


def _normalize_artifact_kind(payload: Dict[str, Any]) -> str:
    raw_kind = payload.get("kind")
    if raw_kind:
        return str(raw_kind)
    raw_scope = str(payload.get("scope") or "").strip().lower()
    if raw_scope == "agent":
        return "agent_node"
    if raw_scope == "tool":
        return "tool_impl"
    return "rag_operator"


def _default_contract_for_kind(kind: str) -> Dict[str, Any]:
    if kind == "agent_node":
        return {
            "state_reads": list(payload_list([])),
            "state_writes": list(payload_list([])),
            "input_schema": {"type": "object", "additionalProperties": True},
            "output_schema": {"type": "object", "additionalProperties": True},
            "node_ui": {},
        }
    if kind == "tool_impl":
        return {
            "input_schema": {"type": "object", "additionalProperties": True},
            "output_schema": {"type": "object", "additionalProperties": True},
            "side_effects": [],
            "execution_mode": "interactive",
            "tool_ui": {},
        }
    return {
        "operator_category": "transform",
        "pipeline_role": "processor",
        "input_schema": {"type": "object", "additionalProperties": True},
        "output_schema": {"type": "object", "additionalProperties": True},
        "execution_mode": "background",
    }


def payload_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _normalize_artifact_request_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(payload.get("runtime"), dict):
        return dict(payload)

    kind = _normalize_artifact_kind(payload)
    python_code = payload.get("python_code") or payload.get("code") or ""
    entry_module_path = str(payload.get("entry_module_path") or "main.py")
    normalized: Dict[str, Any] = {
        "slug": payload.get("slug") or payload.get("name"),
        "display_name": payload.get("display_name") or payload.get("name"),
        "description": payload.get("description"),
        "kind": kind,
        "runtime": {
            "source_files": payload_list(payload.get("source_files")) or [{"path": entry_module_path, "content": python_code}],
            "entry_module_path": entry_module_path,
            "python_dependencies": payload_list(payload.get("dependencies") or payload.get("python_dependencies")),
            "runtime_target": payload.get("runtime_target") or "cloudflare_workers",
        },
        "capabilities": payload.get("capabilities") or {
            "network_access": False,
            "allowed_hosts": [],
            "secret_refs": [],
            "storage_access": [],
            "side_effects": [],
        },
        "config_schema": payload.get("config_schema") if isinstance(payload.get("config_schema"), dict) else {},
    }

    if kind == "agent_node":
        normalized["agent_contract"] = payload.get("agent_contract") or {
            **_default_contract_for_kind(kind),
            "state_reads": payload_list(payload.get("reads")),
            "state_writes": payload_list(payload.get("writes")),
        }
    elif kind == "tool_impl":
        normalized["tool_contract"] = payload.get("tool_contract") or _default_contract_for_kind(kind)
    else:
        normalized["rag_contract"] = payload.get("rag_contract") or _default_contract_for_kind(kind)
    return normalized


def list_artifacts(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    try:
        tenant_slug = payload.get("tenant_slug")
        sdk_client = control_client_factory(client)
        response = sdk_client.artifacts.list(tenant_slug=tenant_slug)
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "list_artifacts_failed",
            "detail": str(exc),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "list_artifacts_failed", "detail": str(exc)}]


def get_artifact(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    artifact_id = payload.get("artifact_id") or payload.get("id")
    if not artifact_id:
        return None, [{"error": "missing_fields", "fields": ["artifact_id"]}]

    try:
        tenant_slug = payload.get("tenant_slug")
        sdk_client = control_client_factory(client)
        response = sdk_client.artifacts.get(str(artifact_id), tenant_slug=tenant_slug)
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "get_artifact_failed",
            "detail": str(exc),
            "artifact_id": artifact_id,
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "get_artifact_failed", "detail": str(exc), "artifact_id": artifact_id}]


def create_or_update_draft(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    artifact_id = payload.get("artifact_id") or payload.get("id")
    name = payload.get("name")
    python_code = payload.get("python_code") or payload.get("code")

    if not artifact_id and (not name or not python_code):
        return None, [{"error": "missing_fields", "fields": ["name", "python_code"]}]

    if dry_run:
        skipped: Dict[str, Any] = {"status": "skipped", "dry_run": True}
        if artifact_id:
            skipped["artifact_id"] = str(artifact_id)
        else:
            skipped["name"] = name
        return skipped, []

    request_payload = _normalize_artifact_request_payload(dict(payload))
    tenant_slug = request_payload.pop("tenant_slug", None)
    request_payload.pop("artifact_id", None)
    request_payload.pop("id", None)
    if not artifact_id:
        request_payload.setdefault("display_name", payload.get("display_name") or name)

    try:
        sdk_client = control_client_factory(client)
        if artifact_id:
            response = sdk_client.artifacts.update_draft(
                str(artifact_id),
                request_payload,
                tenant_slug=tenant_slug,
                options=request_options_builder(payload=payload, dry_run=False),
            )
        else:
            response = sdk_client.artifacts.create_draft(
                request_payload,
                tenant_slug=tenant_slug,
                options=request_options_builder(payload=payload, dry_run=False),
            )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "create_artifact_draft_failed",
            "detail": str(exc),
            "name": name,
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "create_artifact_draft_failed", "detail": str(exc), "name": name}]


def publish(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    artifact_id = payload.get("artifact_id") or payload.get("id")
    if not artifact_id:
        return None, [{"error": "missing_fields", "fields": ["artifact_id"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "artifact_id": str(artifact_id)}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.artifacts.publish(
            str(artifact_id),
            tenant_slug=payload.get("tenant_slug"),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "publish_artifact_failed",
            "detail": str(exc),
            "artifact_id": artifact_id,
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "publish_artifact_failed", "detail": str(exc), "artifact_id": artifact_id}]


def delete(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    artifact_id = payload.get("artifact_id") or payload.get("id")
    if not artifact_id:
        return None, [{"error": "missing_fields", "fields": ["artifact_id"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "artifact_id": str(artifact_id)}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.artifacts.delete(
            str(artifact_id),
            tenant_slug=payload.get("tenant_slug"),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data") or {"deleted": True, "artifact_id": str(artifact_id)}, []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "delete_artifact_failed",
            "detail": str(exc),
            "artifact_id": artifact_id,
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "delete_artifact_failed", "detail": str(exc), "artifact_id": artifact_id}]


def create_test_run(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    request_payload = payload.get("request") if isinstance(payload.get("request"), dict) else payload
    if not isinstance(request_payload, dict):
        return None, [{"error": "invalid_payload"}]

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.artifacts.create_test_run(request_payload, tenant_slug=payload.get("tenant_slug"))
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "create_artifact_test_run_failed",
            "detail": str(exc),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "create_artifact_test_run_failed", "detail": str(exc)}]
