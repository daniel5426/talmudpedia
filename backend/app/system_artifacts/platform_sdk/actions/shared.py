from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from sdk import Client
from talmudpedia_control_sdk import ControlPlaneClient


def request_options(
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


def control_client(client: Client) -> ControlPlaneClient:
    token = getattr(client, "api_key", None)
    auth_header = None
    if isinstance(getattr(client, "headers", None), dict):
        auth_header = client.headers.get("Authorization")
    if isinstance(auth_header, str) and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()

    organization_id = None
    if isinstance(getattr(client, "headers", None), dict):
        organization_id = client.headers.get("X-Organization-ID")
    if not organization_id:
        organization_id = getattr(client, "organization_id", None)

    return ControlPlaneClient(
        base_url=client.base_url,
        token=token,
        organization_id=organization_id,
        timeout=60.0,
    )



def call_agent_execute(
    client: Client,
    agent_id: str,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Dict[str, Any]:
    sdk_client = control_client_factory(client)
    response = sdk_client.agents.execute(agent_id, payload)
    data = response.get("data")
    return data if isinstance(data, dict) else {"output": {"text": str(data)}}


def augment_agent_response(response: Dict[str, Any]) -> Dict[str, Any]:
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


def evaluate_assertions(response: Dict[str, Any], assertions: List[Dict[str, Any]]) -> Tuple[bool, List[Dict[str, Any]]]:
    if not assertions:
        return True, []

    results: List[Dict[str, Any]] = []
    passed = True
    for assertion in assertions:
        res = evaluate_assertion(response, assertion)
        results.append(res)
        if not res.get("passed"):
            passed = False

    return passed, results


def evaluate_assertion(response: Dict[str, Any], assertion: Dict[str, Any]) -> Dict[str, Any]:
    atype = (assertion or {}).get("type") or "exact"
    path = (assertion or {}).get("path")
    expected = (assertion or {}).get("expected")
    actual = resolve_json_path(response, path) if path else response

    if atype == "contains":
        ok = assert_contains(actual, expected)
    elif atype in {"exact", "jsonpath"}:
        ok = assert_exact(actual, expected)
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


def assert_contains(actual: Any, expected: Any) -> bool:
    if actual is None:
        return False
    if isinstance(actual, (list, tuple, set)):
        return expected in actual
    if isinstance(actual, dict):
        if expected in actual.keys() or expected in actual.values():
            return True
    try:
        return str(expected) in json.dumps(actual, ensure_ascii=False)
    except Exception:
        return str(expected) in str(actual)


def assert_exact(actual: Any, expected: Any) -> bool:
    if isinstance(actual, (dict, list)) or isinstance(expected, (dict, list)):
        return actual == expected
    return str(actual) == str(expected)


def resolve_json_path(data: Any, path: Optional[str]) -> Any:
    if path is None:
        return data

    current = data
    for token in parse_json_path(str(path)):
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


def parse_json_path(path: str) -> List[Any]:
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
