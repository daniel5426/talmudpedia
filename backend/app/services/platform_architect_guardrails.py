from __future__ import annotations

from collections import defaultdict
import json
from threading import Lock
from typing import Any


_LOCK = Lock()
_RUN_FAILURE_STATE: dict[str, dict[str, Any]] = {}
_BLOCK_IMMEDIATELY_CODES = {
    "MISSING_REQUIRED_FIELD",
    "NON_CANONICAL_PLATFORM_SDK_INPUT",
    "INVALID_JSON",
}
_MUTATION_ACTION_PREFIXES = (
    "agents.graph.",
    "rag.graph.",
)
_MUTATION_ACTION_NAMES = {
    "agents.update",
    "rag.update_visual_pipeline",
    "agents.create",
    "rag.create_visual_pipeline",
}
_VALIDATION_ACTIONS = {
    "agents.graph.validate_patch",
    "rag.graph.validate_patch",
    "agents.nodes.validate",
    "agents.validate",
    "rag.compile_visual_pipeline",
    "rag.compile_pipeline",
}


class PlatformArchitectBlockedError(RuntimeError):
    def __init__(self, blocker: dict[str, Any]):
        self.blocker = blocker
        super().__init__(blocker.get("message") or "Platform architect repair loop blocked")


def enforce_platform_architect_guardrails(
    *,
    tool_slug: str | None,
    tool_result: Any,
    input_data: dict[str, Any] | None,
    node_context: dict[str, Any] | None,
    emitter: Any | None,
) -> None:
    if not _is_platform_architect(node_context):
        return
    if not isinstance(tool_slug, str) or not tool_slug.startswith("platform-"):
        return

    envelope = _extract_sdk_envelope(tool_result)
    if not envelope:
        return

    action = str(envelope.get("action") or "").strip()
    if not action:
        return

    run_id = str((node_context or {}).get("run_id") or "")
    if not run_id:
        return
    node_id = str((node_context or {}).get("node_id") or "tool_node")
    errors = [item for item in list(envelope.get("errors") or []) if isinstance(item, dict)]

    if not errors:
        if _is_mutation_action(action) or action in _VALIDATION_ACTIONS:
            _record_success(run_id, action)
        return

    if not _is_mutation_action(action):
        return

    normalized_code = _normalized_error_code(errors)
    fingerprint = _failure_fingerprint(action, errors)
    blocker = _record_failure(run_id, action, fingerprint)
    blocker.update(
        {
            "target_resource": _target_resource(input_data or {}),
            "attempted_action": action,
            "normalized_failure_code": normalized_code,
            "last_validation_details": _validation_details(errors),
        }
    )

    if emitter:
        emitter.emit_internal_event(
            "architect.repair_attempted",
            {
                "action": action,
                "failure_fingerprint": fingerprint,
                "normalized_failure_code": normalized_code,
                "attempt_count": blocker["attempt_count"],
                "target_resource": blocker["target_resource"],
            },
            node_id=node_id,
            category="architect",
        )

    if normalized_code in _BLOCK_IMMEDIATELY_CODES or blocker["attempt_count"] >= 2:
        blocker["message"] = (
            "Platform architect stopped after repeated mutation failure. "
            f"action={action} code={normalized_code} target={blocker['target_resource']}"
        )
        if emitter:
            emitter.emit_internal_event(
                "architect.repair_blocked",
                blocker,
                node_id=node_id,
                category="architect",
            )
            emitter.emit_internal_event(
                "architect.progress_stalled",
                blocker,
                node_id=node_id,
                category="architect",
            )
        raise PlatformArchitectBlockedError(blocker)


def _extract_sdk_envelope(tool_result: Any) -> dict[str, Any] | None:
    if not isinstance(tool_result, dict):
        return None
    context = tool_result.get("context")
    if isinstance(context, dict) and "action" in context and "errors" in context:
        return context
    if "action" in tool_result and "errors" in tool_result:
        return tool_result
    return None


def _is_platform_architect(node_context: dict[str, Any] | None) -> bool:
    state_context = (node_context or {}).get("state_context")
    if not isinstance(state_context, dict):
        return False
    return str(state_context.get("agent_slug") or "").strip() == "platform-architect"


def _is_mutation_action(action: str) -> bool:
    return action in _MUTATION_ACTION_NAMES or any(action.startswith(prefix) for prefix in _MUTATION_ACTION_PREFIXES)


def _record_success(run_id: str, action: str) -> None:
    with _LOCK:
        state = _RUN_FAILURE_STATE.setdefault(
            run_id,
            {"failure_counts": defaultdict(int), "mutation_succeeded": False},
        )
        if _is_mutation_action(action):
            state["mutation_succeeded"] = True
        state["failure_counts"].clear()


def _record_failure(run_id: str, action: str, fingerprint: str) -> dict[str, Any]:
    with _LOCK:
        state = _RUN_FAILURE_STATE.setdefault(
            run_id,
            {"failure_counts": defaultdict(int), "mutation_succeeded": False},
        )
        state["failure_counts"][fingerprint] += 1
        return {
            "failure_fingerprint": fingerprint,
            "attempt_count": int(state["failure_counts"][fingerprint]),
            "mutation_succeeded": bool(state.get("mutation_succeeded")),
            "recommended_next_repair_action": _recommended_next_repair_action(action),
        }


def _normalized_error_code(errors: list[dict[str, Any]]) -> str:
    for error in errors:
        code = error.get("code")
        if code:
            return str(code)
    return "UNKNOWN_ERROR"


def _validation_details(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for error in errors:
        if isinstance(error.get("validation_errors"), list):
            details.extend(item for item in error["validation_errors"] if isinstance(item, dict))
            continue
        raw_details = error.get("details")
        if isinstance(raw_details, dict) and isinstance(raw_details.get("errors"), list):
            details.extend(item for item in raw_details["errors"] if isinstance(item, dict))
    return details


def _failure_fingerprint(action: str, errors: list[dict[str, Any]]) -> str:
    payload = {
        "action": action,
        "code": _normalized_error_code(errors),
        "validation": [
            {
                "code": item.get("code"),
                "field": item.get("field") or item.get("path"),
                "message": item.get("message"),
            }
            for item in _validation_details(errors)
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _target_resource(input_data: dict[str, Any]) -> str:
    for key in ("agent_id", "pipeline_id", "id", "node_id"):
        value = input_data.get(key)
        if value:
            return f"{key}:{value}"
    payload = input_data.get("payload")
    if isinstance(payload, dict):
        for key in ("agent_id", "pipeline_id", "id", "node_id"):
            value = payload.get(key)
            if value:
                return f"{key}:{value}"
    return "unknown"


def _recommended_next_repair_action(action: str) -> str:
    if action.startswith("agents.graph.") or action == "agents.update":
        return "Read the current agent graph, validate one corrected mutation, and stop if the same error repeats."
    if action.startswith("rag.graph.") or action == "rag.update_visual_pipeline":
        return "Read the current pipeline graph, validate one corrected mutation, and stop if the same error repeats."
    return "Inspect persisted state, apply one corrected mutation, then validate."
