from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sdk import Client
from talmudpedia_control_sdk import ControlPlaneSDKError

from .shared import control_client


def list_pending(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.workload_security.list_pending_scope_policies()
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "list_pending_scope_policies_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "list_pending_scope_policies_failed", "detail": str(exc)}]


def approve_policy(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    principal_id = payload.get("principal_id")
    approved_scopes = payload.get("approved_scopes")
    if not isinstance(approved_scopes, list):
        approved_scopes = []

    missing: List[str] = []
    if not principal_id:
        missing.append("principal_id")
    if not approved_scopes:
        missing.append("approved_scopes")
    if missing:
        return None, [{"error": "missing_fields", "fields": missing}]

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.workload_security.approve_scope_policy(str(principal_id), approved_scopes)
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "approve_scope_policy_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "approve_scope_policy_failed", "detail": str(exc)}]


def reject_policy(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    principal_id = payload.get("principal_id")
    if not principal_id:
        return None, [{"error": "missing_fields", "fields": ["principal_id"]}]

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.workload_security.reject_scope_policy(str(principal_id))
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "reject_scope_policy_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "reject_scope_policy_failed", "detail": str(exc)}]


def list_approvals(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.workload_security.list_action_approvals(
            subject_type=payload.get("subject_type"),
            subject_id=payload.get("subject_id"),
            action_scope=payload.get("action_scope"),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "list_action_approvals_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "list_action_approvals_failed", "detail": str(exc)}]


def decide_approval(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    request_payload = payload.get("decision") if isinstance(payload.get("decision"), dict) else payload.get("payload")
    if not isinstance(request_payload, dict):
        request_payload = payload

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.workload_security.decide_action_approval(request_payload)
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "decide_action_approval_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "decide_action_approval_failed", "detail": str(exc)}]
