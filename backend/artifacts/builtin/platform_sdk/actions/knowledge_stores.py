from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sdk import Client
from talmudpedia_control_sdk import ControlPlaneSDKError

from .shared import control_client, request_options


def list_knowledge_stores(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    tenant_slug = payload.get("tenant_slug")
    if not tenant_slug:
        return None, [{"error": "missing_fields", "fields": ["tenant_slug"]}]

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.knowledge_stores.list(str(tenant_slug))
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "list_knowledge_stores_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "list_knowledge_stores_failed", "detail": str(exc)}]


def create_or_update(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    store_id = payload.get("store_id") or payload.get("id")
    tenant_slug = payload.get("tenant_slug")

    if dry_run:
        skipped: Dict[str, Any] = {"status": "skipped", "dry_run": True}
        if store_id:
            skipped["store_id"] = str(store_id)
        return skipped, []

    try:
        sdk_client = control_client_factory(client)
        if store_id:
            patch_payload = dict(payload.get("patch")) if isinstance(payload.get("patch"), dict) else dict(payload)
            patch_payload.pop("store_id", None)
            patch_payload.pop("id", None)
            response = sdk_client.knowledge_stores.update(
                str(store_id),
                patch_payload,
                tenant_slug=tenant_slug,
                options=request_options_builder(payload=payload, dry_run=False),
            )
        else:
            if not tenant_slug:
                return None, [{"error": "missing_fields", "fields": ["tenant_slug"]}]
            response = sdk_client.knowledge_stores.create(
                payload,
                str(tenant_slug),
                options=request_options_builder(payload=payload, dry_run=False),
            )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "create_or_update_knowledge_store_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "create_or_update_knowledge_store_failed", "detail": str(exc)}]


def delete(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    store_id = payload.get("store_id") or payload.get("id")
    if not store_id:
        return None, [{"error": "missing_fields", "fields": ["store_id"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "store_id": str(store_id)}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.knowledge_stores.delete(
            str(store_id),
            tenant_slug=payload.get("tenant_slug"),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "delete_knowledge_store_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "delete_knowledge_store_failed", "detail": str(exc)}]


def stats(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    store_id = payload.get("store_id") or payload.get("id")
    if not store_id:
        return None, [{"error": "missing_fields", "fields": ["store_id"]}]

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.knowledge_stores.stats(str(store_id), tenant_slug=payload.get("tenant_slug"))
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "knowledge_store_stats_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "knowledge_store_stats_failed", "detail": str(exc)}]
