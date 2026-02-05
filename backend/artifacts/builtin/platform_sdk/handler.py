"""
Platform SDK Tool Artifact

Executes platform actions via the dynamic SDK:
- fetch_catalog: summarize available RAG/Agent nodes
- validate_plan: validate plan steps without mutation
- execute_plan: create artifacts, deploy pipelines, deploy agents
- respond: echo message without mutation
"""
from __future__ import annotations

import json
import os
import asyncio
from typing import Any, Dict, List, Optional, Tuple

import requests

from sdk import Client, ArtifactBuilder
from app.core.security import create_access_token
from app.core.internal_token import create_service_token
from app.agent.graph.schema import AgentGraph, NodeType
from app.agent.graph.compiler import AgentCompiler
from app.rag.pipeline.compiler import PipelineCompiler


def execute(state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    inputs = _resolve_inputs(state, context)
    inputs = _coerce_json_text(inputs)

    action = inputs.get("action") or (inputs.get("payload") or {}).get("action") or "fetch_catalog"
    payload = inputs.get("payload") if isinstance(inputs.get("payload"), dict) else {}
    steps = inputs.get("steps") if isinstance(inputs.get("steps"), list) else []
    steps = _normalize_steps(steps)
    dry_run = bool(inputs.get("dry_run") or payload.get("dry_run", False))

    base_url, api_key, tenant_id, extra_headers = _resolve_auth(inputs, payload, state=state, context=context)
    print(
        "[platform_sdk] "
        f"action={action} "
        f"base_url={base_url} "
        f"token={'yes' if api_key else 'no'} "
        f"tenant_id={tenant_id} "
        f"headers={list(extra_headers.keys())}"
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
    elif action == "respond":
        result = {"message": payload.get("message") or inputs.get("message") or ""}
    else:
        result = {"message": f"Unknown action '{action}'. Supported: fetch_catalog, validate_plan, execute_plan, respond."}
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

        normalized.append(step)

    return normalized


def _resolve_auth(inputs: Dict[str, Any], payload: Dict[str, Any], state: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None) -> Tuple[str, Optional[str], Optional[str], Dict[str, str]]:
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
        or os.getenv("TENANT_ID")
    )
    if tenant_id is not None:
        tenant_id = str(tenant_id)

    user_id = (
        payload.get("user_id")
        or inputs.get("user_id")
        or state_ctx.get("user_id")
        or tool_ctx.get("user_id")
    )

    token = None

    # 1) Service token (minted from PLATFORM_SERVICE_SECRET)
    if tenant_id and os.getenv("PLATFORM_SERVICE_SECRET"):
        try:
            token = create_service_token(tenant_id=tenant_id)
        except Exception:
            token = None

    # 2) Explicit token from inputs/context
    if token is None:
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

    # 3) Environment fallbacks for client-side tokens
    if token is None:
        token = os.getenv("PLATFORM_API_KEY") or os.getenv("API_KEY")

    # Final fallback: mint a short-lived user token if none is provided but we have a tenant_id
    if token is None and tenant_id:
        try:
            token = create_access_token(subject=user_id or "platform-sdk", tenant_id=tenant_id)
        except Exception:
            token = None

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

    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append({"step": idx, "error": "invalid_step", "detail": "Step must be an object"})
            continue

        step_type = step.get("action") or step.get("type")
        if not step_type:
            errors.append({"step": idx, "error": "missing_action"})
            continue

        if step_type == "create_custom_node":
            if not step.get("name") or not (step.get("python_code") or step.get("code")):
                errors.append({"step": idx, "error": "missing_fields", "fields": ["name", "python_code"]})
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
        resp = requests.post(
            f"{client.base_url}/api/agents",
            json=payload,
            headers=client.headers,
        )
        resp.raise_for_status()
        return resp.json(), None
    except Exception as exc:
        return None, {"error": "deploy_agent_failed", "detail": str(exc)}
