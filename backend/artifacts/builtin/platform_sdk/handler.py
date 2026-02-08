"""
Platform SDK Tool Artifact

Executes platform actions via the dynamic SDK:
- fetch_catalog: summarize available RAG/Agent nodes
- validate_plan: validate plan steps without mutation
- execute_plan: create artifacts, deploy pipelines, deploy agents
- create_artifact_draft: create draft artifacts via /admin/artifacts
- promote_artifact: promote draft artifacts into file-based artifacts
- create_tool: create draft tools via /tools
- run_agent: execute an agent (non-streaming)
- run_tests: execute multi-case tests and evaluate assertions
- respond: echo message without mutation
"""
from __future__ import annotations

import json
import os
import asyncio
from typing import Any, Dict, List, Optional, Tuple

import requests

from sdk import Client, ArtifactBuilder
from app.agent.graph.schema import AgentGraph, NodeType
from app.agent.graph.compiler import AgentCompiler
from app.rag.pipeline.compiler import PipelineCompiler


PRIVILEGED_ACTION_SCOPES = {
    "fetch_catalog": ["pipelines.catalog.read"],
    "create_artifact_draft": ["artifacts.write"],
    "promote_artifact": ["artifacts.write"],
    "create_tool": ["tools.write"],
    "run_agent": ["agents.execute"],
    "run_tests": ["agents.run_tests"],
}

PLAN_ACTION_SCOPES = {
    "deploy_agent": ["agents.write"],
    "deploy_rag_pipeline": ["pipelines.write"],
    "create_artifact_draft": ["artifacts.write"],
    "promote_artifact": ["artifacts.write"],
    "create_tool": ["tools.write"],
    "run_agent": ["agents.execute"],
    "run_tests": ["agents.run_tests"],
}


