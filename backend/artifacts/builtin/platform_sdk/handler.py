"""
Platform SDK Tool Artifact

Executes platform control-plane actions via SDK method wrappers.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sdk import Client
from talmudpedia_control_sdk import ControlPlaneClient
from app.services.orchestration_policy_service import (
    ORCHESTRATION_SURFACE_OPTION_B,
    is_orchestration_surface_enabled,
)

from .actions import agents as agent_actions
from .actions import artifacts as artifact_actions
from .actions import auth as auth_actions
from .actions import catalog as catalog_actions
from .actions import credentials as credential_actions
from .actions import knowledge_stores as knowledge_store_actions
from .actions import models as model_actions
from .actions import orchestration as orchestration_actions
from .actions import rag as rag_actions
from .actions import shared as shared_actions
from .actions import tools as tool_actions
from .actions import workload_security as workload_security_actions


ACTION_ALIASES = {
    "fetch_catalog": "catalog.list_capabilities",
    "create_agent": "agents.create",
    "update_agent": "agents.update",
    "run_agent_tests": "agents.run_tests",
    "create_pipeline": "rag.create_visual_pipeline",
    "update_pipeline": "rag.update_visual_pipeline",
    "compile_pipeline": "rag.compile_visual_pipeline",
    "register_asset": "artifacts.create_or_update_draft",
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
    "rag.list_pipelines": ["pipelines.read"],
    "rag.list_visual_pipelines": ["pipelines.read"],
    "rag.create_or_update_pipeline": ["pipelines.write"],
    "rag.create_visual_pipeline": ["pipelines.write"],
    "rag.update_visual_pipeline": ["pipelines.write"],
    "rag.compile_pipeline": ["pipelines.write"],
    "rag.compile_visual_pipeline": ["pipelines.write"],
    "rag.create_job": ["pipelines.write"],
    "rag.get_job": ["pipelines.read"],
    "rag.get_executable_pipeline": ["pipelines.read"],
    "rag.get_executable_input_schema": ["pipelines.read"],
    "rag.get_step_data": ["pipelines.read"],
    "artifacts.list": ["artifacts.read"],
    "artifacts.get": ["artifacts.read"],
    "artifacts.create_or_update_draft": ["artifacts.write"],
    "artifacts.promote": ["artifacts.write"],
    "artifacts.delete": ["artifacts.write"],
    "artifacts.test": ["artifacts.write"],
    "tools.list": ["tools.read"],
    "tools.get": ["tools.read"],
    "tools.create_or_update": ["tools.write"],
    "tools.publish": ["tools.write"],
    "tools.create_version": ["tools.write"],
    "tools.delete": ["tools.write"],
    "agents.list": ["agents.read"],
    "agents.get": ["agents.read"],
    "agents.create": ["agents.write"],
    "agents.update": ["agents.write"],
    "agents.create_or_update": ["agents.write"],
    "agents.publish": ["agents.write"],
    "agents.validate": ["agents.write"],
    "agents.execute": ["agents.execute"],
    "agents.start_run": ["agents.execute"],
    "agents.resume_run": ["agents.execute"],
    "agents.get_run": ["agents.execute"],
    "agents.get_run_tree": ["agents.execute"],
    "agents.run_tests": ["agents.run_tests"],
    "models.list": ["models.read"],
    "models.create_or_update": ["models.write"],
    "models.add_provider": ["models.write"],
    "models.update_provider": ["models.write"],
    "models.delete_provider": ["models.write"],
    "credentials.list": ["credentials.read"],
    "credentials.create_or_update": ["credentials.write"],
    "credentials.delete": ["credentials.write"],
    "credentials.usage": ["credentials.read"],
    "credentials.status": ["credentials.read"],
    "knowledge_stores.list": ["knowledge_stores.read"],
    "knowledge_stores.create_or_update": ["knowledge_stores.write"],
    "knowledge_stores.delete": ["knowledge_stores.write"],
    "knowledge_stores.stats": ["knowledge_stores.read"],
    "auth.create_delegation_grant": ["auth.write"],
    "auth.mint_workload_token": ["auth.write"],
    "workload_security.list_pending": ["workload_security.read"],
    "workload_security.approve_policy": ["workload_security.write"],
    "workload_security.reject_policy": ["workload_security.write"],
    "workload_security.list_approvals": ["workload_security.read"],
    "workload_security.decide_approval": ["workload_security.write"],
    "orchestration.spawn_run": ["agents.execute"],
    "orchestration.spawn_group": ["agents.execute"],
    "orchestration.join": ["agents.execute"],
    "orchestration.cancel_subtree": ["agents.execute"],
    "orchestration.evaluate_and_replan": ["agents.execute"],
    "orchestration.query_tree": ["agents.execute"],
    "respond": [],
}

DOMAIN_TOOL_ALLOWED_PREFIXES = {
    "platform-rag": ("rag.",),
    "platform-agents": ("agents.",),
    "platform-assets": ("tools.", "artifacts.", "models.", "credentials.", "knowledge_stores."),
    "platform-governance": ("auth.", "workload_security.", "orchestration."),
}

PUBLISH_ACTIONS = {
    "agents.publish",
    "tools.publish",
    "artifacts.promote",
}


def execute(state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    inputs = _resolve_inputs(state, context)
    inputs = _coerce_json_text(inputs)

    payload = dict(inputs.get("payload")) if isinstance(inputs.get("payload"), dict) else {}
    if inputs.get("idempotency_key") and not payload.get("idempotency_key"):
        payload["idempotency_key"] = inputs.get("idempotency_key")
    if isinstance(inputs.get("request_metadata"), dict) and not isinstance(payload.get("request_metadata"), dict):
        payload["request_metadata"] = inputs.get("request_metadata")
    if inputs.get("tenant_id") and not payload.get("tenant_id"):
        payload["tenant_id"] = inputs.get("tenant_id")
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
        return _finalize_output(output, inputs=inputs, payload=payload, tool_slug=None)

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
        return _finalize_output(output, inputs=inputs, payload=payload, tool_slug=None)

    canonical_action = _canonicalize_action(action)
    tool_slug = _resolve_tool_slug(inputs=inputs, payload=payload, state=state, context=context, config=config)
    domain_error = _validate_domain_action_access(canonical_action=canonical_action, tool_slug=tool_slug)
    if domain_error is not None:
        output = {
            "result": {
                "status": "validation_error",
                "reason": "tool_action_scope_mismatch",
                "message": domain_error["message"],
            },
            "errors": [domain_error],
            "action": canonical_action,
            "dry_run": dry_run,
        }
        return _finalize_output(output, inputs=inputs, payload=payload, tool_slug=tool_slug)

    if _is_mutating_action(canonical_action) and not tenant_for_flags:
        output = {
            "result": {
                "status": "validation_error",
                "reason": "missing_tenant_context",
                "message": f"Action '{canonical_action}' requires explicit tenant_id.",
            },
            "errors": [{
                "error": "missing_tenant_context",
                "code": "TENANT_REQUIRED",
                "action": canonical_action,
                "message": f"Action '{canonical_action}' requires explicit tenant_id.",
                "http_status": 422,
                "retryable": False,
            }],
            "action": canonical_action,
            "dry_run": dry_run,
        }
        return _finalize_output(output, inputs=inputs, payload=payload, tool_slug=tool_slug)

    if canonical_action in PUBLISH_ACTIONS and not _has_explicit_publish_intent(inputs, payload):
        output = {
            "result": {
                "status": "validation_error",
                "reason": "draft_first_policy",
                "message": f"Action '{canonical_action}' blocked by draft-first policy.",
                "next_actions": [
                    "Continue in draft mode and validate without publish/promote.",
                    "Set objective_flags.allow_publish=true to explicitly permit publish/promote.",
                ],
            },
            "errors": [{
                "error": "draft_first_policy_denied",
                "code": "DRAFT_FIRST_POLICY_DENIED",
                "action": canonical_action,
                "message": f"Action '{canonical_action}' requires explicit publish intent.",
                "http_status": 403,
                "retryable": False,
            }],
            "action": canonical_action,
            "dry_run": dry_run,
        }
        return _finalize_output(output, inputs=inputs, payload=payload, tool_slug=tool_slug)

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
        return _finalize_output(output, inputs=inputs, payload=payload, tool_slug=tool_slug)

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

    dispatched = _dispatch_action(
        canonical_action=canonical_action,
        client=client,
        inputs=inputs,
        payload=payload,
        tests=tests,
        dry_run=dry_run,
    )
    if dispatched is None:
        result = {"message": f"Unknown action '{action}'."}
        errors: List[Dict[str, Any]] = [{
            "error": "unknown_action",
            "code": "INVALID_ARGUMENT",
            "action": action,
            "message": f"Unsupported action: {action}",
            "http_status": 422,
            "retryable": False,
        }]
    else:
        result, errors = dispatched
    if any(str(err.get("code")) == "SENSITIVE_ACTION_APPROVAL_REQUIRED" for err in errors if isinstance(err, dict)):
        result = {
            "status": "blocked_approval",
            "reason": "approval_required",
            "message": "Action blocked pending approval.",
            "next_actions": [
                "Request approval for the blocked action.",
                "Retry the action after approval is granted.",
            ],
        }

    output = {
        "result": result,
        "errors": errors,
        "action": canonical_action,
        "dry_run": dry_run,
    }
    return _finalize_output(output, inputs=inputs, payload=payload, tool_slug=tool_slug)


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


def _resolve_tool_slug(
    *,
    inputs: Dict[str, Any],
    payload: Dict[str, Any],
    state: Optional[Dict[str, Any]],
    context: Optional[Dict[str, Any]],
    config: Optional[Dict[str, Any]],
) -> Optional[str]:
    candidates = [
        payload.get("tool_slug"),
        inputs.get("tool_slug"),
        (config or {}).get("tool_slug"),
        (context or {}).get("tool_slug"),
    ]
    state_ctx = state.get("context") if isinstance(state, dict) and isinstance(state.get("context"), dict) else {}
    candidates.append(state_ctx.get("tool_slug"))
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _validate_domain_action_access(canonical_action: str, tool_slug: Optional[str]) -> Optional[Dict[str, Any]]:
    if not tool_slug:
        return None
    prefixes = DOMAIN_TOOL_ALLOWED_PREFIXES.get(tool_slug)
    if not prefixes:
        return None
    if any(canonical_action.startswith(prefix) for prefix in prefixes):
        return None
    return {
        "error": "tool_action_scope_mismatch",
        "code": "SCOPE_DENIED",
        "tool_slug": tool_slug,
        "action": canonical_action,
        "message": f"Action '{canonical_action}' is not allowed by tool '{tool_slug}'.",
        "http_status": 403,
        "retryable": False,
    }


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

    if set(inputs.keys()) == {"text"} and isinstance(inputs.get("text"), str):
        text = inputs.get("text", "").strip()
        if text.startswith("```"):
            text = text.lstrip("`")
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1 :]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return inputs

    return inputs


def _extract_meta(inputs: Dict[str, Any], payload: Dict[str, Any], tool_slug: Optional[str]) -> Dict[str, Any]:
    request_metadata = payload.get("request_metadata") if isinstance(payload.get("request_metadata"), dict) else {}
    if not request_metadata and isinstance(inputs.get("request_metadata"), dict):
        request_metadata = inputs.get("request_metadata")

    idempotency_key = (
        payload.get("idempotency_key")
        or inputs.get("idempotency_key")
    )
    trace_id = (
        request_metadata.get("trace_id")
        or payload.get("trace_id")
        or inputs.get("trace_id")
        or f"trace-{uuid4()}"
    )
    request_id = (
        request_metadata.get("request_id")
        or payload.get("request_id")
        or inputs.get("request_id")
    )
    return {
        "trace_id": str(trace_id) if trace_id is not None else None,
        "request_id": str(request_id) if request_id is not None else None,
        "idempotency_key": str(idempotency_key) if idempotency_key else None,
        "idempotency_provided": bool(idempotency_key),
        "tool_slug": tool_slug,
    }


def _finalize_output(
    output: Dict[str, Any],
    *,
    inputs: Dict[str, Any],
    payload: Dict[str, Any],
    tool_slug: Optional[str],
) -> Dict[str, Any]:
    output["meta"] = _extract_meta(inputs=inputs, payload=payload, tool_slug=tool_slug)
    return {"context": output, "tool_outputs": [output]}


def _resolve_required_scopes(action: str) -> List[str]:
    scopes = set(PRIVILEGED_ACTION_SCOPES.get(action, []))
    return sorted(scopes)


def _is_mutating_action(action: str) -> bool:
    scopes = _resolve_required_scopes(action)
    if not scopes:
        return False
    return any(not scope.endswith(".read") for scope in scopes)


def _has_explicit_publish_intent(inputs: Dict[str, Any], payload: Dict[str, Any]) -> bool:
    candidates = [
        payload.get("allow_publish"),
        payload.get("publish_intent"),
        inputs.get("allow_publish"),
        inputs.get("publish_intent"),
    ]
    objective_flags = payload.get("objective_flags") if isinstance(payload.get("objective_flags"), dict) else {}
    if not objective_flags and isinstance(inputs.get("objective_flags"), dict):
        objective_flags = inputs.get("objective_flags")
    candidates.append(objective_flags.get("allow_publish"))

    for candidate in candidates:
        if isinstance(candidate, bool):
            return candidate
        if isinstance(candidate, str) and candidate.strip().lower() in {"1", "true", "yes", "publish"}:
            return True
    return False


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
            raise ValueError(f"Action '{action}' requires bearer token; missing caller auth context")
    elif not token:
        raise ValueError(f"Action '{action}' requires bearer token; missing caller auth context")

    if not tenant_id:
        raise ValueError(f"Action '{action}' requires explicit tenant_id.")

    extra_headers: Dict[str, str] = {}
    if isinstance(payload.get("headers"), dict):
        extra_headers.update(payload.get("headers"))
    if isinstance(inputs.get("headers"), dict):
        extra_headers.update(inputs.get("headers"))

    return base_url, token, tenant_id, extra_headers


def _run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        return None


# Compatibility wrappers retained for existing tests and monkeypatch hooks.
def _fetch_catalog(client: Client, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    return catalog_actions.list_capabilities(client, payload, control_client_factory=_control_client)


def _catalog_get_rag_operator_catalog(client: Client, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    return catalog_actions.get_rag_operator_catalog(client, payload, control_client_factory=_control_client)


def _catalog_list_rag_operators(client: Client, payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    return catalog_actions.list_rag_operators(client, payload, control_client_factory=_control_client)


def _catalog_get_rag_operator(client: Client, payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    return catalog_actions.get_rag_operator(client, payload, control_client_factory=_control_client)


def _catalog_list_agent_operators(client: Client) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    return catalog_actions.list_agent_operators(client, control_client_factory=_control_client)


def _create_artifact_draft(client: Client, payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    return artifact_actions.create_or_update_draft(
        client,
        payload,
        dry_run,
        control_client_factory=_control_client,
        request_options_builder=_request_options,
    )


def _promote_artifact(client: Client, payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    return artifact_actions.promote(
        client,
        payload,
        dry_run,
        control_client_factory=_control_client,
        request_options_builder=_request_options,
    )


def _create_tool(client: Client, payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    return tool_actions.create_or_update(
        client,
        payload,
        dry_run,
        control_client_factory=_control_client,
        request_options_builder=_request_options,
    )


def _run_agent(client: Client, payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    return agent_actions.execute(
        client,
        payload,
        dry_run,
        control_client_factory=_control_client,
        resolve_agent_id_by_slug_fn=_resolve_agent_id_by_slug,
    )


def _run_tests(client: Client, tests: List[Dict[str, Any]], dry_run: bool) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    return agent_actions.run_tests(
        client,
        tests,
        dry_run,
        resolve_agent_id_by_slug_fn=_resolve_agent_id_by_slug,
        call_agent_execute_fn=_call_agent_execute,
        augment_agent_response_fn=_augment_agent_response,
        evaluate_assertions_fn=_evaluate_assertions,
    )


def _resolve_caller_run_id(inputs: Dict[str, Any], payload: Dict[str, Any]) -> Optional[str]:
    return orchestration_actions.resolve_caller_run_id(inputs, payload)


def _orchestration_spawn_run(client: Client, inputs: Dict[str, Any], payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    return orchestration_actions.spawn_run(
        client,
        inputs,
        payload,
        dry_run,
        control_client_factory=_control_client,
        request_options_builder=_request_options,
    )


def _orchestration_spawn_group(client: Client, inputs: Dict[str, Any], payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    return orchestration_actions.spawn_group(
        client,
        inputs,
        payload,
        dry_run,
        control_client_factory=_control_client,
        request_options_builder=_request_options,
    )


def _orchestration_join(client: Client, inputs: Dict[str, Any], payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    return orchestration_actions.join(
        client,
        inputs,
        payload,
        dry_run,
        control_client_factory=_control_client,
        request_options_builder=_request_options,
    )


def _orchestration_cancel_subtree(client: Client, inputs: Dict[str, Any], payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    return orchestration_actions.cancel_subtree(
        client,
        inputs,
        payload,
        dry_run,
        control_client_factory=_control_client,
        request_options_builder=_request_options,
    )


def _orchestration_evaluate_and_replan(client: Client, inputs: Dict[str, Any], payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    return orchestration_actions.evaluate_and_replan(
        client,
        inputs,
        payload,
        dry_run,
        control_client_factory=_control_client,
        request_options_builder=_request_options,
    )


def _orchestration_query_tree(client: Client, inputs: Dict[str, Any], payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    return orchestration_actions.query_tree(
        client,
        inputs,
        payload,
        dry_run,
        control_client_factory=_control_client,
    )


def _request_options(
    *,
    step: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
    dry_run: bool,
) -> Dict[str, Any]:
    return shared_actions.request_options(step=step, payload=payload, dry_run=dry_run)


def _control_client(client: Client) -> ControlPlaneClient:
    return shared_actions.control_client(client)


def _resolve_agent_id_by_slug(client: Client, agent_slug: str) -> Optional[str]:
    return shared_actions.resolve_agent_id_by_slug(client, agent_slug, control_client_factory=_control_client)


def _call_agent_execute(client: Client, agent_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return shared_actions.call_agent_execute(client, agent_id, payload, control_client_factory=_control_client)


def _augment_agent_response(response: Dict[str, Any]) -> Dict[str, Any]:
    return shared_actions.augment_agent_response(response)


def _evaluate_assertions(response: Dict[str, Any], assertions: List[Dict[str, Any]]) -> Tuple[bool, List[Dict[str, Any]]]:
    return shared_actions.evaluate_assertions(response, assertions)


def _evaluate_assertion(response: Dict[str, Any], assertion: Dict[str, Any]) -> Dict[str, Any]:
    return shared_actions.evaluate_assertion(response, assertion)


def _assert_contains(actual: Any, expected: Any) -> bool:
    return shared_actions.assert_contains(actual, expected)


def _assert_exact(actual: Any, expected: Any) -> bool:
    return shared_actions.assert_exact(actual, expected)


def _resolve_json_path(data: Any, path: Optional[str]) -> Any:
    return shared_actions.resolve_json_path(data, path)


def _parse_json_path(path: str) -> List[Any]:
    return shared_actions.parse_json_path(path)


def _dispatch_action(
    *,
    canonical_action: str,
    client: Client,
    inputs: Dict[str, Any],
    payload: Dict[str, Any],
    tests: List[Dict[str, Any]],
    dry_run: bool,
) -> Optional[Tuple[Any, List[Dict[str, Any]]]]:
    handlers = {
        "catalog.list_capabilities": lambda: _fetch_catalog(client, payload),
        "catalog.get_rag_operator_catalog": lambda: _catalog_get_rag_operator_catalog(client, payload),
        "catalog.list_rag_operators": lambda: _catalog_list_rag_operators(client, payload),
        "catalog.get_rag_operator": lambda: _catalog_get_rag_operator(client, payload),
        "catalog.list_agent_operators": lambda: _catalog_list_agent_operators(client),
        "rag.list_pipelines": lambda: rag_actions.list_pipelines(client, payload, control_client_factory=_control_client),
        "rag.list_visual_pipelines": lambda: rag_actions.list_pipelines(client, payload, control_client_factory=_control_client),
        "rag.create_or_update_pipeline": lambda: rag_actions.create_or_update_pipeline(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "rag.create_visual_pipeline": lambda: rag_actions.create_visual_pipeline(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "rag.update_visual_pipeline": lambda: rag_actions.update_visual_pipeline(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "rag.compile_pipeline": lambda: rag_actions.compile_pipeline(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "rag.compile_visual_pipeline": lambda: rag_actions.compile_visual_pipeline(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "rag.create_job": lambda: rag_actions.create_job(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "rag.get_job": lambda: rag_actions.get_job(client, payload, control_client_factory=_control_client),
        "rag.get_executable_pipeline": lambda: rag_actions.get_executable_pipeline(client, payload, control_client_factory=_control_client),
        "rag.get_executable_input_schema": lambda: rag_actions.get_executable_input_schema(client, payload, control_client_factory=_control_client),
        "rag.get_step_data": lambda: rag_actions.get_step_data(client, payload, control_client_factory=_control_client),
        "artifacts.list": lambda: artifact_actions.list_artifacts(client, payload, control_client_factory=_control_client),
        "artifacts.get": lambda: artifact_actions.get_artifact(client, payload, control_client_factory=_control_client),
        "artifacts.create_or_update_draft": lambda: _create_artifact_draft(client, payload, dry_run),
        "artifacts.promote": lambda: _promote_artifact(client, payload, dry_run),
        "artifacts.delete": lambda: artifact_actions.delete(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "artifacts.test": lambda: artifact_actions.test_artifact(client, payload, control_client_factory=_control_client),
        "tools.list": lambda: tool_actions.list_tools(client, payload, control_client_factory=_control_client),
        "tools.get": lambda: tool_actions.get_tool(client, payload, control_client_factory=_control_client),
        "tools.create_or_update": lambda: _create_tool(client, payload, dry_run),
        "tools.publish": lambda: tool_actions.publish(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "tools.create_version": lambda: tool_actions.create_version(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "tools.delete": lambda: tool_actions.delete(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "agents.list": lambda: agent_actions.list_agents(client, payload, control_client_factory=_control_client),
        "agents.get": lambda: agent_actions.get_agent(client, payload, control_client_factory=_control_client),
        "agents.create": lambda: agent_actions.create(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "agents.update": lambda: agent_actions.update(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "agents.create_or_update": lambda: agent_actions.create_or_update(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "agents.publish": lambda: agent_actions.publish(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "agents.validate": lambda: agent_actions.validate(client, payload, control_client_factory=_control_client),
        "agents.execute": lambda: _run_agent(client, payload, dry_run),
        "agents.start_run": lambda: agent_actions.start_run(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "agents.resume_run": lambda: agent_actions.resume_run(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "agents.get_run": lambda: agent_actions.get_run(client, payload, control_client_factory=_control_client),
        "agents.get_run_tree": lambda: agent_actions.get_run_tree(client, payload, control_client_factory=_control_client),
        "agents.run_tests": lambda: _run_tests(client, tests, dry_run),
        "models.list": lambda: model_actions.list_models(client, payload, control_client_factory=_control_client),
        "models.create_or_update": lambda: model_actions.create_or_update(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "models.add_provider": lambda: model_actions.add_provider(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "models.update_provider": lambda: model_actions.update_provider(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "models.delete_provider": lambda: model_actions.delete_provider(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "credentials.list": lambda: credential_actions.list_credentials(client, payload, control_client_factory=_control_client),
        "credentials.create_or_update": lambda: credential_actions.create_or_update(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "credentials.delete": lambda: credential_actions.delete(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "credentials.usage": lambda: credential_actions.usage(client, payload, control_client_factory=_control_client),
        "credentials.status": lambda: credential_actions.status(client, payload, control_client_factory=_control_client),
        "knowledge_stores.list": lambda: knowledge_store_actions.list_knowledge_stores(client, payload, control_client_factory=_control_client),
        "knowledge_stores.create_or_update": lambda: knowledge_store_actions.create_or_update(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "knowledge_stores.delete": lambda: knowledge_store_actions.delete(client, payload, dry_run, control_client_factory=_control_client, request_options_builder=_request_options),
        "knowledge_stores.stats": lambda: knowledge_store_actions.stats(client, payload, control_client_factory=_control_client),
        "auth.create_delegation_grant": lambda: auth_actions.create_delegation_grant(client, payload, control_client_factory=_control_client),
        "auth.mint_workload_token": lambda: auth_actions.mint_workload_token(client, payload, control_client_factory=_control_client),
        "workload_security.list_pending": lambda: workload_security_actions.list_pending(client, payload, control_client_factory=_control_client),
        "workload_security.approve_policy": lambda: workload_security_actions.approve_policy(client, payload, control_client_factory=_control_client),
        "workload_security.reject_policy": lambda: workload_security_actions.reject_policy(client, payload, control_client_factory=_control_client),
        "workload_security.list_approvals": lambda: workload_security_actions.list_approvals(client, payload, control_client_factory=_control_client),
        "workload_security.decide_approval": lambda: workload_security_actions.decide_approval(client, payload, control_client_factory=_control_client),
        "orchestration.spawn_run": lambda: _orchestration_spawn_run(client, inputs, payload, dry_run),
        "orchestration.spawn_group": lambda: _orchestration_spawn_group(client, inputs, payload, dry_run),
        "orchestration.join": lambda: _orchestration_join(client, inputs, payload, dry_run),
        "orchestration.cancel_subtree": lambda: _orchestration_cancel_subtree(client, inputs, payload, dry_run),
        "orchestration.evaluate_and_replan": lambda: _orchestration_evaluate_and_replan(client, inputs, payload, dry_run),
        "orchestration.query_tree": lambda: _orchestration_query_tree(client, inputs, payload, dry_run),
        "respond": lambda: ({ "message": payload.get("message") or inputs.get("message") or "" }, []),
    }
    handler_fn = handlers.get(canonical_action)
    if handler_fn is None:
        return None
    return handler_fn()
