from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sdk import Client
from talmudpedia_control_sdk import ControlPlaneSDKError

from .shared import (
    augment_agent_response,
    call_agent_execute,
    control_client,
    evaluate_assertions,
    request_options,
    resolve_agent_id_by_slug,
)


def _extract_validation_errors(details: Any) -> List[Dict[str, Any]]:
    if not isinstance(details, dict):
        return []

    candidates = []
    if isinstance(details.get("errors"), list):
        candidates.append(details.get("errors"))

    detail_payload = details.get("detail")
    if isinstance(detail_payload, dict) and isinstance(detail_payload.get("errors"), list):
        candidates.append(detail_payload.get("errors"))
    elif isinstance(detail_payload, list):
        candidates.append(detail_payload)

    for candidate in candidates:
        normalized = [item for item in candidate if isinstance(item, dict)]
        if normalized:
            return normalized
    return []


def _sdk_error_payload(error_name: str, exc: ControlPlaneSDKError, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "error": error_name,
        "detail": str(exc),
        "code": exc.code,
        "http_status": exc.http_status,
    }
    if exc.details is not None:
        payload["details"] = exc.details
        validation_errors = _extract_validation_errors(exc.details)
        if validation_errors:
            payload["validation_errors"] = validation_errors

    for key, value in extra.items():
        if value is not None:
            payload[key] = value
    return payload


def list_agents(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    kwargs = {
        "status": payload.get("status"),
        "skip": int(payload.get("skip", 0) or 0),
        "limit": int(payload.get("limit", 50) or 50),
        "compact": bool(payload.get("compact", False)),
    }
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.agents.list(**kwargs)
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("list_agents_failed", exc)]
    except Exception as exc:
        return None, [{"error": "list_agents_failed", "detail": str(exc)}]


def get_agent(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    agent_id = payload.get("agent_id") or payload.get("id")
    if not agent_id:
        return None, [{"error": "missing_fields", "fields": ["agent_id"]}]

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.agents.get(str(agent_id))
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("get_agent_failed", exc, agent_id=agent_id)]
    except Exception as exc:
        return None, [{"error": "get_agent_failed", "detail": str(exc), "agent_id": agent_id}]


def create_or_update(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    agent_id = payload.get("agent_id") or payload.get("id")

    if dry_run:
        skipped: Dict[str, Any] = {"status": "skipped", "dry_run": True}
        if agent_id:
            skipped["agent_id"] = str(agent_id)
        else:
            skipped["name"] = payload.get("name")
        return skipped, []

    try:
        sdk_client = control_client_factory(client)
        if agent_id:
            patch_payload = dict(payload.get("patch")) if isinstance(payload.get("patch"), dict) else dict(payload)
            patch_payload.pop("agent_id", None)
            patch_payload.pop("id", None)
            method = str(payload.get("method", "PATCH")).upper()
            response = sdk_client.agents.update(
                str(agent_id),
                patch_payload,
                method=method,
                options=request_options_builder(payload=payload, dry_run=False),
            )
        else:
            response = sdk_client.agents.create(
                payload,
                options=request_options_builder(payload=payload, dry_run=False),
            )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("create_or_update_agent_failed", exc, agent_id=agent_id)]
    except Exception as exc:
        return None, [{"error": "create_or_update_agent_failed", "detail": str(exc), "agent_id": agent_id}]


