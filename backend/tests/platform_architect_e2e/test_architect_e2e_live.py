from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import uuid
from dataclasses import asdict
from typing import Any, Dict
from uuid import UUID

import pytest
import requests
from sqlalchemy import select
from talmudpedia_control_sdk import ControlPlaneClient

from app.core.scope_registry import get_required_scopes_for_action
from app.services.architect_mode_service import ArchitectMode, ArchitectModeService
from tests.platform_architect_e2e.db_checks import check_agent_run_exists, resolve_organization_slug
from tests.platform_architect_e2e.reporting import E2EReport
from tests.platform_architect_e2e.scenario_matrix import SCENARIOS, ScenarioDefinition
from tests.platform_architect_e2e.verifiers import (
    contains_action_evidence,
    contains_token,
    extract_assistant_text,
    extract_first_json_object,
)


TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "paused"}
DEFAULT_TEST_BASE_URL = "http://localhost:8000"
DEFAULT_TEST_API_KEY = ""
DEFAULT_TEST_ORGANIZATION_ID = ""
DEFAULT_TEST_PROJECT_ID = ""
DEFAULT_TEST_USER_EMAIL = "danielbenassaya2626@gmail.com"
DEFAULT_TEST_CHAT_MODEL_SLUG = "gpt-5-mini-2025-08-07"


