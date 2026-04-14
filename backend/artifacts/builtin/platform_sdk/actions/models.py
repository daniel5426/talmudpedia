from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sdk import Client
from talmudpedia_control_sdk import ControlPlaneSDKError

from .shared import control_client, request_options


def list_models(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.models.list(
            capability_type=payload.get("capability_type"),
            is_active=payload.get("is_active", True),
            skip=int(payload.get("skip", 0) or 0),
            limit=int(payload.get("limit", 20) or 20),
            view=str(payload.get("view") or "summary"),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "list_models_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "list_models_failed", "detail": str(exc)}]


def create_or_update(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    model_id = payload.get("model_id") or payload.get("id")

    if dry_run:
        skipped: Dict[str, Any] = {"status": "skipped", "dry_run": True}
        if model_id:
            skipped["model_id"] = str(model_id)
        return skipped, []

    try:
        sdk_client = control_client_factory(client)
        if model_id:
            patch_payload = dict(payload.get("patch")) if isinstance(payload.get("patch"), dict) else dict(payload)
            patch_payload.pop("model_id", None)
            patch_payload.pop("id", None)
            response = sdk_client.models.update(
                str(model_id),
                patch_payload,
                options=request_options_builder(payload=payload, dry_run=False),
            )
        else:
            response = sdk_client.models.create(
                payload,
                options=request_options_builder(payload=payload, dry_run=False),
            )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "create_or_update_model_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "create_or_update_model_failed", "detail": str(exc)}]


def add_provider(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    model_id = payload.get("model_id")
    provider_spec = payload.get("provider") if isinstance(payload.get("provider"), dict) else payload.get("spec")
    if not isinstance(provider_spec, dict):
        provider_spec = payload

    if not model_id:
        return None, [{"error": "missing_fields", "fields": ["model_id"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "model_id": str(model_id)}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.models.add_provider(
            str(model_id),
            provider_spec,
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "add_provider_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "add_provider_failed", "detail": str(exc)}]


def update_provider(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    model_id = payload.get("model_id")
    provider_id = payload.get("provider_id")
    patch_payload = payload.get("patch") if isinstance(payload.get("patch"), dict) else payload

    missing: List[str] = []
    if not model_id:
        missing.append("model_id")
    if not provider_id:
        missing.append("provider_id")
    if missing:
        return None, [{"error": "missing_fields", "fields": missing}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "model_id": str(model_id), "provider_id": str(provider_id)}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.models.update_provider(
            str(model_id),
            str(provider_id),
            patch_payload,
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "update_provider_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "update_provider_failed", "detail": str(exc)}]


def delete_provider(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    model_id = payload.get("model_id")
    provider_id = payload.get("provider_id")

    missing: List[str] = []
    if not model_id:
        missing.append("model_id")
    if not provider_id:
        missing.append("provider_id")
    if missing:
        return None, [{"error": "missing_fields", "fields": missing}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "model_id": str(model_id), "provider_id": str(provider_id)}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.models.delete_provider(
            str(model_id),
            str(provider_id),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data") or {"deleted": True}, []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "delete_provider_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "delete_provider_failed", "detail": str(exc)}]
