from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sdk import Client
from talmudpedia_control_sdk import ControlPlaneSDKError

from .shared import control_client, request_options


def list_credentials(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.credentials.list(category=payload.get("category"))
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "list_credentials_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "list_credentials_failed", "detail": str(exc)}]


def create_or_update(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    credential_id = payload.get("credential_id") or payload.get("id")

    if dry_run:
        skipped: Dict[str, Any] = {"status": "skipped", "dry_run": True}
        if credential_id:
            skipped["credential_id"] = str(credential_id)
        return skipped, []

    try:
        sdk_client = control_client_factory(client)
        if credential_id:
            patch_payload = dict(payload.get("patch")) if isinstance(payload.get("patch"), dict) else dict(payload)
            patch_payload.pop("credential_id", None)
            patch_payload.pop("id", None)
            response = sdk_client.credentials.update(
                str(credential_id),
                patch_payload,
                options=request_options_builder(payload=payload, dry_run=False),
            )
        else:
            response = sdk_client.credentials.create(
                payload,
                options=request_options_builder(payload=payload, dry_run=False),
            )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "create_or_update_credential_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "create_or_update_credential_failed", "detail": str(exc)}]


def delete(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    credential_id = payload.get("credential_id") or payload.get("id")
    if not credential_id:
        return None, [{"error": "missing_fields", "fields": ["credential_id"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "credential_id": str(credential_id)}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.credentials.delete(
            str(credential_id),
            force_disconnect=bool(payload.get("force_disconnect", False)),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "delete_credential_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "delete_credential_failed", "detail": str(exc)}]


def usage(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    credential_id = payload.get("credential_id") or payload.get("id")
    if not credential_id:
        return None, [{"error": "missing_fields", "fields": ["credential_id"]}]

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.credentials.usage(str(credential_id))
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "credential_usage_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "credential_usage_failed", "detail": str(exc)}]


def status(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.credentials.status()
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "credentials_status_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "credentials_status_failed", "detail": str(exc)}]
