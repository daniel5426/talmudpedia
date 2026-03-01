"""
Platform SDK Tool Artifact

Executes platform control-plane actions via SDK method wrappers.
"""
from __future__ import annotations

import json
import os
import asyncio
from typing import Any, Dict, List, Optional, Tuple

from sdk import Client
from talmudpedia_control_sdk import ControlPlaneClient, ControlPlaneSDKError
from app.services.orchestration_policy_service import (
    ORCHESTRATION_SURFACE_OPTION_B,
    is_orchestration_surface_enabled,
)


ACTION_ALIASES = {
    "fetch_catalog": "catalog.list_capabilities",
    "create_artifact_draft": "artifacts.create_or_update_draft",
    "promote_artifact": "artifacts.promote",
    "create_tool": "tools.create_or_update",
    "run_agent": "agents.execute",
    "run_tests": "agents.run_tests",
    "spawn_run": "orchestration.spawn_run",
    "spawn_group": "orchestration.spawn_group",
    "join": "orchestration.join",
    "cancel_subtree": "orchestration.cancel_subtree",
    "evaluate_and_replan": "orchestration.evaluate_and_replan",
    "query_tree": "orchestration.query_tree",
}

DEPRECATED_ACTIONS = {"validate_plan", "execute_plan"}

ORCHESTRATION_PRIMITIVE_ACTIONS = {
    "orchestration.spawn_run",
    "orchestration.spawn_group",
    "orchestration.join",
    "orchestration.cancel_subtree",
    "orchestration.evaluate_and_replan",
    "orchestration.query_tree",
}

PRIVILEGED_ACTION_SCOPES = {
    "catalog.list_capabilities": ["pipelines.catalog.read"],
    "catalog.get_rag_operator_catalog": ["pipelines.catalog.read"],
    "catalog.list_rag_operators": ["pipelines.catalog.read"],
    "catalog.get_rag_operator": ["pipelines.catalog.read"],
    "catalog.list_agent_operators": ["pipelines.catalog.read"],
    "artifacts.create_or_update_draft": ["artifacts.write"],
    "artifacts.promote": ["artifacts.write"],
    "tools.create_or_update": ["tools.write"],
    "agents.execute": ["agents.execute"],
    "agents.run_tests": ["agents.run_tests"],
    "orchestration.spawn_run": ["agents.execute"],
    "orchestration.spawn_group": ["agents.execute"],
    "orchestration.join": ["agents.execute"],
    "orchestration.cancel_subtree": ["agents.execute"],
    "orchestration.evaluate_and_replan": ["agents.execute"],
    "orchestration.query_tree": ["agents.execute"],
    "respond": [],
}