def execute(state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    inputs = _resolve_inputs(state, context)
    inputs = _coerce_json_text(inputs)

    payload = inputs.get("payload") if isinstance(inputs.get("payload"), dict) else {}
    steps = inputs.get("steps") if isinstance(inputs.get("steps"), list) else []
    if not steps and isinstance(inputs.get("actions"), list):
        steps = inputs.get("actions") or []
    if not steps and isinstance(payload.get("steps"), list):
        steps = payload.get("steps") or []
    if not steps and isinstance(payload.get("actions"), list):
        steps = payload.get("actions") or []
    steps = _normalize_steps(steps)
    tests = inputs.get("tests") if isinstance(inputs.get("tests"), list) else []
    if not tests and isinstance(payload.get("tests"), list):
        tests = payload.get("tests") or []
    dry_run = bool(inputs.get("dry_run") or payload.get("dry_run", False))
    explicit_action = _extract_explicit_action(inputs, payload)
    action = _resolve_action(explicit_action, inputs, payload, steps, tests)

    if action == "noop":
        output = {
            "result": {
                "status": "ignored",
                "reason": "missing_or_non_action_invocation",
                "message": "No explicit Platform SDK action was provided.",
            },
            "errors": [{"error": "missing_action"}],
            "action": "noop",
            "dry_run": dry_run,
        }
        return {
            "context": output,
            "tool_outputs": [output],
        }

    required_scopes = _resolve_required_scopes(action=action, steps=steps)
    base_url, api_key, tenant_id, extra_headers = _resolve_auth(
        inputs,
        payload,
        state=state,
        context=context,
        action=action,
        required_scopes=required_scopes,
    )
    client = Client(base_url=base_url, api_key=api_key, tenant_id=tenant_id, extra_headers=extra_headers)

    errors: List[Dict[str, Any]] = []

    if action == "fetch_catalog":
        result = _fetch_catalog(client, payload)
    elif action == "validate_plan":
        result, errors = _validate_plan(client, steps)
    elif action == "execute_plan":
        validation, validation_errors = _validate_plan(client, steps)
        if validation_errors:
            result = {
                "status": "validation_failed",
                "validation": validation,
            }
            errors = validation_errors
        else:
            result, errors = _execute_plan(client, steps, dry_run)
    elif action == "create_artifact_draft":
        result, errors = _create_artifact_draft(client, payload, dry_run)
    elif action == "promote_artifact":
        result, errors = _promote_artifact(client, payload, dry_run)
    elif action == "create_tool":
        result, errors = _create_tool(client, payload, dry_run)
    elif action == "run_agent":
        result, errors = _run_agent(client, payload, dry_run)
    elif action == "run_tests":
        result, errors = _run_tests(client, tests, dry_run)
    elif action == "respond":
        result = {"message": payload.get("message") or inputs.get("message") or ""}
    else:
        result = {"message": f"Unknown action '{action}'. Supported: fetch_catalog, validate_plan, execute_plan, create_artifact_draft, promote_artifact, create_tool, run_agent, run_tests, respond."}
        errors.append({"error": "unknown_action", "action": action})

    output = {
        "result": result,
        "errors": errors,
        "action": action,
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
    if steps:
        return "execute_plan"
    if tests:
        return "run_tests"
    if payload.get("message") or inputs.get("message"):
        return "respond"
    if _is_non_action_invocation(inputs, payload):
        return "noop"
    return "noop"


def _is_non_action_invocation(inputs: Dict[str, Any], payload: Dict[str, Any]) -> bool:
    if not isinstance(inputs, dict):
        return True

    metadata_probe_keys = {"artifact_id", "version", "config_keys"}
    if metadata_probe_keys.issubset(set(inputs.keys())):
        return True

    auth_envelope_keys = {
        "user_id",
        "grant_id",
        "tenant_id",
        "principal_id",
        "requested_scopes",
        "initiator_user_id",
        "run_id",
        "value",
    }
    if set(inputs.keys()).issubset(auth_envelope_keys):
        value = inputs.get("value")
        if value in ("", None):
            return True

    if not payload and not inputs:
        return True

    return False


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


def _normalize_steps(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Accepts looser planner output such as:
      {"create_custom_node": {...}}
      {"deploy_agent": {"payload/graph_json": {...}}}
    and rewrites into the expected shape:
      {"action": "create_custom_node", ...}
    """
    normalized: List[Dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue

        if "action" in step:
            normalized.append(step)
            continue

        if "create_custom_node" in step and isinstance(step["create_custom_node"], dict):
            data = step["create_custom_node"]
            norm = {"action": "create_custom_node"}
            norm.update(data)
            normalized.append(norm)
            continue

        if "deploy_agent" in step and isinstance(step["deploy_agent"], dict):
            data = step["deploy_agent"]
            payload = data.get("payload/graph_json") or data.get("graph_json") or data.get("payload")
            norm = {"action": "deploy_agent"}
            if payload:
                norm["payload"] = payload
            normalized.append(norm)
            continue

        if "deploy_rag_pipeline" in step and isinstance(step["deploy_rag_pipeline"], dict):
            data = step["deploy_rag_pipeline"]
            payload = data.get("payload/graph_json") or data.get("graph_json") or data.get("payload")
            norm = {"action": "deploy_rag_pipeline"}
            if payload:
                norm["payload"] = payload
            normalized.append(norm)
            continue

        if "create_artifact_draft" in step and isinstance(step["create_artifact_draft"], dict):
            data = step["create_artifact_draft"]
            norm = {"action": "create_artifact_draft"}
            norm.update(data)
            normalized.append(norm)
            continue

        if "promote_artifact" in step and isinstance(step["promote_artifact"], dict):
            data = step["promote_artifact"]
            norm = {"action": "promote_artifact"}
            norm.update(data)
            normalized.append(norm)
            continue

        if "create_tool" in step and isinstance(step["create_tool"], dict):
            data = step["create_tool"]
            norm = {"action": "create_tool"}
            norm.update(data)
            normalized.append(norm)
            continue

        if "run_agent" in step and isinstance(step["run_agent"], dict):
            data = step["run_agent"]
            norm = {"action": "run_agent"}
            norm.update(data)
            normalized.append(norm)
            continue

        if "run_tests" in step and isinstance(step["run_tests"], dict):
            data = step["run_tests"]
            norm = {"action": "run_tests"}
            norm.update(data)
            normalized.append(norm)
            continue

        normalized.append(step)

    return normalized


def _resolve_required_scopes(action: str, steps: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    scopes = set(PRIVILEGED_ACTION_SCOPES.get(action, []))
    if action == "execute_plan":
        for step in steps or []:
            if not isinstance(step, dict):
                continue
            step_action = step.get("action")
            if step_action:
                scopes.update(PLAN_ACTION_SCOPES.get(step_action, []))
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

    scoped_action = action or "fetch_catalog"
    scope_list = required_scopes or _resolve_required_scopes(scoped_action)
    if scope_list:
        delegated_token = None
        auth_ctx = tool_ctx.get("auth") if isinstance(tool_ctx.get("auth"), dict) else {}
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
                    f"Action '{scoped_action}' requires delegated workload token; workload token mint failed: {exc}"
                ) from exc

        if not delegated_token:
            raise ValueError(
                f"Action '{scoped_action}' requires delegated workload token; missing grant context or caller auth context"
            )
        token = delegated_token

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


def _extract_step_payload(step: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(step, dict):
        return {}
    payload = step.get("payload")
    if isinstance(payload, dict):
        return payload
    if isinstance(step.get("graph_json"), dict):
        return step.get("graph_json") or {}
    return {k: v for k, v in step.items() if k not in {"action", "type", "depends_on", "id"}}


def _collect_step_ids(steps: List[Dict[str, Any]]) -> set:
    step_ids = set()
    for step in steps:
        if isinstance(step, dict) and step.get("id"):
            step_ids.add(str(step.get("id")))
    return step_ids


def _validate_plan(client: Client, steps: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    errors: List[Dict[str, Any]] = []

    try:
        client.connect()
    except Exception:
        pass

    rag_catalog = client.nodes.catalog or {}
    agent_catalog = client.agent_nodes.catalog or []

    rag_operator_ids = set()
    if isinstance(rag_catalog, dict):
        for specs in rag_catalog.values():
            if isinstance(specs, list):
                for spec in specs:
                    if isinstance(spec, dict) and spec.get("operator_id"):
                        rag_operator_ids.add(spec["operator_id"])

    agent_types = set()
    if isinstance(agent_catalog, list):
        for spec in agent_catalog:
            if isinstance(spec, dict) and spec.get("type"):
                agent_types.add(spec["type"])

    builtin_agent_types = {node.value for node in NodeType}
    allowed_agent_types = builtin_agent_types.union(agent_types)

    step_ids = _collect_step_ids(steps)

    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append({"step": idx, "error": "invalid_step", "detail": "Step must be an object"})
            continue

        step_type = step.get("action") or step.get("type")
        if not step_type:
            errors.append({"step": idx, "error": "missing_action"})
            continue

        depends_on = step.get("depends_on")
        if depends_on is not None:
            if not isinstance(depends_on, list):
                errors.append({"step": idx, "error": "invalid_depends_on", "detail": "depends_on must be a list"})
            else:
                for dep in depends_on:
                    if str(dep) not in step_ids:
                        errors.append({"step": idx, "error": "unknown_dependency", "dependency": dep})

        if step_type == "create_custom_node":
            if not step.get("name") or not (step.get("python_code") or step.get("code")):
                errors.append({"step": idx, "error": "missing_fields", "fields": ["name", "python_code"]})
            continue

        if step_type == "create_artifact_draft":
            payload = _extract_step_payload(step)
            if not payload.get("name") or not (payload.get("python_code") or payload.get("code")):
                errors.append({"step": idx, "error": "missing_fields", "fields": ["name", "python_code"]})
            continue

        if step_type == "promote_artifact":
            payload = _extract_step_payload(step)
            artifact_id = payload.get("artifact_id") or payload.get("id") or step.get("artifact_id")
            if not artifact_id:
                errors.append({"step": idx, "error": "missing_fields", "fields": ["artifact_id"]})
            continue

        if step_type == "create_tool":
            payload = _extract_step_payload(step)
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
                errors.append({"step": idx, "error": "missing_fields", "fields": missing})
            continue

        if step_type == "run_agent":
            payload = _extract_step_payload(step)
            agent_id = payload.get("agent_id") or payload.get("id")
            agent_slug = payload.get("agent_slug") or payload.get("slug")
            if not agent_id and not agent_slug:
                errors.append({"step": idx, "error": "missing_fields", "fields": ["agent_id or agent_slug"]})
            continue

        if step_type == "run_tests":
            payload = _extract_step_payload(step)
            tests = payload.get("tests") if isinstance(payload.get("tests"), list) else None
            if not tests:
                errors.append({"step": idx, "error": "missing_fields", "fields": ["tests"]})
            continue

        if step_type == "deploy_rag_pipeline":
            payload = step.get("graph_json") or step.get("payload")
            if not isinstance(payload, dict):
                errors.append({"step": idx, "error": "missing_payload", "action": step_type})
                continue

            # Validate operators against catalog
            for node in payload.get("nodes", []) or []:
                operator_id = None
                if isinstance(node, dict):
                    data = node.get("data", {}) if isinstance(node.get("data"), dict) else {}
                    operator_id = data.get("operator") or node.get("operator")
                if operator_id and rag_operator_ids and operator_id not in rag_operator_ids:
                    errors.append({"step": idx, "error": "unknown_operator", "operator": operator_id})

            compiler = PipelineCompiler()
            result = compiler.compile(payload)
            if not result.success:
                for err in result.errors:
                    errors.append({
                        "step": idx,
                        "error": "pipeline_validation_error",
                        "code": err.code,
                        "message": err.message,
                        "node_id": err.node_id,
                    })
            continue

        if step_type == "deploy_agent":
            payload = step.get("graph_json") or step.get("payload")
            if not isinstance(payload, dict):
                errors.append({"step": idx, "error": "missing_payload", "action": step_type})
                continue

            graph_payload = payload.get("graph_definition") if isinstance(payload.get("graph_definition"), dict) else payload
            try:
                graph = AgentGraph.model_validate(graph_payload)
            except Exception as exc:
                errors.append({"step": idx, "error": "agent_graph_invalid", "detail": str(exc)})
                continue

            for node in graph.nodes:
                if node.type and allowed_agent_types and node.type not in allowed_agent_types:
                    errors.append({"step": idx, "error": "unknown_agent_node", "node_type": node.type})

            compiler = AgentCompiler()
            validation_result = _run_async(compiler.validate(graph))
            if validation_result is None:
                errors.append({"step": idx, "error": "validation_unavailable", "detail": "Async validation unavailable"})
            else:
                for err in validation_result:
                    errors.append({
                        "step": idx,
                        "error": "agent_validation_error",
                        "node_id": err.node_id,
                        "edge_id": err.edge_id,
                        "message": err.message,
                        "severity": err.severity,
                    })
            continue

        errors.append({"step": idx, "error": "unsupported_action", "action": step_type})

    return {"valid": len(errors) == 0, "issues": errors}, errors


def _fetch_catalog(client: Client, payload: Dict[str, Any]) -> Dict[str, Any]:
    client.connect()
    rag_catalog = client.nodes.catalog or {}
    agent_catalog = client.agent_nodes.catalog or []

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

    return result


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


def _execute_plan(client: Client, steps: List[Dict[str, Any]], dry_run: bool) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append({"step": idx, "error": "invalid_step", "detail": "Step must be an object"})
            continue

        step_type = step.get("action") or step.get("type")
        if not step_type:
            errors.append({"step": idx, "error": "missing_action"})
            continue

        if step_type == "create_custom_node":
            result, err = _step_create_custom_node(client, step, dry_run)
        elif step_type == "create_artifact_draft":
            result, err = _step_create_artifact_draft(client, step, dry_run)
        elif step_type == "promote_artifact":
            result, err = _step_promote_artifact(client, step, dry_run)
        elif step_type == "create_tool":
            result, err = _step_create_tool(client, step, dry_run)
        elif step_type == "run_agent":
            result, err = _step_run_agent(client, step, dry_run)
        elif step_type == "run_tests":
            result, err = _step_run_tests(client, step, dry_run)
        elif step_type == "deploy_rag_pipeline":
            result, err = _step_deploy_rag_pipeline(client, step, dry_run)
        elif step_type == "deploy_agent":
            result, err = _step_deploy_agent(client, step, dry_run)
        else:
            result, err = None, {"step": idx, "error": "unsupported_action", "action": step_type}

        if err:
            errors.append(err)
        results.append({"action": step_type, "result": result})

    return {"steps": results}, errors


def _step_create_custom_node(client: Client, step: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    name = step.get("name")
    python_code = step.get("python_code") or step.get("code")

    if not name or not python_code:
        return None, {"error": "missing_fields", "fields": ["name", "python_code"]}

    if dry_run:
        return {"status": "skipped", "dry_run": True, "name": name}, None

    try:
        created = ArtifactBuilder.create(
            client,
            name=name,
            python_code=python_code,
            category=step.get("category", "custom"),
            input_type=step.get("input_type", "raw_documents"),
            output_type=step.get("output_type", "normalized_documents"),
            display_name=step.get("display_name"),
            description=step.get("description"),
            config_schema=step.get("config_schema"),
        )
        return created, None
    except Exception as exc:
        return None, {"error": "create_custom_node_failed", "detail": str(exc), "name": name}


def _step_deploy_rag_pipeline(client: Client, step: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    payload = step.get("graph_json") or step.get("payload")
    if not isinstance(payload, dict):
        return None, {"error": "missing_payload", "action": "deploy_rag_pipeline"}

    if dry_run:
        return {"status": "skipped", "dry_run": True}, None

    try:
        resp = requests.post(
            f"{client.base_url}/admin/pipelines/visual-pipelines",
            json=payload,
            headers=client.headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json(), None
    except Exception as exc:
        return None, {"error": "deploy_rag_pipeline_failed", "detail": str(exc)}


def _step_deploy_agent(client: Client, step: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    payload = step.get("graph_json") or step.get("payload")
    if not isinstance(payload, dict):
        return None, {"error": "missing_payload", "action": "deploy_agent"}

    if dry_run:
        return {"status": "skipped", "dry_run": True}, None

    try:
        primary_url = f"{client.base_url}/agents"
        fallback_url = f"{client.base_url}/api/agents"
        resp = requests.post(primary_url, json=payload, headers=client.headers, timeout=30)
        if resp.status_code == 404:
            resp = requests.post(fallback_url, json=payload, headers=client.headers, timeout=30)
        resp.raise_for_status()
        return resp.json(), None
    except Exception as exc:
        return None, {"error": "deploy_agent_failed", "detail": str(exc)}


def _step_create_artifact_draft(client: Client, step: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    payload = _extract_step_payload(step)
    result, errors = _create_artifact_draft(client, payload, dry_run)
    if errors:
        return result, {"error": "create_artifact_draft_failed", "details": errors}
    return result, None


def _step_promote_artifact(client: Client, step: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    payload = _extract_step_payload(step)
    result, errors = _promote_artifact(client, payload, dry_run)
    if errors:
        return result, {"error": "promote_artifact_failed", "details": errors}
    return result, None


def _step_create_tool(client: Client, step: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    payload = _extract_step_payload(step)
    result, errors = _create_tool(client, payload, dry_run)
    if errors:
        return result, {"error": "create_tool_failed", "details": errors}
    return result, None


def _step_run_agent(client: Client, step: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    payload = _extract_step_payload(step)
    result, errors = _run_agent(client, payload, dry_run)
    if errors:
        return result, {"error": "run_agent_failed", "details": errors}
    return result, None


def _step_run_tests(client: Client, step: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    payload = _extract_step_payload(step)
    tests = payload.get("tests") if isinstance(payload.get("tests"), list) else []
    result, errors = _run_tests(client, tests, dry_run)
    if errors:
        return result, {"error": "run_tests_failed", "details": errors}
    return result, None


def _create_artifact_draft(client: Client, payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
    name = payload.get("name")
    python_code = payload.get("python_code") or payload.get("code")
    if not name or not python_code:
        return None, [{"error": "missing_fields", "fields": ["name", "python_code"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "name": name}, []

    request_payload = dict(payload)
    request_payload["python_code"] = python_code
    request_payload.pop("code", None)
    request_payload.setdefault("display_name", payload.get("display_name") or name)

    try:
        resp = requests.post(
            f"{client.base_url}/admin/artifacts",
            json=request_payload,
            headers=client.headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json(), []
    except Exception as exc:
        return None, [{"error": "create_artifact_draft_failed", "detail": str(exc), "name": name}]


def _promote_artifact(client: Client, payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
    artifact_id = payload.get("artifact_id") or payload.get("id")
    if not artifact_id:
        return None, [{"error": "missing_fields", "fields": ["artifact_id"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "artifact_id": artifact_id}, []

    promote_payload = {}
    if payload.get("namespace"):
        promote_payload["namespace"] = payload.get("namespace")
    if payload.get("version"):
        promote_payload["version"] = payload.get("version")

    try:
        resp = requests.post(
            f"{client.base_url}/admin/artifacts/{artifact_id}/promote",
            json=promote_payload,
            headers=client.headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json(), []
    except Exception as exc:
        return None, [{"error": "promote_artifact_failed", "detail": str(exc), "artifact_id": artifact_id}]


def _create_tool(client: Client, payload: Dict[str, Any], dry_run: bool) -> Tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
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
        return {"status": "skipped", "dry_run": True, "slug": payload.get("slug")}, []

    try:
        resp = requests.post(
            f"{client.base_url}/tools",
            json=payload,
            headers=client.headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json(), []
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
        response = _call_agent_execute(client, agent_id, request_payload)
        return response, []
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
    for page in range(0, 10):
        try:
            resp = requests.get(
                f"{client.base_url}/agents",
                params={"skip": page * page_size, "limit": page_size},
                headers=client.headers,
                timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json() or {}
            agents = payload.get("agents") if isinstance(payload, dict) else []
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
    resp = requests.post(
        f"{client.base_url}/agents/{agent_id}/execute",
        json=payload,
        headers=client.headers,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


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
