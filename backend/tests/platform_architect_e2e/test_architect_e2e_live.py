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
from app.db.postgres.engine import sessionmaker as async_sessionmaker
from app.db.postgres.models.agents import Agent
from app.db.postgres.models.security import (
    WorkloadPolicyStatus,
    WorkloadPrincipalBinding,
    WorkloadResourceType,
    WorkloadScopePolicy,
)
from app.services.delegation_service import DelegationService
from tests.platform_architect_e2e.db_checks import check_agent_run_exists, resolve_tenant_slug
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
DEFAULT_TEST_API_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJleHAiOjE3Nzk4MjYzMjIsInN1YiI6Ijg4ZDY3MzE1LWU3N2ItNDg0ZS04ZWJiLTc5YmRkNTBkYTFjMCIs"
    "InRlbmFudF9pZCI6ImY3NTM4ZWI1LTdmZjctNDg1Ny1hOGUxLTdiMjFjYzU4ZjEwYSIsIm9yZ191bml0X2lkIjo"
    "iY2E0MjE0NDctY2Q0YS00NjM3LTg1ZDYtOWU2MzNmMGZkZjFiIiwib3JnX3JvbGUiOiJvd25lciJ9."
    "9Kgqm_BbAr3xtN0k2JK3SkNxzebWrzmcyC4i_euk9OQ"
)
DEFAULT_TEST_TENANT_ID = "f7538eb5-7ff7-4857-a8e1-7b21cc58f10a"
DEFAULT_TEST_TENANT_EMAIL = "danielbenassaya2626@gmail.com"
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
    tenant_id: str,
    architect_agent_id: str,
    initiator_user_id: str | None,
    required_scopes: set[str],
) -> dict[str, Any]:
    async with async_sessionmaker() as db:
        agent = await db.get(Agent, UUID(str(architect_agent_id)))
        if agent is None:
            return {"ok": False, "reason": "platform-architect agent not found by id"}

        binding_res = await db.execute(
            select(WorkloadPrincipalBinding).where(
                WorkloadPrincipalBinding.tenant_id == UUID(str(tenant_id)),
                WorkloadPrincipalBinding.resource_type == WorkloadResourceType.AGENT,
                WorkloadPrincipalBinding.resource_id == str(agent.id),
            )
        )
        binding = binding_res.scalars().first()
        if binding is None:
            return {
                "ok": False,
                "reason": "No workload principal binding found for platform-architect agent",
            }

        policy_res = await db.execute(
            select(WorkloadScopePolicy)
            .where(WorkloadScopePolicy.principal_id == binding.principal_id)
            .order_by(WorkloadScopePolicy.version.desc())
            .limit(1)
        )
        policy = policy_res.scalars().first()
        if policy is None:
            return {
                "ok": False,
                "reason": "No workload scope policy found for platform-architect principal",
            }

        approved_scopes = set(policy.approved_scopes or [])
        if policy.status != WorkloadPolicyStatus.APPROVED:
            return {
                "ok": False,
                "reason": f"Workload policy is not approved (status={policy.status.value})",
                "approved_scopes": sorted(approved_scopes),
                "required_scopes": sorted(required_scopes),
            }

        delegation = DelegationService(db)
        user_scopes: set[str] = set()
        user_scope_mode = "unresolved"
        parsed_initiator: UUID | None = None
        if initiator_user_id:
            try:
                parsed_initiator = UUID(str(initiator_user_id))
            except ValueError:
                parsed_initiator = None
        if parsed_initiator is not None:
            user_scopes = await delegation._resolve_user_scopes(UUID(str(tenant_id)), parsed_initiator)
            user_scope_mode = "wildcard" if "*" in user_scopes else "explicit"
        else:
            user_scopes = {"*"}

        effective_scopes = DelegationService._intersect_scopes(user_scopes, approved_scopes, required_scopes)
        missing_effective_scopes = sorted(required_scopes - set(effective_scopes))
        missing_policy_scopes = sorted(required_scopes - approved_scopes)

        missing_user_scopes: list[str] = []
        if "*" not in user_scopes:
            missing_user_scopes = sorted(required_scopes - user_scopes)

        return {
            "ok": len(missing_effective_scopes) == 0,
            "required_scopes": sorted(required_scopes),
            "approved_scopes": sorted(approved_scopes),
            "user_scopes": sorted(user_scopes),
            "user_scope_mode": user_scope_mode,
            "missing_effective_scopes": missing_effective_scopes,
            "missing_policy_scopes": missing_policy_scopes,
            "missing_user_scopes": missing_user_scopes,
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
    base_url = _env("TEST_BASE_URL", DEFAULT_TEST_BASE_URL)
    api_key = _env("TEST_API_KEY", DEFAULT_TEST_API_KEY)
    tenant_id = _env("TEST_TENANT_ID", DEFAULT_TEST_TENANT_ID)
    tenant_email = _env("TEST_TENANT_EMAIL", DEFAULT_TEST_TENANT_EMAIL)
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
        "tenant_id": str(tenant_id),
        "tenant_email": str(tenant_email),
        "timeout_s": str(timeout_s),
        "resource_prefix": str(resource_prefix),
        "report_path": str(report_path),
        "chat_model": str(chat_model) if chat_model else "",
    }