def execute(state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    inputs = _resolve_inputs(state, context)
    inputs = _coerce_json_text(inputs)

    payload = inputs.get("payload") if isinstance(inputs.get("payload"), dict) else {}
    tests = inputs.get("tests") if isinstance(inputs.get("tests"), list) else []
    if not tests and isinstance(payload.get("tests"), list):
        tests = payload.get("tests") or []
    dry_run = bool(inputs.get("dry_run") or payload.get("dry_run", False))
    explicit_action = _extract_explicit_action(inputs, payload)
    action = _resolve_action(explicit_action, inputs, payload, [], tests)
    tenant_for_flags = _resolve_effective_tenant_id(inputs, payload, state, context)

    if action == "noop":
        output = {
            "result": {
                "status": "validation_error",
                "reason": "missing_required_action",
                "message": "Platform SDK calls require an explicit action.",
            },
            "errors": [{
                "error": "missing_action",
                "code": "MISSING_REQUIRED_FIELD",
                "message": "Missing required field: action",
                "http_status": 422,
                "retryable": False,
            }],
            "action": "noop",
            "dry_run": dry_run,
        }
        return {
            "context": output,
            "tool_outputs": [output],
        }

    if action in DEPRECATED_ACTIONS:
        output = {
            "result": {
                "status": "validation_error",
                "reason": "deprecated_action",
                "message": f"Action '{action}' is deprecated; use domain action wrappers.",
            },
            "errors": [{
                "error": "deprecated_action",
                "code": "INVALID_ARGUMENT",
                "action": action,
                "message": f"Action '{action}' is no longer supported.",
                "http_status": 422,
                "retryable": False,
            }],
            "action": action,
            "dry_run": dry_run,
        }
        return {
            "context": output,
            "tool_outputs": [output],
        }

    canonical_action = _canonicalize_action(action)
    gated_actions = {canonical_action} if canonical_action in ORCHESTRATION_PRIMITIVE_ACTIONS else set()

    if gated_actions and not is_orchestration_surface_enabled(
        surface=ORCHESTRATION_SURFACE_OPTION_B,
        tenant_id=tenant_for_flags,
    ):
        disabled_actions = sorted(gated_actions)
        output = {
            "result": {
                "status": "feature_disabled",
                "surface": ORCHESTRATION_SURFACE_OPTION_B,
                "actions": disabled_actions,
                "tenant_id": tenant_for_flags,
            },
            "errors": [{
                "error": "feature_disabled",
                "surface": ORCHESTRATION_SURFACE_OPTION_B,
                "actions": disabled_actions,
            }],
            "action": action,
            "dry_run": dry_run,
        }
        return {
            "context": output,
            "tool_outputs": [output],
        }

    required_scopes = _resolve_required_scopes(action=canonical_action)
    base_url, api_key, tenant_id, extra_headers = _resolve_auth(
        inputs,
        payload,
        state=state,
        context=context,
        action=canonical_action,
        required_scopes=required_scopes,
    )
    client = Client(base_url=base_url, api_key=api_key, tenant_id=tenant_id, extra_headers=extra_headers)
    if api_key and not client.headers.get("Authorization"):
        client.headers["Authorization"] = f"Bearer {api_key}"
    if not client.headers.get("X-SDK-Contract"):
        client.headers["X-SDK-Contract"] = "1"

    errors: List[Dict[str, Any]] = []

    if canonical_action == "catalog.list_capabilities":
        catalog_result = _fetch_catalog(client, payload)
        if isinstance(catalog_result, tuple):
            result, errors = catalog_result
        else:
            result = catalog_result
    elif canonical_action == "catalog.get_rag_operator_catalog":
        result, errors = _catalog_get_rag_operator_catalog(client, payload)
    elif canonical_action == "catalog.list_rag_operators":
        result, errors = _catalog_list_rag_operators(client, payload)
    elif canonical_action == "catalog.get_rag_operator":
        result, errors = _catalog_get_rag_operator(client, payload)
    elif canonical_action == "catalog.list_agent_operators":
        result, errors = _catalog_list_agent_operators(client)
    elif canonical_action == "artifacts.create_or_update_draft":
        result, errors = _create_artifact_draft(client, payload, dry_run)
    elif canonical_action == "artifacts.promote":
        result, errors = _promote_artifact(client, payload, dry_run)
    elif canonical_action == "tools.create_or_update":
        result, errors = _create_tool(client, payload, dry_run)
    elif canonical_action == "agents.execute":
        result, errors = _run_agent(client, payload, dry_run)
    elif canonical_action == "agents.run_tests":
        result, errors = _run_tests(client, tests, dry_run)
    elif canonical_action == "orchestration.spawn_run":
        result, errors = _orchestration_spawn_run(client, inputs, payload, dry_run)
    elif canonical_action == "orchestration.spawn_group":
        result, errors = _orchestration_spawn_group(client, inputs, payload, dry_run)
    elif canonical_action == "orchestration.join":
        result, errors = _orchestration_join(client, inputs, payload, dry_run)
    elif canonical_action == "orchestration.cancel_subtree":
        result, errors = _orchestration_cancel_subtree(client, inputs, payload, dry_run)
    elif canonical_action == "orchestration.evaluate_and_replan":
        result, errors = _orchestration_evaluate_and_replan(client, inputs, payload, dry_run)
    elif canonical_action == "orchestration.query_tree":
        result, errors = _orchestration_query_tree(client, inputs, payload, dry_run)
    elif canonical_action == "respond":
        result = {"message": payload.get("message") or inputs.get("message") or ""}
    else:
        result = {"message": f"Unknown action '{action}'."}
        errors.append({
            "error": "unknown_action",
            "code": "INVALID_ARGUMENT",
            "action": action,
            "message": f"Unsupported action: {action}",
            "http_status": 422,
            "retryable": False,
        })

    output = {
        "result": result,
        "errors": errors,
        "action": canonical_action,
        "dry_run": dry_run,
    }

    return {
        "context": output,
        "tool_outputs": [output],
    }


def _extract_explicit_action(inputs: Dict[str, Any], payload: Dict[str, Any]) -> Optional[str]:
    action = inputs.get("action")
    if isinstance(action, str) and action.strip():
        return action.strip()
    payload_action = payload.get("action")
    if isinstance(payload_action, str) and payload_action.strip():
        return payload_action.strip()
    return None


def _resolve_action(
    explicit_action: Optional[str],
    inputs: Dict[str, Any],
    payload: Dict[str, Any],
    steps: List[Dict[str, Any]],
    tests: List[Dict[str, Any]],
) -> str:
    if explicit_action:
        return explicit_action
    return "noop"


def _canonicalize_action(action: str) -> str:
    return ACTION_ALIASES.get(action, action)


def _resolve_effective_tenant_id(
    inputs: Dict[str, Any],
    payload: Dict[str, Any],
    state: Optional[Dict[str, Any]],
    context: Optional[Dict[str, Any]],
) -> Optional[str]:
    state_ctx = state.get("context") if isinstance(state, dict) and isinstance(state.get("context"), dict) else {}
    tool_ctx = context if isinstance(context, dict) else {}
    tenant_id = (
        payload.get("tenant_id")
        or inputs.get("tenant_id")
        or state_ctx.get("tenant_id")
        or tool_ctx.get("tenant_id")
    )
    if tenant_id is None:
        return None
    return str(tenant_id)


def _resolve_inputs(state: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(context, dict):
        ctx_inputs = context.get("inputs")
        if isinstance(ctx_inputs, dict) and ctx_inputs:
            return ctx_inputs

    state_context = state.get("context")
    if isinstance(state_context, dict) and state_context:
        return state_context

    last_output = (state.get("state") or {}).get("last_agent_output")
    if isinstance(last_output, dict) and last_output:
        return last_output

    messages = state.get("messages") or []
    if messages:
        last_msg = messages[-1]
        if isinstance(last_msg, dict):
            content = last_msg.get("content")
        else:
            content = getattr(last_msg, "content", str(last_msg))
        return {"text": content}

    return {}


def _coerce_json_text(inputs: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(inputs, dict):
        return {}

    # If we got a single text field, try to parse JSON, handling ``` fences.
    if set(inputs.keys()) == {"text"} and isinstance(inputs.get("text"), str):
        text = inputs.get("text", "").strip()
        if text.startswith("```"):
            text = text.lstrip("`")
            # Drop optional leading language label
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1 :]
            if text.endswith("```"):
                text = text[: -3]
            text = text.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return inputs
    return inputs


def _resolve_required_scopes(action: str) -> List[str]:
    scopes = set(PRIVILEGED_ACTION_SCOPES.get(action, []))
    return sorted(scopes)


def _resolve_auth(
    inputs: Dict[str, Any],
    payload: Dict[str, Any],
    state: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    action: Optional[str] = None,
    required_scopes: Optional[List[str]] = None,
) -> Tuple[str, Optional[str], Optional[str], Dict[str, str]]:
    base_url = (
        payload.get("base_url")
        or inputs.get("base_url")
        or os.getenv("PLATFORM_BASE_URL")
        or os.getenv("API_BASE_URL")
        or "http://localhost:8000"
    )

    state_ctx = state.get("context") if isinstance(state, dict) else {}
    if state_ctx is None:
        state_ctx = {}
    tool_ctx = context if isinstance(context, dict) else {}
    if tool_ctx is None:
        tool_ctx = {}

    tenant_id = (
        payload.get("tenant_id")
        or inputs.get("tenant_id")
        or state_ctx.get("tenant_id")
        or tool_ctx.get("tenant_id")
    )
    if tenant_id is not None:
        tenant_id = str(tenant_id)

    token = (
        payload.get("token")
        or inputs.get("token")
        or payload.get("api_key")
        or inputs.get("api_key")
        or payload.get("bearer_token")
        or inputs.get("bearer_token")
        or state_ctx.get("token")
        or tool_ctx.get("token")
    )
    auth_ctx = tool_ctx.get("auth") if isinstance(tool_ctx.get("auth"), dict) else {}
    if not token and isinstance(auth_ctx.get("token"), str):
        token = auth_ctx.get("token")
    if not token and isinstance(auth_ctx.get("bearer_token"), str):
        token = auth_ctx.get("bearer_token")

    if not action:
        raise ValueError("Action is required for auth scope resolution.")

    scope_list = required_scopes or _resolve_required_scopes(action)
    if scope_list:
        delegated_token = None
        mint_token_cb = auth_ctx.get("mint_token")
        if callable(mint_token_cb):
            try:
                delegated_token = _run_async(
                    mint_token_cb(
                        scope_subset=scope_list,
                        audience="talmudpedia-internal-api",
                    )
                )
            except Exception as exc:
                raise ValueError(
                    f"Action '{action}' requires delegated workload token; workload token mint failed: {exc}"
                ) from exc

        if delegated_token:
            token = delegated_token
        elif not token:
            raise ValueError(
                f"Action '{action}' requires bearer token; missing caller auth context"
            )
    elif not token:
        raise ValueError(f"Action '{action}' requires bearer token; missing caller auth context")

    if not tenant_id:
        raise ValueError(f"Action '{action}' requires explicit tenant_id.")

    extra_headers = {}
    if isinstance(payload.get("headers"), dict):
        extra_headers.update(payload.get("headers"))
    if isinstance(inputs.get("headers"), dict):
        extra_headers.update(inputs.get("headers"))

    return base_url, token, tenant_id, extra_headers


def _run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        # Avoid crashing if a loop is already running
        return None


def _fetch_catalog(client: Client, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    rag_catalog, rag_errors = _catalog_get_rag_operator_catalog(client, payload)
    agent_catalog, agent_errors = _catalog_list_agent_operators(client)
    errors = rag_errors + agent_errors

    rag_summary = _summarize_rag_catalog(rag_catalog)
    agent_summary = _summarize_agent_catalog(agent_catalog)

    result = {
        "summary": {
            "rag": rag_summary,
            "agent": agent_summary,
        }
    }

    if payload.get("include_raw"):
        result["rag_catalog"] = rag_catalog
        result["agent_catalog"] = agent_catalog

    return result, errors


def _catalog_get_rag_operator_catalog(client: Client, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    try:
        tenant_slug = payload.get("tenant_slug")
        sdk_client = _control_client(client)
        response = sdk_client.catalog.get_rag_operator_catalog(tenant_slug=tenant_slug)
        data = response.get("data")
        if not isinstance(data, dict):
            return {}, []
        return data, []
    except ControlPlaneSDKError as exc:
        return {}, [{
            "error": "catalog_get_rag_operator_catalog_failed",
            "detail": str(exc),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return {}, [{"error": "catalog_get_rag_operator_catalog_failed", "detail": str(exc)}]


def _catalog_list_rag_operators(client: Client, payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    try:
        tenant_slug = payload.get("tenant_slug")
        sdk_client = _control_client(client)
        response = sdk_client.catalog.list_rag_operators(tenant_slug=tenant_slug)
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "catalog_list_rag_operators_failed",
            "detail": str(exc),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "catalog_list_rag_operators_failed", "detail": str(exc)}]


def _catalog_get_rag_operator(client: Client, payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    operator_id = payload.get("operator_id")
    if not operator_id:
        return None, [{"error": "missing_fields", "fields": ["operator_id"]}]
    try:
        tenant_slug = payload.get("tenant_slug")
        sdk_client = _control_client(client)
        response = sdk_client.catalog.get_rag_operator(str(operator_id), tenant_slug=tenant_slug)
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "catalog_get_rag_operator_failed",
            "detail": str(exc),
            "operator_id": operator_id,
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "catalog_get_rag_operator_failed", "detail": str(exc), "operator_id": operator_id}]


def _catalog_list_agent_operators(client: Client) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    try:
        sdk_client = _control_client(client)
        response = sdk_client.catalog.list_agent_operators()
        data = response.get("data")
        if isinstance(data, list):
            return data, []
        return [], []
    except ControlPlaneSDKError as exc:
        return [], [{
            "error": "catalog_list_agent_operators_failed",
            "detail": str(exc),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return [], [{"error": "catalog_list_agent_operators_failed", "detail": str(exc)}]


def _summarize_rag_catalog(rag_catalog: Any) -> Dict[str, Any]:
    if not isinstance(rag_catalog, dict):
        return {"total": 0, "categories": {}}

    categories = {}
    total = 0
    examples = {}
    for cat, specs in rag_catalog.items():
        if not isinstance(specs, list):
            continue
        count = len(specs)
        total += count
        categories[cat] = count
        examples[cat] = [s.get("operator_id") for s in specs[:3] if isinstance(s, dict)]

    return {
        "total": total,
        "categories": categories,
        "examples": examples,
        "fields": ["operator_id", "display_name", "category", "input_type", "output_type", "version", "scope"],
    }


def _summarize_agent_catalog(agent_catalog: Any) -> Dict[str, Any]:
    if not isinstance(agent_catalog, list):
        return {"total": 0, "categories": {}}

    categories = {}
    total = len(agent_catalog)
    examples = {}
    for spec in agent_catalog:
        if not isinstance(spec, dict):
            continue
        cat = spec.get("category", "general")
        categories[cat] = categories.get(cat, 0) + 1
        if cat not in examples:
            examples[cat] = []
        if len(examples[cat]) < 3:
            examples[cat].append(spec.get("type"))

    return {
        "total": total,
        "categories": categories,
        "examples": examples,
        "fields": ["type", "display_name", "category", "reads", "writes"],
    }


def _resolve_caller_run_id(inputs: Dict[str, Any], payload: Dict[str, Any]) -> Optional[str]:
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


def _orchestration_spawn_run(client: Client, inputs: Dict[str, Any], payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    errors: List[Dict[str, Any]] = []
    caller_run_id = _resolve_caller_run_id(inputs, payload)
    target_agent_id = payload.get("target_agent_id") or inputs.get("target_agent_id")
    target_agent_slug = payload.get("target_agent_slug") or payload.get("target_slug") or inputs.get("target_agent_slug")
    scope_subset = payload.get("scope_subset") or inputs.get("scope_subset") or payload.get("requested_scopes") or inputs.get("requested_scopes") or []
    if not isinstance(scope_subset, list):
        scope_subset = []
    idempotency_key = payload.get("idempotency_key") or inputs.get("idempotency_key")
    mapped_input_payload = payload.get("mapped_input_payload") if isinstance(payload.get("mapped_input_payload"), dict) else {}
    if not mapped_input_payload and isinstance(payload.get("input"), dict):
        mapped_input_payload = payload.get("input")

    missing = []
    if not caller_run_id:
        missing.append("caller_run_id")
    if not idempotency_key:
        missing.append("idempotency_key")
    if not target_agent_id and not target_agent_slug:
        missing.append("target_agent_id or target_agent_slug")
    if not scope_subset:
        missing.append("scope_subset")
    if missing:
        return None, [{"error": "missing_fields", "fields": missing}]

    request_payload = {
        "caller_run_id": caller_run_id,
        "parent_node_id": payload.get("parent_node_id") or inputs.get("parent_node_id"),
        "target_agent_id": target_agent_id,
        "target_agent_slug": target_agent_slug,
        "mapped_input_payload": mapped_input_payload,
        "failure_policy": payload.get("failure_policy"),
        "timeout_s": payload.get("timeout_s"),
        "scope_subset": scope_subset,
        "idempotency_key": idempotency_key,
        "start_background": payload.get("start_background", True),
    }

    if dry_run:
        request_payload["dry_run"] = True
        return {"status": "skipped", "dry_run": True, "request": request_payload}, errors

    try:
        sdk_client = _control_client(client)
        response = sdk_client.orchestration.spawn_run(
            request_payload,
            options=_request_options(payload=payload, dry_run=False),
        )
        return response.get("data"), errors
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "spawn_run_failed",
            "detail": str(exc),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "spawn_run_failed", "detail": str(exc)}]


def _orchestration_spawn_group(client: Client, inputs: Dict[str, Any], payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    errors: List[Dict[str, Any]] = []
    caller_run_id = _resolve_caller_run_id(inputs, payload)
    targets = payload.get("targets") if isinstance(payload.get("targets"), list) else []
    scope_subset = payload.get("scope_subset") or inputs.get("scope_subset") or payload.get("requested_scopes") or inputs.get("requested_scopes") or []
    if not isinstance(scope_subset, list):
        scope_subset = []
    idempotency_key_prefix = payload.get("idempotency_key_prefix") or inputs.get("idempotency_key_prefix")

    missing = []
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
        return {"status": "skipped", "dry_run": True, "request": request_payload}, errors

    try:
        sdk_client = _control_client(client)
        response = sdk_client.orchestration.spawn_group(
            request_payload,
            options=_request_options(payload=payload, dry_run=False),
        )
        return response.get("data"), errors
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "spawn_group_failed",
            "detail": str(exc),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "spawn_group_failed", "detail": str(exc)}]


def _orchestration_join(client: Client, inputs: Dict[str, Any], payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    caller_run_id = _resolve_caller_run_id(inputs, payload)
    group_id = payload.get("orchestration_group_id") or inputs.get("orchestration_group_id") or payload.get("group_id")
    missing = []
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
        sdk_client = _control_client(client)
        response = sdk_client.orchestration.join(
            request_payload,
            options=_request_options(payload=payload, dry_run=False),
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


def _orchestration_cancel_subtree(client: Client, inputs: Dict[str, Any], payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    caller_run_id = _resolve_caller_run_id(inputs, payload)
    run_id = payload.get("run_id") or inputs.get("run_id")
    missing = []
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
        sdk_client = _control_client(client)
        response = sdk_client.orchestration.cancel_subtree(
            request_payload,
            options=_request_options(payload=payload, dry_run=False),
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


def _orchestration_evaluate_and_replan(client: Client, inputs: Dict[str, Any], payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    caller_run_id = _resolve_caller_run_id(inputs, payload)
    run_id = payload.get("run_id") or inputs.get("run_id")
    missing = []
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
        sdk_client = _control_client(client)
        response = sdk_client.orchestration.evaluate_and_replan(
            request_payload,
            options=_request_options(payload=payload, dry_run=False),
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


def _orchestration_query_tree(client: Client, inputs: Dict[str, Any], payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    run_id = payload.get("run_id") or inputs.get("run_id") or _resolve_caller_run_id(inputs, payload)
    if not run_id:
        return None, [{"error": "missing_fields", "fields": ["run_id"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "request": {"run_id": run_id}}, []

    try:
        sdk_client = _control_client(client)
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


def _request_options(
    *,
    step: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
    dry_run: bool,
) -> Dict[str, Any]:
    source: Dict[str, Any] = {}
    if isinstance(payload, dict):
        source.update(payload)
    if isinstance(step, dict):
        source.update(step)
    options: Dict[str, Any] = {"dry_run": dry_run}
    if source.get("validate_only") is not None:
        options["validate_only"] = bool(source.get("validate_only"))
    if source.get("idempotency_key"):
        options["idempotency_key"] = str(source.get("idempotency_key"))
    if isinstance(source.get("request_metadata"), dict):
        options["request_metadata"] = source.get("request_metadata")
    return options


def _control_client(client: Client) -> ControlPlaneClient:
    token = getattr(client, "api_key", None)
    auth_header = None
    if isinstance(getattr(client, "headers", None), dict):
        auth_header = client.headers.get("Authorization")
    if isinstance(auth_header, str) and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    tenant_id = None
    if isinstance(getattr(client, "headers", None), dict):
        tenant_id = client.headers.get("X-Tenant-ID")
    if not tenant_id:
        tenant_id = getattr(client, "tenant_id", None)
    return ControlPlaneClient(
        base_url=client.base_url,
        token=token,
        tenant_id=tenant_id,
        timeout=60.0,
    )


def _create_artifact_draft(client: Client, payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
    artifact_id = payload.get("artifact_id") or payload.get("id")
    name = payload.get("name")
    python_code = payload.get("python_code") or payload.get("code")

    if not artifact_id and (not name or not python_code):
        return None, [{"error": "missing_fields", "fields": ["name", "python_code"]}]

    if dry_run:
        skipped = {"status": "skipped", "dry_run": True}
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
        sdk_client = _control_client(client)
        if artifact_id:
            response = sdk_client.artifacts.update_draft(
                str(artifact_id),
                request_payload,
                tenant_slug=tenant_slug,
                options=_request_options(payload=payload, dry_run=False),
            )
        else:
            response = sdk_client.artifacts.create_draft(
                request_payload,
                tenant_slug=tenant_slug,
                options=_request_options(payload=payload, dry_run=False),
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


def _promote_artifact(client: Client, payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
    artifact_id = payload.get("artifact_id") or payload.get("id")
    if not artifact_id:
        return None, [{"error": "missing_fields", "fields": ["artifact_id"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "artifact_id": artifact_id}, []

    namespace = payload.get("namespace")
    if not namespace:
        return None, [{"error": "missing_fields", "fields": ["namespace"]}]
    version = payload.get("version")
    tenant_slug = payload.get("tenant_slug")

    try:
        sdk_client = _control_client(client)
        response = sdk_client.artifacts.promote(
            artifact_id,
            namespace=namespace,
            version=version,
            tenant_slug=tenant_slug,
            options=_request_options(payload=payload, dry_run=False),
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


def _create_tool(client: Client, payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
    tool_id = payload.get("tool_id") or payload.get("id")
    if not tool_id:
        missing = []
        if not payload.get("name"):
            missing.append("name")
        if not payload.get("slug"):
            missing.append("slug")
        if not payload.get("input_schema"):
            missing.append("input_schema")
        if not payload.get("output_schema"):
            missing.append("output_schema")
        if missing:
            return None, [{"error": "missing_fields", "fields": missing}]

    if dry_run:
        skipped = {"status": "skipped", "dry_run": True}
        if tool_id:
            skipped["tool_id"] = str(tool_id)
        else:
            skipped["slug"] = payload.get("slug")
        return skipped, []

    try:
        sdk_client = _control_client(client)
        if tool_id:
            patch_payload = dict(payload.get("patch")) if isinstance(payload.get("patch"), dict) else dict(payload)
            patch_payload.pop("tool_id", None)
            patch_payload.pop("id", None)
            response = sdk_client.tools.update(
                str(tool_id),
                patch_payload,
                options=_request_options(payload=payload, dry_run=False),
            )
        else:
            response = sdk_client.tools.create(
                payload,
                options=_request_options(payload=payload, dry_run=False),
            )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "create_tool_failed",
            "detail": str(exc),
            "slug": payload.get("slug"),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "create_tool_failed", "detail": str(exc), "slug": payload.get("slug")}]


def _run_agent(client: Client, payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
    agent_id = payload.get("agent_id") or payload.get("id")
    agent_slug = payload.get("agent_slug") or payload.get("slug")
    if not agent_id and agent_slug:
        agent_id = _resolve_agent_id_by_slug(client, agent_slug)
    if not agent_id:
        return None, [{"error": "missing_fields", "fields": ["agent_id or agent_slug"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "agent_id": agent_id}, []

    input_text, messages, context = _resolve_agent_input(payload)
    request_payload = {
        "input": input_text,
        "messages": messages or [],
        "context": context or {},
    }
    try:
        sdk_client = _control_client(client)
        response = sdk_client.agents.execute(agent_id, request_payload).get("data")
        return response, []
    except ControlPlaneSDKError as exc:
        return None, [{
            "error": "run_agent_failed",
            "detail": str(exc),
            "agent_id": agent_id,
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return None, [{"error": "run_agent_failed", "detail": str(exc), "agent_id": agent_id}]


def _run_tests(client: Client, tests: List[Dict[str, Any]], dry_run: bool) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    errors: List[Dict[str, Any]] = []
    if dry_run:
        return {"status": "skipped", "dry_run": True, "tests": [], "summary": {"passed": 0, "failed": 0}}, errors

    if not isinstance(tests, list) or not tests:
        errors.append({"error": "missing_tests"})
        return {"tests": [], "summary": {"passed": 0, "failed": 0}}, errors

    results = []
    passed = 0
    failed = 0

    for idx, test in enumerate(tests):
        if not isinstance(test, dict):
            errors.append({"test": idx, "error": "invalid_test"})
            failed += 1
            continue

        name = test.get("name") or f"test_{idx + 1}"
        target = test.get("agent_target") if isinstance(test.get("agent_target"), dict) else {}
        agent_id = target.get("agent_id") or test.get("agent_id") or target.get("id")
        agent_slug = target.get("agent_slug") or test.get("agent_slug") or target.get("slug")
        if not agent_id and agent_slug:
            agent_id = _resolve_agent_id_by_slug(client, agent_slug)

        if not agent_id:
            errors.append({"test": name, "error": "missing_agent_target"})
            results.append({"name": name, "status": "failed", "details": "Missing agent target", "run_id": None})
            failed += 1
            continue

        input_block = test.get("input") if isinstance(test.get("input"), dict) else {}
        input_text = input_block.get("text") or test.get("text") or test.get("input_text")
        context = input_block.get("context") or test.get("context") or {}
        messages = input_block.get("messages") or test.get("messages") or []
        if not isinstance(messages, list):
            messages = []
        if not isinstance(context, dict):
            context = {}

        try:
            response = _call_agent_execute(client, agent_id, {"input": input_text, "messages": messages, "context": context})
            response = _augment_agent_response(response)
        except Exception as exc:
            results.append({"name": name, "status": "failed", "details": str(exc), "run_id": None})
            failed += 1
            continue

        assertions = test.get("assertions") if isinstance(test.get("assertions"), list) else []
        passed_assertions, details = _evaluate_assertions(response, assertions)

        if passed_assertions:
            results.append({"name": name, "status": "passed", "details": details, "run_id": response.get("run_id")})
            passed += 1
        else:
            results.append({"name": name, "status": "failed", "details": details, "run_id": response.get("run_id")})
            failed += 1

    summary = {"passed": passed, "failed": failed}
    return {"tests": results, "summary": summary}, errors


def _resolve_agent_input(payload: Dict[str, Any]) -> Tuple[Optional[str], List[Dict[str, Any]], Dict[str, Any]]:
    input_text = None
    messages = []
    context = {}

    input_block = payload.get("input")
    if isinstance(input_block, dict):
        input_text = input_block.get("text") or input_block.get("input") or input_block.get("input_text")
        messages = input_block.get("messages") or []
        context = input_block.get("context") or {}
    elif isinstance(input_block, str):
        input_text = input_block

    if input_text is None:
        input_text = payload.get("text") or payload.get("input_text")
    if not messages:
        messages = payload.get("messages") or []
    if not context:
        context = payload.get("context") or {}

    if not isinstance(messages, list):
        messages = []
    if not isinstance(context, dict):
        context = {}

    return input_text, messages, context


def _resolve_agent_id_by_slug(client: Client, agent_slug: str) -> Optional[str]:
    if not agent_slug:
        return None
    page_size = 200
    sdk_client = _control_client(client)
    for page in range(0, 10):
        try:
            response = sdk_client.agents.list(skip=page * page_size, limit=page_size, compact=True)
            payload = response.get("data")
            agents: Any
            if isinstance(payload, dict):
                agents = payload.get("agents") or payload.get("items") or []
            else:
                agents = payload or []
            if not isinstance(agents, list):
                return None
            for agent in agents:
                if isinstance(agent, dict) and agent.get("slug") == agent_slug:
                    return agent.get("id")
            if len(agents) < page_size:
                return None
        except Exception:
            return None
    return None


def _call_agent_execute(client: Client, agent_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    sdk_client = _control_client(client)
    response = sdk_client.agents.execute(agent_id, payload)
    data = response.get("data")
    return data if isinstance(data, dict) else {"output": {"text": str(data)}}


def _augment_agent_response(response: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(response, dict):
        return {"output": {"text": str(response)}}
    output = response.get("output")
    if isinstance(output, dict):
        text = output.get("text")
        if isinstance(text, str):
            try:
                output["json"] = json.loads(text)
            except Exception:
                pass
    return response


def _evaluate_assertions(response: Dict[str, Any], assertions: List[Dict[str, Any]]) -> Tuple[bool, List[Dict[str, Any]]]:
    if not assertions:
        return True, []
    results = []
    passed = True
    for assertion in assertions:
        res = _evaluate_assertion(response, assertion)
        results.append(res)
        if not res.get("passed"):
            passed = False
    return passed, results


def _evaluate_assertion(response: Dict[str, Any], assertion: Dict[str, Any]) -> Dict[str, Any]:
    atype = (assertion or {}).get("type") or "exact"
    path = (assertion or {}).get("path")
    expected = (assertion or {}).get("expected")
    actual = _resolve_json_path(response, path) if path else response

    if atype == "contains":
        ok = _assert_contains(actual, expected)
    elif atype in {"exact", "jsonpath"}:
        ok = _assert_exact(actual, expected)
    else:
        return {
            "type": atype,
            "path": path,
            "expected": expected,
            "actual": actual,
            "passed": False,
            "error": "unsupported_assertion_type",
        }

    return {
        "type": atype,
        "path": path,
        "expected": expected,
        "actual": actual,
        "passed": ok,
    }


def _assert_contains(actual: Any, expected: Any) -> bool:
    if actual is None:
        return False
    if isinstance(actual, (list, tuple, set)):
        return expected in actual
    if isinstance(actual, dict):
        if expected in actual.keys():
            return True
        if expected in actual.values():
            return True
    try:
        return str(expected) in json.dumps(actual, ensure_ascii=False)
    except Exception:
        return str(expected) in str(actual)


def _assert_exact(actual: Any, expected: Any) -> bool:
    if isinstance(actual, (dict, list)) or isinstance(expected, (dict, list)):
        return actual == expected
    return str(actual) == str(expected)


def _resolve_json_path(data: Any, path: Optional[str]) -> Any:
    if path is None:
        return data
    tokens = _parse_json_path(str(path))
    current = data
    for token in tokens:
        if isinstance(token, int):
            if isinstance(current, list) and 0 <= token < len(current):
                current = current[token]
            else:
                return None
        else:
            if isinstance(current, dict) and token in current:
                current = current[token]
            else:
                return None
    return current


def _parse_json_path(path: str) -> List[Any]:
    cleaned = path.strip()
    if cleaned.startswith("$."):
        cleaned = cleaned[2:]
    elif cleaned.startswith("$"):
        cleaned = cleaned[1:]

    tokens: List[Any] = []
    buffer = ""
    i = 0
    while i < len(cleaned):
        char = cleaned[i]
        if char == ".":
            if buffer:
                tokens.append(buffer)
                buffer = ""
            i += 1
            continue
        if char == "[":
            if buffer:
                tokens.append(buffer)
                buffer = ""
            i += 1
            end = cleaned.find("]", i)
            if end == -1:
                token = cleaned[i:]
                i = len(cleaned)
            else:
                token = cleaned[i:end]
                i = end + 1
            token = token.strip().strip('"').strip("'")
            if token.isdigit():
                tokens.append(int(token))
            elif token:
                tokens.append(token)
            continue
        buffer += char
        i += 1
    if buffer:
        tokens.append(buffer)
    return tokens
