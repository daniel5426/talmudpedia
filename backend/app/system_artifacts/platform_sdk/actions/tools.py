from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sdk import Client
from talmudpedia_control_sdk import ControlPlaneSDKError

from .shared import control_client, request_options


def list_tools(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    kwargs = {
        "scope": payload.get("scope"),
        "is_active": payload.get("is_active"),
        "status": payload.get("status"),
        "implementation_type": payload.get("implementation_type"),
        "tool_type": payload.get("tool_type"),
        "skip": int(payload.get("skip", 0) or 0),
        "limit": int(payload.get("limit", 20) or 20),
        "view": str(payload.get("view") or "summary"),
    }

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.tools.list(**kwargs)
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "list_tools_failed",
            "detail": str(exc),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "list_tools_failed", "detail": str(exc)}]


def get_tool(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    tool_id = payload.get("tool_id") or payload.get("id")
    if not tool_id:
        return None, [{"error": "missing_fields", "fields": ["tool_id"]}]

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.tools.get(str(tool_id))
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "get_tool_failed",
            "detail": str(exc),
            "tool_id": tool_id,
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "get_tool_failed", "detail": str(exc), "tool_id": tool_id}]


def create_or_update(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    tool_id = payload.get("tool_id") or payload.get("id")
    if not tool_id:
        missing: List[str] = []
        if not payload.get("name"):
            missing.append("name")
        if not payload.get("input_schema"):
            missing.append("input_schema")
        if not payload.get("output_schema"):
            missing.append("output_schema")
        if missing:
            return None, [{"error": "missing_fields", "fields": missing}]

    if dry_run:
        skipped: Dict[str, Any] = {"status": "skipped", "dry_run": True}
        if tool_id:
            skipped["tool_id"] = str(tool_id)
        else:
            skipped["name"] = payload.get("name")
        return skipped, []

    try:
        sdk_client = control_client_factory(client)
        if tool_id:
            patch_payload = dict(payload.get("patch")) if isinstance(payload.get("patch"), dict) else dict(payload)
            patch_payload.pop("tool_id", None)
            patch_payload.pop("id", None)
            response = sdk_client.tools.update(
                str(tool_id),
                patch_payload,
                options=request_options_builder(payload=payload, dry_run=False),
            )
        else:
            response = sdk_client.tools.create(
                payload,
                options=request_options_builder(payload=payload, dry_run=False),
            )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "create_tool_failed",
            "detail": str(exc),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "create_tool_failed", "detail": str(exc), "name": payload.get("name")}]


def publish(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    tool_id = payload.get("tool_id") or payload.get("id")
    if not tool_id:
        return None, [{"error": "missing_fields", "fields": ["tool_id"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "tool_id": str(tool_id)}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.tools.publish(
            str(tool_id),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "publish_tool_failed",
            "detail": str(exc),
            "tool_id": tool_id,
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "publish_tool_failed", "detail": str(exc), "tool_id": tool_id}]


def create_version(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    tool_id = payload.get("tool_id") or payload.get("id")
    new_version = payload.get("new_version") or payload.get("version")
    missing: List[str] = []
    if not tool_id:
        missing.append("tool_id")
    if not new_version:
        missing.append("new_version")
    if missing:
        return None, [{"error": "missing_fields", "fields": missing}]

    if dry_run:
        return {
            "status": "skipped",
            "dry_run": True,
            "tool_id": str(tool_id),
            "new_version": str(new_version),
        }, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.tools.create_version(
            str(tool_id),
            str(new_version),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "create_tool_version_failed",
            "detail": str(exc),
            "tool_id": tool_id,
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "create_tool_version_failed", "detail": str(exc), "tool_id": tool_id}]


def delete(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    tool_id = payload.get("tool_id") or payload.get("id")
    if not tool_id:
        return None, [{"error": "missing_fields", "fields": ["tool_id"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "tool_id": str(tool_id)}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.tools.delete(
            str(tool_id),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data") or {"deleted": True, "tool_id": str(tool_id)}, []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "delete_tool_failed",
            "detail": str(exc),
            "tool_id": tool_id,
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "delete_tool_failed", "detail": str(exc), "tool_id": tool_id}]
