from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sdk import Client
from talmudpedia_control_sdk import ControlPlaneSDKError

from .shared import control_client


def list_capabilities(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    rag_catalog, rag_errors = get_rag_operator_catalog(
        client,
        payload,
        control_client_factory=control_client_factory,
    )
    agent_catalog, agent_errors = list_agent_operators(
        client,
        control_client_factory=control_client_factory,
    )
    errors = rag_errors + agent_errors

    result = {
        "summary": {
            "rag": _summarize_rag_catalog(rag_catalog),
            "agent": _summarize_agent_catalog(agent_catalog),
        }
    }

    if payload.get("include_raw"):
        result["rag_catalog"] = rag_catalog
        result["agent_catalog"] = agent_catalog

    return result, errors


def get_rag_operator_catalog(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    try:
        organization_id = payload.get("organization_id")
        sdk_client = control_client_factory(client)
        response = sdk_client.catalog.get_rag_operator_catalog(organization_id=organization_id)
        data = response.get("data")
        if isinstance(data, dict):
            return data, []
        return {}, []
    except ControlPlaneSDKError as exc:
        return {}, [{
            "error": "catalog_get_rag_operator_catalog_failed",
            "detail": str(exc),
            "code": exc.code,
            "http_status": exc.http_status,
        }]
    except Exception as exc:
        return {}, [{"error": "catalog_get_rag_operator_catalog_failed", "detail": str(exc)}]


def list_rag_operators(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    try:
        organization_id = payload.get("organization_id")
        sdk_client = control_client_factory(client)
        response = sdk_client.catalog.list_rag_operators(organization_id=organization_id)
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


def get_rag_operator(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    operator_id = payload.get("operator_id")
    if not operator_id:
        return None, [{"error": "missing_fields", "fields": ["operator_id"]}]

    try:
        organization_id = payload.get("organization_id")
        sdk_client = control_client_factory(client)
        response = sdk_client.catalog.get_rag_operator(str(operator_id), organization_id=organization_id)
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


def list_agent_operators(
    client: Client,
    *,
    control_client_factory=control_client,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.catalog.list_agent_nodes()
        data = response.get("data")
        if isinstance(data, dict) and isinstance(data.get("nodes"), list):
            return data["nodes"], []
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

    categories: Dict[str, int] = {}
    total = 0
    examples: Dict[str, List[str]] = {}
    for spec in list(rag_catalog.get("operators") or []):
        if not isinstance(spec, dict):
            continue
        category = str(spec.get("category") or "custom")
        total += 1
        categories[category] = categories.get(category, 0) + 1
        examples.setdefault(category, [])
        if len(examples[category]) < 3:
            examples[category].append(str(spec.get("type") or ""))

    return {
        "total": total,
        "categories": categories,
        "examples": examples,
        "fields": ["type", "title", "category", "input_type", "output_type"],
    }


def _summarize_agent_catalog(agent_catalog: Any) -> Dict[str, Any]:
    if not isinstance(agent_catalog, list):
        return {"total": 0, "categories": {}}

    categories: Dict[str, int] = {}
    examples: Dict[str, List[str]] = {}
    total = len(agent_catalog)

    for spec in agent_catalog:
        if not isinstance(spec, dict):
            continue
        category = spec.get("category", "general")
        categories[category] = categories.get(category, 0) + 1
        if category not in examples:
            examples[category] = []
        if len(examples[category]) < 3:
            examples[category].append(spec.get("type"))

    return {
        "total": total,
        "categories": categories,
        "examples": examples,
        "fields": ["type", "display_name", "category", "reads", "writes"],
    }