def create(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    return create_or_update(
        client,
        payload,
        dry_run,
        control_client_factory=control_client_factory,
        request_options_builder=request_options_builder,
    )


def update(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    if not (payload.get("agent_id") or payload.get("id")):
        return None, [{"error": "missing_fields", "fields": ["agent_id"]}]
    return create_or_update(
        client,
        payload,
        dry_run,
        control_client_factory=control_client_factory,
        request_options_builder=request_options_builder,
    )


def publish(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    agent_id = payload.get("agent_id") or payload.get("id")
    if not agent_id:
        return None, [{"error": "missing_fields", "fields": ["agent_id"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "agent_id": str(agent_id)}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.agents.publish(
            str(agent_id),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("publish_agent_failed", exc, agent_id=agent_id)]
    except Exception as exc:
        return None, [{"error": "publish_agent_failed", "detail": str(exc), "agent_id": agent_id}]


def validate(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    agent_id = payload.get("agent_id") or payload.get("id")
    if not agent_id:
        return None, [{"error": "missing_fields", "fields": ["agent_id"]}]

    validation_payload = payload.get("validation") if isinstance(payload.get("validation"), dict) else payload.get("payload")
    if not isinstance(validation_payload, dict):
        validation_payload = {}

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.agents.validate(str(agent_id), validation_payload)
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("validate_agent_failed", exc, agent_id=agent_id)]
    except Exception as exc:
        return None, [{"error": "validate_agent_failed", "detail": str(exc), "agent_id": agent_id}]


def execute(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    resolve_agent_id_by_slug_fn=resolve_agent_id_by_slug,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    agent_id = payload.get("agent_id") or payload.get("id")
    agent_slug = payload.get("agent_slug") or payload.get("slug")
    if not agent_id and agent_slug:
        agent_id = resolve_agent_id_by_slug_fn(
            client,
            str(agent_slug),
            control_client_factory=control_client_factory,
        )
    if not agent_id:
        return None, [{"error": "missing_fields", "fields": ["agent_id or agent_slug"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "agent_id": agent_id}, []

    input_text, messages, context = resolve_agent_input(payload)
    request_payload = {
        "input": input_text,
        "messages": messages or [],
        "context": context or {},
    }

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.agents.execute(str(agent_id), request_payload)
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("run_agent_failed", exc, agent_id=agent_id)]
    except Exception as exc:
        return None, [{"error": "run_agent_failed", "detail": str(exc), "agent_id": agent_id}]


def start_run(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    agent_id = payload.get("agent_id") or payload.get("id")
    if not agent_id:
        return None, [{"error": "missing_fields", "fields": ["agent_id"]}]

    run_payload = payload.get("run") if isinstance(payload.get("run"), dict) else payload.get("payload")
    if not isinstance(run_payload, dict):
        run_payload = {}

    if dry_run:
        return {
            "status": "skipped",
            "dry_run": True,
            "agent_id": str(agent_id),
            "request": run_payload,
        }, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.agents.start_run(str(agent_id), run_payload)
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("start_run_failed", exc, agent_id=agent_id)]
    except Exception as exc:
        return None, [{"error": "start_run_failed", "detail": str(exc), "agent_id": agent_id}]


def resume_run(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    run_id = payload.get("run_id")
    if not run_id:
        return None, [{"error": "missing_fields", "fields": ["run_id"]}]

    run_payload = payload.get("run") if isinstance(payload.get("run"), dict) else payload.get("payload")
    if not isinstance(run_payload, dict):
        run_payload = {}

    if dry_run:
        return {
            "status": "skipped",
            "dry_run": True,
            "run_id": str(run_id),
            "request": run_payload,
        }, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.agents.resume_run(str(run_id), run_payload)
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("resume_run_failed", exc, run_id=run_id)]
    except Exception as exc:
        return None, [{"error": "resume_run_failed", "detail": str(exc), "run_id": run_id}]


def get_run(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    run_id = payload.get("run_id")
    if not run_id:
        return None, [{"error": "missing_fields", "fields": ["run_id"]}]

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.agents.get_run(
            str(run_id),
            include_tree=bool(payload.get("include_tree", False)),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("get_run_failed", exc, run_id=run_id)]
    except Exception as exc:
        return None, [{"error": "get_run_failed", "detail": str(exc), "run_id": run_id}]


def get_run_tree(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    run_id = payload.get("run_id")
    if not run_id:
        return None, [{"error": "missing_fields", "fields": ["run_id"]}]

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.agents.get_run_tree(str(run_id))
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("get_run_tree_failed", exc, run_id=run_id)]
    except Exception as exc:
        return None, [{"error": "get_run_tree_failed", "detail": str(exc), "run_id": run_id}]


def run_tests(
    client: Client,
    tests: List[Dict[str, Any]],
    dry_run: bool,
    *,
    resolve_agent_id_by_slug_fn=resolve_agent_id_by_slug,
    call_agent_execute_fn=call_agent_execute,
    augment_agent_response_fn=augment_agent_response,
    evaluate_assertions_fn=evaluate_assertions,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    errors: List[Dict[str, Any]] = []

    if dry_run:
        return {"status": "skipped", "dry_run": True, "tests": [], "summary": {"passed": 0, "failed": 0}}, errors

    if not isinstance(tests, list) or not tests:
        errors.append({"error": "missing_tests"})
        return {"tests": [], "summary": {"passed": 0, "failed": 0}}, errors

    results: List[Dict[str, Any]] = []
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
            agent_id = resolve_agent_id_by_slug_fn(client, str(agent_slug))

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
            response = call_agent_execute_fn(client, str(agent_id), {"input": input_text, "messages": messages, "context": context})
            response = augment_agent_response_fn(response)
        except Exception as exc:
            results.append({"name": name, "status": "failed", "details": str(exc), "run_id": None})
            failed += 1
            continue

        assertions = test.get("assertions") if isinstance(test.get("assertions"), list) else []
        passed_assertions, details = evaluate_assertions_fn(response, assertions)

        if passed_assertions:
            results.append({"name": name, "status": "passed", "details": details, "run_id": response.get("run_id")})
            passed += 1
        else:
            results.append({"name": name, "status": "failed", "details": details, "run_id": response.get("run_id")})
            failed += 1

    return {"tests": results, "summary": {"passed": passed, "failed": failed}}, errors


def resolve_agent_input(payload: Dict[str, Any]) -> Tuple[Optional[str], List[Dict[str, Any]], Dict[str, Any]]:
    input_text = None
    messages: List[Dict[str, Any]] = []
    context: Dict[str, Any] = {}

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
