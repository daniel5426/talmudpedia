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


def create(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    missing: List[str] = []
    for field_name in ("slug", "display_name", "kind", "runtime"):
        if payload.get(field_name) in (None, ""):
            missing.append(field_name)
    if missing:
        return None, [{"error": "missing_fields", "fields": missing}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "slug": str(payload.get("slug") or "")}, []

    try:
        sdk_client = control_client_factory(client)
        request_payload = dict(payload)
        tenant_slug = request_payload.pop("tenant_slug", None)
        response = sdk_client.artifacts.create(
            request_payload,
            tenant_slug=tenant_slug,
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "create_artifact_failed",
            "detail": str(exc),
            "slug": payload.get("slug"),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "create_artifact_failed", "detail": str(exc), "slug": payload.get("slug")}]


def update(
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
    patch_payload = dict(payload.get("patch")) if isinstance(payload.get("patch"), dict) else None
    if patch_payload is None:
        return None, [{"error": "missing_fields", "fields": ["patch"]}]

    if dry_run:
        return {
            "status": "skipped",
            "dry_run": True,
            "artifact_id": str(artifact_id),
        }, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.artifacts.update(
            str(artifact_id),
            patch_payload,
            tenant_slug=payload.get("tenant_slug"),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "update_artifact_failed",
            "detail": str(exc),
            "artifact_id": artifact_id,
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "update_artifact_failed", "detail": str(exc), "artifact_id": artifact_id}]


def convert_kind(
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

    request_payload = dict(payload)
    request_payload.pop("artifact_id", None)
    request_payload.pop("id", None)
    if not request_payload.get("kind"):
        return None, [{"error": "missing_fields", "fields": ["kind"]}]

    if dry_run:
        return {
            "status": "skipped",
            "dry_run": True,
            "artifact_id": str(artifact_id),
            "kind": str(request_payload.get("kind")),
        }, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.artifacts.convert_kind(
            str(artifact_id),
            request_payload,
            tenant_slug=payload.get("tenant_slug"),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "convert_artifact_kind_failed",
            "detail": str(exc),
            "artifact_id": artifact_id,
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "convert_artifact_kind_failed", "detail": str(exc), "artifact_id": artifact_id}]


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
    request_payload = dict(payload)
    request_payload.pop("tenant_slug", None)
    if not request_payload:
        return None, [{"error": "missing_fields", "fields": ["input_data"]}]

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
