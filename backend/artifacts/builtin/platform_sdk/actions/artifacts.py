from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sdk import Client
from talmudpedia_control_sdk import ControlPlaneSDKError

from .shared import control_client, request_options


def list_artifacts(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    try:
        tenant_slug = payload.get("tenant_slug")
        sdk_client = control_client_factory(client)
        response = sdk_client.artifacts.list(
            tenant_slug=tenant_slug,
            skip=int(payload.get("skip", 0) or 0),
            limit=int(payload.get("limit", 20) or 20),
            view=str(payload.get("view") or "summary"),
        )
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

    request_payload = dict(payload)
    tenant_slug = request_payload.pop("tenant_slug", None)
    request_payload.pop("artifact_id", None)
    request_payload.pop("id", None)
    if python_code:
        request_payload["python_code"] = python_code
    request_payload.pop("code", None)
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


def promote(
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

    namespace = payload.get("namespace")
    if not namespace:
        return None, [{"error": "missing_fields", "fields": ["namespace"]}]

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.artifacts.promote(
            str(artifact_id),
            namespace=namespace,
            version=payload.get("version"),
            tenant_slug=payload.get("tenant_slug"),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "promote_artifact_failed",
            "detail": str(exc),
            "artifact_id": artifact_id,
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "promote_artifact_failed", "detail": str(exc), "artifact_id": artifact_id}]


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


def test_artifact(
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
        response = sdk_client.artifacts.test(request_payload, tenant_slug=payload.get("tenant_slug"))
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "test_artifact_failed",
            "detail": str(exc),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "test_artifact_failed", "detail": str(exc)}]