def _run_async(coro: Any) -> Any:
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _decode_jwt_sub(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload_part = parts[1]
    payload_part += "=" * (-len(payload_part) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload_part.encode("utf-8")).decode("utf-8")
        payload = json.loads(raw)
    except Exception:
        return None
    subject = payload.get("sub")
    if subject is None:
        return None
    return str(subject)


def _build_scope_requirements() -> tuple[set[str], dict[str, list[str]]]:
    required_scopes: set[str] = set()
    scope_to_actions: dict[str, list[str]] = {}
    for scenario in SCENARIOS:
        action_scopes = get_required_scopes_for_action(scenario.target_action)
        for scope in action_scopes:
            required_scopes.add(scope)
            scope_to_actions.setdefault(scope, []).append(scenario.target_action)
    return required_scopes, scope_to_actions


async def _compute_scope_preflight(
    *,
    organization_id: str,
    architect_agent_id: str,
    initiator_user_id: str | None,
    required_scopes: set[str],
) -> dict[str, Any]:
    del organization_id, architect_agent_id
    if not initiator_user_id:
        return {
            "ok": True,
            "required_scopes": sorted(required_scopes),
            "effective_scopes": ["*"],
            "requested_architect_mode": ArchitectMode.FULL_ACCESS.value,
            "effective_architect_mode": ArchitectMode.FULL_ACCESS.value,
            "missing_effective_scopes": [],
        }
    effective_mode = ArchitectMode.FULL_ACCESS
    effective_scopes = set(ArchitectModeService.scopes_for_mode(effective_mode))
    missing_effective_scopes = sorted(scope for scope in required_scopes if "*" not in effective_scopes and scope not in effective_scopes)
    return {
        "ok": len(missing_effective_scopes) == 0,
        "required_scopes": sorted(required_scopes),
        "effective_scopes": sorted(effective_scopes),
        "requested_architect_mode": ArchitectMode.FULL_ACCESS.value,
        "effective_architect_mode": effective_mode.value,
        "missing_effective_scopes": missing_effective_scopes,
    }


def _unwrap_data(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    if isinstance(payload, dict):
        return payload
    return {}


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _resolve_runtime_env() -> dict[str, str]:
    base_url = _env("PLATFORM_ARCHITECT_BASE_URL", _env("TEST_BASE_URL", DEFAULT_TEST_BASE_URL))
    api_key = _env("PLATFORM_ARCHITECT_API_KEY", _env("TEST_API_KEY", DEFAULT_TEST_API_KEY))
    organization_id = _env("PLATFORM_ARCHITECT_ORGANIZATION_ID", _env("TEST_ORGANIZATION_ID", DEFAULT_TEST_ORGANIZATION_ID))
    project_id = _env("PLATFORM_ARCHITECT_PROJECT_ID", _env("TEST_PROJECT_ID", DEFAULT_TEST_PROJECT_ID))
    user_email = _env("PLATFORM_ARCHITECT_USER_EMAIL", _env("TEST_USER_EMAIL", DEFAULT_TEST_USER_EMAIL))
    timeout_s = _env("ARCH_E2E_TIMEOUT_SECONDS", "120")
    resource_prefix = _env("ARCH_E2E_RESOURCE_PREFIX", "arch-e2e")
    report_path = _env(
        "ARCH_E2E_REPORT_PATH",
        "backend/artifacts/e2e/platform_architect/latest_report.json",
    )
    chat_model = _env("TEST_CHAT_MODEL_SLUG", DEFAULT_TEST_CHAT_MODEL_SLUG)

    return {
        "base_url": str(base_url).rstrip("/"),
        "api_key": str(api_key),
        "organization_id": str(organization_id),
        "project_id": str(project_id),
        "user_email": str(user_email),
        "timeout_s": str(timeout_s),
        "resource_prefix": str(resource_prefix),
        "report_path": str(report_path),
        "chat_model": str(chat_model) if chat_model else "",
    }


def _headers(api_key: str, organization_id: str, project_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "X-Organization-ID": organization_id,
        "X-Project-ID": project_id,
        "Content-Type": "application/json",
    }


def _resolve_architect_agent_id(client: ControlPlaneClient) -> str:
    listing = client.agents.list(limit=200)
    data = _unwrap_data(listing)
    agents = data.get("agents") if isinstance(data, dict) else None
    if not isinstance(agents, list):
        raise RuntimeError("Unable to list agents for architect resolution.")

    for item in agents:
        if isinstance(item, dict) and item.get("system_key") == "platform_architect":
            agent_id = item.get("id")
            if agent_id:
                return str(agent_id)

    raise RuntimeError("platform_architect agent not found in tenant.")

def _start_run(
    base_url: str,
    headers: dict[str, str],
    architect_id: str,
    prompt: str,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    context_payload = dict(runtime_context or {})
    context_payload.setdefault("architect_mode", ArchitectMode.FULL_ACCESS.value)
    response = requests.post(
        f"{base_url}/agents/{architect_id}/run",
        headers=headers,
        json={"input": prompt, "messages": [], "context": context_payload},
        timeout=30,
    )
    response.raise_for_status()
    payload = _unwrap_data(response.json())
    run_id = payload.get("run_id") or payload.get("id")
    if not run_id:
        raise RuntimeError(f"Missing run_id in run start response: {payload}")
    return str(run_id)


def _get_run(base_url: str, headers: dict[str, str], run_id: str) -> dict[str, Any]:
    response = requests.get(
        f"{base_url}/agents/runs/{run_id}",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return _unwrap_data(response.json())


def _get_run_tree(base_url: str, headers: dict[str, str], run_id: str) -> dict[str, Any]:
    response = requests.get(
        f"{base_url}/agents/runs/{run_id}/tree",
        headers=headers,
        timeout=30,
    )
    if response.status_code >= 400:
        return {}
    return _unwrap_data(response.json())


def _poll_run(base_url: str, headers: dict[str, str], run_id: str, timeout_s: int) -> dict[str, Any]:
    start = time.time()
    last = {}
    while time.time() - start < timeout_s:
        payload = _get_run(base_url, headers, run_id)
        last = payload
        status = str(payload.get("status") or "").lower()
        if status in TERMINAL_RUN_STATUSES:
            return payload
        time.sleep(1.0)
    raise TimeoutError(f"Run {run_id} did not finish within {timeout_s}s. Last payload={last}")


def _scenario_prompt(
    scenario: ScenarioDefinition,
    unique_prefix: str,
    organization_id: str,
    tenant_slug: str | None,
    chat_model: str,
) -> str:
    slug_hint = tenant_slug or ""
    model_hint = chat_model or ""
    return (
        "You are testing one capability only.\\n"
        f"Target action: {scenario.target_action}\\n"
        f"Tool slug: {scenario.tool_slug}\\n"
        "Rules:\\n"
        "1) Execute exactly one canonical action call matching target action.\\n"
        "2) Use organization_id exactly as provided.\\n"
        "3) Use names/slugs starting with provided test prefix.\\n"
        "4) For create actions produce a minimal valid payload. For agents.create include exactly one start node, "
        "at least one end node, and a control edge from start to end; never use empty agent graph.\\n"
        "5) Return final response as one JSON object only with keys: status, action, resources, errors.\\n"
        f"Inputs: organization_id={organization_id}, tenant_slug={slug_hint}, prefix={unique_prefix}, model_slug={model_hint}."
    )


def _action_specific_api_check(
    scenario: ScenarioDefinition,
    sdk_client: ControlPlaneClient,
    tenant_slug: str | None,
    unique_prefix: str,
    assistant_json: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    action = scenario.target_action

    try:
        if action == "agents.create":
            agents = _unwrap_data(sdk_client.agents.list(limit=200)).get("agents", [])
            found = [a for a in agents if isinstance(a, dict) and str(a.get("slug", "")).startswith(unique_prefix)]
            if not found:
                return False, "No created agent with expected prefix"
            graph = found[0].get("graph_definition") or {}
            nodes = graph.get("nodes") if isinstance(graph, dict) else []
            has_start = any(isinstance(n, dict) and n.get("type") == "start" for n in nodes)
            has_end = any(isinstance(n, dict) and n.get("type") == "end" for n in nodes)
            return bool(has_start and has_end), "Created agent graph lacks start/end" if not (has_start and has_end) else "ok"

        if action == "rag.create_visual_pipeline" and tenant_slug:
            pipelines = _unwrap_data(sdk_client.rag.list_visual_pipelines(tenant_slug=tenant_slug)).get("data", [])
            pipeline_by_id = {
                str(p.get("id")): p
                for p in pipelines
                if isinstance(p, dict) and p.get("id") is not None
            }
            resources = assistant_json.get("resources") if isinstance(assistant_json, dict) else None
            candidate_ids: set[str] = set()
            if isinstance(resources, list):
                for item in resources:
                    if isinstance(item, dict) and item.get("id"):
                        candidate_ids.add(str(item.get("id")))
            elif isinstance(resources, dict) and resources.get("id"):
                candidate_ids.add(str(resources.get("id")))

            if candidate_ids:
                found = [resource_id for resource_id in candidate_ids if resource_id in pipeline_by_id]
                return (len(found) > 0, "Created pipeline id not found in visual pipeline listing")

            found_by_name = [
                p for p in pipelines
                if isinstance(p, dict) and str(p.get("name", "")).startswith(unique_prefix)
            ]
            return (len(found_by_name) > 0, "No created pipeline found by id or name prefix")

        if action == "tools.create_or_update":
            tools = _unwrap_data(sdk_client.tools.list(limit=200)).get("tools", [])
            found = [t for t in tools if isinstance(t, dict) and str(t.get("slug", "")).startswith(unique_prefix)]
            return (len(found) > 0, "No created tool with expected prefix")

        if action == "models.create_or_update":
            models = _unwrap_data(sdk_client.models.list(limit=200, is_active=None)).get("models", [])
            found = [m for m in models if isinstance(m, dict) and str(m.get("slug", "")).startswith(unique_prefix)]
            return (len(found) > 0, "No created model with expected prefix")

        if action == "artifacts.create" and tenant_slug:
            artifacts = _unwrap_data(sdk_client.artifacts.list(tenant_slug=tenant_slug)).get("data", [])
            found = [
                a for a in artifacts
                if isinstance(a, dict)
                and (
                    str(a.get("slug", "")).startswith(unique_prefix)
                    or str(a.get("display_name", "")).startswith(unique_prefix)
                )
            ]
            return (len(found) > 0, "No created artifact with expected prefix")

        if action == "knowledge_stores.create_or_update" and tenant_slug:
            stores = _unwrap_data(sdk_client.knowledge_stores.list(tenant_slug=tenant_slug)).get("data", [])
            found = [s for s in stores if isinstance(s, dict) and str(s.get("name", "")).startswith(unique_prefix)]
            return (len(found) > 0, "No created knowledge store with expected prefix")

    except Exception as exc:
        return False, f"API verification error: {exc}"

    return True, "No action-specific side-effect check required"


@pytest.fixture(scope="session")
def e2e_runtime() -> dict[str, Any]:
    env = _resolve_runtime_env()
    organization_slug = resolve_organization_slug(env["organization_id"])
    sdk = ControlPlaneClient(base_url=env["base_url"], token=env["api_key"], organization_id=env["organization_id"])
    architect_agent_id = _resolve_architect_agent_id(sdk)
    required_scopes, scope_to_actions = _build_scope_requirements()
    initiator_user_id = _decode_jwt_sub(env["api_key"])
    preflight = _run_async(
        _compute_scope_preflight(
            organization_id=env["organization_id"],
            architect_agent_id=architect_agent_id,
            initiator_user_id=initiator_user_id,
            required_scopes=required_scopes,
        )
    )
    if not preflight.get("ok"):
        missing_effective = preflight.get("missing_effective_scopes") or []
        impacted_actions: list[str] = []
        for scope in missing_effective:
            impacted_actions.extend(scope_to_actions.get(str(scope), []))
        impacted_actions = sorted(set(impacted_actions))
        lines = [
            "Architect E2E scope preflight failed before scenario execution.",
            f"organization_id={env['organization_id']}",
            f"architect_agent_id={architect_agent_id}",
            f"initiator_user_id={initiator_user_id or 'unresolved'}",
            f"reason={preflight.get('reason') or 'missing effective scopes'}",
            f"missing_effective_scopes={sorted(missing_effective)}",
            f"requested_architect_mode={preflight.get('requested_architect_mode')}",
            f"effective_architect_mode={preflight.get('effective_architect_mode')}",
            f"effective_scopes={sorted(preflight.get('effective_scopes') or [])}",
            f"impacted_actions={impacted_actions}",
        ]
        pytest.exit("\n".join(lines), returncode=1)

    report = E2EReport(organization_id=env["organization_id"], path=env["report_path"])

    return {
        **env,
        "organization_slug": organization_slug,
        "sdk": sdk,
        "architect_agent_id": architect_agent_id,
        "report": report,
        "headers": _headers(env["api_key"], env["organization_id"], env["project_id"]),
        "requested_scopes": sorted(required_scopes),
    }


@pytest.fixture(scope="session", autouse=True)
def _flush_report(e2e_runtime):
    yield
    e2e_runtime["report"].flush()


@pytest.mark.real_db
@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.id for s in SCENARIOS])
def test_platform_architect_capability_matrix_live(e2e_runtime, scenario: ScenarioDefinition):
    if scenario.requires_model and not e2e_runtime.get("chat_model"):
        pytest.skip(f"Scenario {scenario.id} requires TEST_CHAT_MODEL_SLUG")

    unique_prefix = f"{e2e_runtime['resource_prefix']}-{scenario.id}-{uuid.uuid4().hex[:6]}"
    prompt = _scenario_prompt(
        scenario=scenario,
        unique_prefix=unique_prefix,
        organization_id=e2e_runtime["organization_id"],
        tenant_slug=e2e_runtime.get("organization_slug"),
        chat_model=e2e_runtime.get("chat_model", ""),
    )

    run_id = _start_run(
        e2e_runtime["base_url"],
        e2e_runtime["headers"],
        e2e_runtime["architect_agent_id"],
        prompt,
        {"requested_scopes": e2e_runtime.get("requested_scopes", [])},
    )
    run_status = _poll_run(
        e2e_runtime["base_url"],
        e2e_runtime["headers"],
        run_id,
        int(e2e_runtime["timeout_s"]),
    )
    run_tree = _get_run_tree(e2e_runtime["base_url"], e2e_runtime["headers"], run_id)

    assistant_text = extract_assistant_text(run_status)
    assistant_json = extract_first_json_object(assistant_text)

    action_seen = contains_action_evidence(run_status.get("result"), scenario.target_action) or contains_action_evidence(
        run_tree,
        scenario.target_action,
    )

    db_check = check_agent_run_exists(run_id, e2e_runtime["organization_id"], e2e_runtime["project_id"])
    api_side_effect_ok, api_side_effect_detail = _action_specific_api_check(
        scenario=scenario,
        sdk_client=e2e_runtime["sdk"],
        tenant_slug=e2e_runtime.get("organization_slug"),
        unique_prefix=unique_prefix,
        assistant_json=assistant_json,
    )

    errors_blob = {
        "run_status": run_status.get("error"),
        "run_result": run_status.get("result"),
        "assistant": assistant_json or assistant_text,
        "run_tree": run_tree,
    }

    passed = True
    failure_reasons: list[str] = []
    assistant_status = ""
    assistant_errors_blob: Any = None
    if isinstance(assistant_json, dict):
        assistant_status = str(assistant_json.get("status") or "").strip().lower()
        assistant_errors_blob = assistant_json.get("errors")

    if not action_seen:
        passed = False
        failure_reasons.append("Target action not observed in structured run evidence")

    if not db_check.ok:
        passed = False
        failure_reasons.append(f"DB run linkage failed: {db_check.detail}")

    if scenario.expected_outcome == "expected_block":
        expected_code = str(scenario.expected_error_code or "")
        if assistant_status not in {"error", "blocked", "failed"}:
            passed = False
            failure_reasons.append(f"Assistant status is not a blocked/error status: {assistant_status or 'missing'}")
        saw_code = contains_token(assistant_errors_blob, expected_code) or contains_token(errors_blob, expected_code)
        if not saw_code:
            passed = False
            failure_reasons.append(f"Expected block code not found: {expected_code}")
    else:
        if assistant_status and assistant_status not in {"success", "ok", "completed"}:
            passed = False
            failure_reasons.append(f"Assistant reported non-success status: {assistant_status}")
        if isinstance(assistant_json, dict) and assistant_errors_blob:
            passed = False
            failure_reasons.append(f"Assistant reported errors: {assistant_errors_blob}")
        terminal_status = str(run_status.get("status") or "").lower()
        if terminal_status != "completed":
            passed = False
            failure_reasons.append(f"Run status is not completed: {terminal_status}")
        if not api_side_effect_ok:
            passed = False
            failure_reasons.append(api_side_effect_detail)

    e2e_runtime["report"].add_result(
        {
            "scenario_id": scenario.id,
            "action": scenario.target_action,
            "status": "passed" if passed else "failed",
            "agent_run_id": run_id,
            "assertions": {
                "action_seen": action_seen,
                "db_run_linked": db_check.ok,
                "api_side_effect_ok": api_side_effect_ok,
                "expected_outcome": scenario.expected_outcome,
                "expected_error_code": scenario.expected_error_code,
            },
            "errors": failure_reasons,
            "resource_refs": {
                "prefix": unique_prefix,
                "assistant_report": assistant_json,
            },
            "scenario": asdict(scenario),
        }
    )

    assert passed, " | ".join(failure_reasons)


@pytest.mark.real_db
def test_platform_architect_artifact_worker_smoke_live(e2e_runtime):
    if os.getenv("ARCH_E2E_ARTIFACT_WORKER_SMOKE") != "1":
        pytest.skip("Set ARCH_E2E_ARTIFACT_WORKER_SMOKE=1 to run the manual artifact-worker smoke test.")

    scope_subset = sorted(set(e2e_runtime.get("requested_scopes", [])) | {"agents.execute"})
    unique_prefix = f"{e2e_runtime['resource_prefix']}-artifact-worker-{uuid.uuid4().hex[:6]}"
    prompt = (
        "Create one minimal tool artifact through the architect worker flow. "
        "Use an architect worker binding, spawn the artifact worker, wait for it, persist the artifact through platform-assets, "
        "and do not publish it. "
        f"Use display name {unique_prefix}. "
        "Return one JSON object only with keys: status, artifact_display_name, child_agent_slugs, errors."
    )

    run_id = _start_run(
        e2e_runtime["base_url"],
        e2e_runtime["headers"],
        e2e_runtime["architect_agent_id"],
        prompt,
        {"requested_scopes": scope_subset},
    )
    run_status = _poll_run(
        e2e_runtime["base_url"],
        e2e_runtime["headers"],
        run_id,
        int(e2e_runtime["timeout_s"]),
    )
    run_tree = _get_run_tree(e2e_runtime["base_url"], e2e_runtime["headers"], run_id)
    assistant_text = extract_assistant_text(run_status)
    assistant_json = extract_first_json_object(assistant_text) or {}
    tree_blob = json.dumps(run_tree)

    assert str(run_status.get("status") or "").lower() == "completed"
    assert "artifact-coding-agent" in tree_blob
    assert contains_action_evidence(run_status.get("result"), "artifacts.create") or contains_action_evidence(run_tree, "artifacts.create")
    assert str(assistant_json.get("status") or "").lower() in {"ok", "completed", "success"}
    assert str(assistant_json.get("artifact_display_name") or "") == unique_prefix