def _headers(api_key: str, tenant_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "X-Tenant-ID": tenant_id,
        "Content-Type": "application/json",
    }


def _resolve_architect_agent_id(client: ControlPlaneClient) -> str:
    listing = client.agents.list(limit=200)
    data = _unwrap_data(listing)
    agents = data.get("agents") if isinstance(data, dict) else None
    if not isinstance(agents, list):
        raise RuntimeError("Unable to list agents for architect resolution.")

    for item in agents:
        if isinstance(item, dict) and item.get("slug") == "platform-architect":
            agent_id = item.get("id")
            if agent_id:
                return str(agent_id)

    raise RuntimeError("platform-architect agent not found in tenant.")


def _start_run(
    base_url: str,
    headers: dict[str, str],
    architect_id: str,
    prompt: str,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    context_payload = dict(runtime_context or {})
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
    tenant_id: str,
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
        "2) Use tenant_id exactly as provided.\\n"
        "3) Use names/slugs starting with provided test prefix.\\n"
        "4) For create actions produce a minimal valid payload. For agents.create include exactly one start node, "
        "at least one end node, and a control edge from start to end; never use empty agent graph.\\n"
        "5) Return final response as one JSON object only with keys: status, action, resources, errors.\\n"
        f"Inputs: tenant_id={tenant_id}, tenant_slug={slug_hint}, prefix={unique_prefix}, model_slug={model_hint}."
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

        if action == "artifacts.create_or_update_draft" and tenant_slug:
            artifacts = _unwrap_data(sdk_client.artifacts.list(tenant_slug=tenant_slug)).get("data", [])
            found = [a for a in artifacts if isinstance(a, dict) and str(a.get("name", "")).startswith(unique_prefix)]
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
    tenant_slug = resolve_tenant_slug(env["tenant_id"])
    sdk = ControlPlaneClient(base_url=env["base_url"], token=env["api_key"], tenant_id=env["tenant_id"])
    architect_agent_id = _resolve_architect_agent_id(sdk)
    required_scopes, scope_to_actions = _build_scope_requirements()
    initiator_user_id = _decode_jwt_sub(env["api_key"])
    preflight = _run_async(
        _compute_scope_preflight(
            tenant_id=env["tenant_id"],
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
            f"tenant_id={env['tenant_id']}",
            f"architect_agent_id={architect_agent_id}",
            f"initiator_user_id={initiator_user_id or 'unresolved'}",
            f"reason={preflight.get('reason') or 'missing effective scopes'}",
            f"missing_effective_scopes={sorted(missing_effective)}",
            f"missing_policy_scopes={sorted(preflight.get('missing_policy_scopes') or [])}",
            f"missing_user_scopes={sorted(preflight.get('missing_user_scopes') or [])}",
            f"user_scope_mode={preflight.get('user_scope_mode')}",
            f"impacted_actions={impacted_actions}",
        ]
        pytest.exit("\n".join(lines), returncode=1)

    report = E2EReport(tenant_id=env["tenant_id"], path=env["report_path"])

    return {
        **env,
        "tenant_slug": tenant_slug,
        "sdk": sdk,
        "architect_agent_id": architect_agent_id,
        "report": report,
        "headers": _headers(env["api_key"], env["tenant_id"]),
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
        tenant_id=e2e_runtime["tenant_id"],
        tenant_slug=e2e_runtime.get("tenant_slug"),
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

    db_check = check_agent_run_exists(run_id, e2e_runtime["tenant_id"])
    api_side_effect_ok, api_side_effect_detail = _action_specific_api_check(
        scenario=scenario,
        sdk_client=e2e_runtime["sdk"],
        tenant_slug=e2e_runtime.get("tenant_slug"),
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
