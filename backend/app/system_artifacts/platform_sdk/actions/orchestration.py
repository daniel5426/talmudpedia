from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sdk import Client
from talmudpedia_control_sdk import ControlPlaneSDKError

from .shared import control_client, request_options


def resolve_caller_run_id(inputs: Dict[str, Any], payload: Dict[str, Any]) -> Optional[str]:
    caller_run_id = payload.get("caller_run_id") or inputs.get("caller_run_id")
    if caller_run_id:
        return str(caller_run_id)

    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    if not context and isinstance(inputs.get("context"), dict):
        context = inputs.get("context")

    run_id = context.get("run_id")
    if run_id:
        return str(run_id)

    return None


def spawn_run(
    client: Client,
    inputs: Dict[str, Any],
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    caller_run_id = resolve_caller_run_id(inputs, payload)
    target_agent_id = payload.get("target_agent_id") or inputs.get("target_agent_id")
    scope_subset = payload.get("scope_subset") or inputs.get("scope_subset") or payload.get("requested_scopes") or inputs.get("requested_scopes") or []
    if not isinstance(scope_subset, list):
        scope_subset = []

    idempotency_key = payload.get("idempotency_key") or inputs.get("idempotency_key")
    mapped_input_payload = payload.get("mapped_input_payload") if isinstance(payload.get("mapped_input_payload"), dict) else {}
    if not mapped_input_payload and isinstance(payload.get("input"), dict):
        mapped_input_payload = payload.get("input")

    missing: List[str] = []
    if not caller_run_id:
        missing.append("caller_run_id")
    if not idempotency_key:
        missing.append("idempotency_key")
    if not target_agent_id:
        missing.append("target_agent_id")
    if not scope_subset:
        missing.append("scope_subset")
    if missing:
        return None, [{"error": "missing_fields", "fields": missing}]

    request_payload = {
        "caller_run_id": caller_run_id,
        "parent_node_id": payload.get("parent_node_id") or inputs.get("parent_node_id"),
        "target_agent_id": target_agent_id,
        "mapped_input_payload": mapped_input_payload,
        "failure_policy": payload.get("failure_policy"),
        "timeout_s": payload.get("timeout_s"),
        "scope_subset": scope_subset,
        "idempotency_key": idempotency_key,
        "start_background": payload.get("start_background", True),
    }

    if dry_run:
        request_payload["dry_run"] = True
        return {"status": "skipped", "dry_run": True, "request": request_payload}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.orchestration.spawn_run(
            request_payload,
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "spawn_run_failed",
            "detail": str(exc),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "spawn_run_failed", "detail": str(exc)}]


def spawn_group(
    client: Client,
    inputs: Dict[str, Any],
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    caller_run_id = resolve_caller_run_id(inputs, payload)
    targets = payload.get("targets") if isinstance(payload.get("targets"), list) else []
    scope_subset = payload.get("scope_subset") or inputs.get("scope_subset") or payload.get("requested_scopes") or inputs.get("requested_scopes") or []
    if not isinstance(scope_subset, list):
        scope_subset = []

    idempotency_key_prefix = payload.get("idempotency_key_prefix") or inputs.get("idempotency_key_prefix")

    missing: List[str] = []
    if not caller_run_id:
        missing.append("caller_run_id")
    if not idempotency_key_prefix:
        missing.append("idempotency_key_prefix")
    if not targets:
        missing.append("targets")
    if not scope_subset:
        missing.append("scope_subset")
    if missing:
        return None, [{"error": "missing_fields", "fields": missing}]

    request_payload = {
        "caller_run_id": caller_run_id,
        "parent_node_id": payload.get("parent_node_id") or inputs.get("parent_node_id"),
        "targets": targets,
        "failure_policy": payload.get("failure_policy"),
        "join_mode": payload.get("join_mode", "all"),
        "quorum_threshold": payload.get("quorum_threshold"),
        "timeout_s": payload.get("timeout_s"),
        "scope_subset": scope_subset,
        "idempotency_key_prefix": idempotency_key_prefix,
        "start_background": payload.get("start_background", True),
    }

    if dry_run:
        request_payload["dry_run"] = True
        return {"status": "skipped", "dry_run": True, "request": request_payload}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.orchestration.spawn_group(
            request_payload,
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "spawn_group_failed",
            "detail": str(exc),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "spawn_group_failed", "detail": str(exc)}]


def join(
    client: Client,
    inputs: Dict[str, Any],
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    caller_run_id = resolve_caller_run_id(inputs, payload)
    group_id = payload.get("orchestration_group_id") or inputs.get("orchestration_group_id") or payload.get("group_id")

    missing: List[str] = []
    if not caller_run_id:
        missing.append("caller_run_id")
    if not group_id:
        missing.append("orchestration_group_id")
    if missing:
        return None, [{"error": "missing_fields", "fields": missing}]

    request_payload = {
        "caller_run_id": caller_run_id,
        "orchestration_group_id": group_id,
        "mode": payload.get("mode"),
        "quorum_threshold": payload.get("quorum_threshold"),
        "timeout_s": payload.get("timeout_s"),
    }

    if dry_run:
        return {"status": "skipped", "dry_run": True, "request": request_payload}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.orchestration.join(
            request_payload,
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "join_failed",
            "detail": str(exc),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "join_failed", "detail": str(exc)}]


def cancel_subtree(
    client: Client,
    inputs: Dict[str, Any],
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    caller_run_id = resolve_caller_run_id(inputs, payload)
    run_id = payload.get("run_id") or inputs.get("run_id")

    missing: List[str] = []
    if not caller_run_id:
        missing.append("caller_run_id")
    if not run_id:
        missing.append("run_id")
    if missing:
        return None, [{"error": "missing_fields", "fields": missing}]

    request_payload = {
        "caller_run_id": caller_run_id,
        "run_id": run_id,
        "include_root": bool(payload.get("include_root", True)),
        "reason": payload.get("reason"),
    }

    if dry_run:
        return {"status": "skipped", "dry_run": True, "request": request_payload}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.orchestration.cancel_subtree(
            request_payload,
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "cancel_subtree_failed",
            "detail": str(exc),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "cancel_subtree_failed", "detail": str(exc)}]


def evaluate_and_replan(
    client: Client,
    inputs: Dict[str, Any],
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    caller_run_id = resolve_caller_run_id(inputs, payload)
    run_id = payload.get("run_id") or inputs.get("run_id")

    missing: List[str] = []
    if not caller_run_id:
        missing.append("caller_run_id")
    if not run_id:
        missing.append("run_id")
    if missing:
        return None, [{"error": "missing_fields", "fields": missing}]

    request_payload = {
        "caller_run_id": caller_run_id,
        "run_id": run_id,
    }

    if dry_run:
        return {"status": "skipped", "dry_run": True, "request": request_payload}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.orchestration.evaluate_and_replan(
            request_payload,
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "evaluate_and_replan_failed",
            "detail": str(exc),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "evaluate_and_replan_failed", "detail": str(exc)}]


def query_tree(
    client: Client,
    inputs: Dict[str, Any],
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    run_id = payload.get("run_id") or inputs.get("run_id") or resolve_caller_run_id(inputs, payload)
    if not run_id:
        return None, [{"error": "missing_fields", "fields": ["run_id"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "request": {"run_id": run_id}}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.orchestration.query_tree(str(run_id))
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "query_tree_failed",
            "detail": str(exc),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "query_tree_failed", "detail": str(exc)}]
