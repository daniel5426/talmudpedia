"""
Platform SDK Tool Artifact

Executes platform actions via the dynamic SDK:
- fetch_catalog: summarize available RAG/Agent nodes
- execute_plan: create artifacts, deploy pipelines, deploy agents
- respond: echo message without mutation
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

from sdk import Client, ArtifactBuilder


def execute(state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    inputs = _resolve_inputs(state, context)
    inputs = _coerce_json_text(inputs)

    action = inputs.get("action") or (inputs.get("payload") or {}).get("action") or "fetch_catalog"
    payload = inputs.get("payload") if isinstance(inputs.get("payload"), dict) else {}
    steps = inputs.get("steps") if isinstance(inputs.get("steps"), list) else []
    dry_run = bool(inputs.get("dry_run") or payload.get("dry_run", False))

    base_url, api_key, tenant_id, extra_headers = _resolve_auth(inputs, payload)
    client = Client(base_url=base_url, api_key=api_key, tenant_id=tenant_id, extra_headers=extra_headers)

    errors: List[Dict[str, Any]] = []

    if action == "fetch_catalog":
        result = _fetch_catalog(client, payload)
    elif action == "execute_plan":
        result, errors = _execute_plan(client, steps, dry_run)
    elif action == "respond":
        result = {"message": payload.get("message") or inputs.get("message") or ""}
    else:
        result = {"message": f"Unknown action '{action}'. Supported: fetch_catalog, execute_plan, respond."}
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

    if set(inputs.keys()) == {"text"} and isinstance(inputs.get("text"), str):
        text = inputs.get("text", "").strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return inputs
    return inputs


def _resolve_auth(inputs: Dict[str, Any], payload: Dict[str, Any]) -> Tuple[str, Optional[str], Optional[str], Dict[str, str]]:
    base_url = (
        payload.get("base_url")
        or inputs.get("base_url")
        or os.getenv("PLATFORM_BASE_URL")
        or os.getenv("API_BASE_URL")
        or "http://localhost:8000"
    )

    token = (
        payload.get("token")
        or inputs.get("token")
        or payload.get("api_key")
        or inputs.get("api_key")
        or payload.get("bearer_token")
        or inputs.get("bearer_token")
        or os.getenv("PLATFORM_API_KEY")
        or os.getenv("API_KEY")
    )

    tenant_id = payload.get("tenant_id") or inputs.get("tenant_id") or os.getenv("TENANT_ID")

    extra_headers = {}
    if isinstance(payload.get("headers"), dict):
        extra_headers.update(payload.get("headers"))
    if isinstance(inputs.get("headers"), dict):
        extra_headers.update(inputs.get("headers"))

    return base_url, token, tenant_id, extra_headers


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
