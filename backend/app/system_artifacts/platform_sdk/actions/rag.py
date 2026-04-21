from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sdk import Client
from talmudpedia_control_sdk import ControlPlaneSDKError

from .shared import control_client, request_options


_CONTROL_PLANE_META_KEYS = {
    "action",
    "builtin_key",
    "organization_id",
    "idempotency_key",
    "request_metadata",
    "validate_only",
    "dry_run",
}


def _strip_control_plane_meta(payload: Dict[str, Any]) -> Dict[str, Any]:
    request_payload = dict(payload or {})
    for key in _CONTROL_PLANE_META_KEYS:
        request_payload.pop(key, None)
    return request_payload


def _normalize_visual_pipeline_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    request_payload = _strip_control_plane_meta(payload)
    graph_definition = request_payload.pop("graph_definition", None)
    if isinstance(graph_definition, dict):
        if "nodes" not in request_payload and isinstance(graph_definition.get("nodes"), list):
            request_payload["nodes"] = graph_definition.get("nodes")
        if "edges" not in request_payload and isinstance(graph_definition.get("edges"), list):
            request_payload["edges"] = graph_definition.get("edges")
    return request_payload


def _normalize_visual_pipeline_patch(patch: Dict[str, Any]) -> Dict[str, Any]:
    patch_payload = _strip_control_plane_meta(patch)
    graph_definition = patch_payload.pop("graph_definition", None)
    if isinstance(graph_definition, dict):
        if isinstance(graph_definition.get("nodes"), list):
            patch_payload["nodes"] = graph_definition.get("nodes")
        if isinstance(graph_definition.get("edges"), list):
            patch_payload["edges"] = graph_definition.get("edges")
    return patch_payload


def _sdk_error_payload(error_name: str, exc: ControlPlaneSDKError, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "error": error_name,
        "detail": str(exc),
        "code": exc.code,
        "http_status": exc.http_status,
    }
    if exc.details is not None:
        payload["details"] = exc.details
    for key, value in extra.items():
        if value is not None:
            payload[key] = value
    validation_errors: list[dict[str, Any]] = []
    if isinstance(exc.details, dict):
        detail_payload = exc.details.get("detail") if isinstance(exc.details.get("detail"), dict) else exc.details
        if isinstance(detail_payload, dict) and isinstance(detail_payload.get("errors"), list):
            validation_errors.extend(item for item in detail_payload["errors"] if isinstance(item, dict))
        if validation_errors:
            payload["validation_errors"] = validation_errors
    return payload


def _retrieval_pipeline_shell_graph() -> Dict[str, Any]:
    return {
        "nodes": [
            {
                "id": "query_input_1",
                "category": "input",
                "operator": "query_input",
                "position": {"x": 0, "y": 0},
                "config": {},
            },
            {
                "id": "model_embedder_1",
                "category": "embedding",
                "operator": "model_embedder",
                "position": {"x": 220, "y": 0},
                "config": {},
            },
            {
                "id": "vector_search_1",
                "category": "retrieval",
                "operator": "vector_search",
                "position": {"x": 440, "y": 0},
                "config": {},
            },
            {
                "id": "retrieval_result_1",
                "category": "output",
                "operator": "retrieval_result",
                "position": {"x": 660, "y": 0},
                "config": {},
            },
        ],
        "edges": [
            {"id": "edge_query_to_embed", "source": "query_input_1", "target": "model_embedder_1"},
            {"id": "edge_embed_to_search", "source": "model_embedder_1", "target": "vector_search_1"},
            {"id": "edge_search_to_result", "source": "vector_search_1", "target": "retrieval_result_1"},
        ],
    }


def operators_catalog(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.get_operator_catalog(organization_id=payload.get("organization_id"))
        data = response.get("data")
        operators: list[dict[str, Any]] = []
        if isinstance(data, dict):
            for category, items in data.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    entry = dict(item)
                    entry.setdefault("category", category)
                    required_fields = []
                    if isinstance(entry.get("required_config"), list):
                        required_fields = [
                            str(field.get("name"))
                            for field in entry["required_config"]
                            if isinstance(field, dict) and field.get("name")
                        ]
                    entry["required_fields"] = required_fields
                    operators.append(entry)
        return {"operators": operators, "categories": data}, []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("get_operator_catalog_failed", exc)]
    except Exception as exc:
        return None, [{"error": "get_operator_catalog_failed", "detail": str(exc)}]


def operators_schema(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    operator_ids = [str(item).strip() for item in list(payload.get("operator_ids") or []) if str(item).strip()]
    if not operator_ids:
        return None, [{"error": "missing_fields", "fields": ["operator_ids"]}]
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.get_operator_schemas(
            operator_ids,
            organization_id=payload.get("organization_id"),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("get_operator_schemas_failed", exc, operator_ids=operator_ids)]
    except Exception as exc:
        return None, [{"error": "get_operator_schemas_failed", "detail": str(exc), "operator_ids": operator_ids}]


def list_pipelines(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.list_visual_pipelines(
            organization_id=payload.get("organization_id"),
            skip=int(payload.get("skip", 0) or 0),
            limit=int(payload.get("limit", 20) or 20),
            view=str(payload.get("view") or "summary"),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "list_pipelines_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "list_pipelines_failed", "detail": str(exc)}]


def create_or_update_pipeline(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    pipeline_id = payload.get("pipeline_id") or payload.get("id")
    organization_id = payload.get("organization_id")

    if dry_run:
        skipped: Dict[str, Any] = {"status": "skipped", "dry_run": True}
        if pipeline_id:
            skipped["pipeline_id"] = str(pipeline_id)
        return skipped, []

    try:
        sdk_client = control_client_factory(client)
        if pipeline_id:
            patch_payload = dict(payload.get("patch")) if isinstance(payload.get("patch"), dict) else dict(payload)
            patch_payload.pop("pipeline_id", None)
            patch_payload.pop("id", None)
            patch_payload = _normalize_visual_pipeline_patch(patch_payload)
            response = sdk_client.rag.update_visual_pipeline(
                str(pipeline_id),
                patch_payload,
                organization_id=organization_id,
                options=request_options_builder(payload=payload, dry_run=False),
            )
        else:
            request_payload = _normalize_visual_pipeline_payload(payload)
            response = sdk_client.rag.create_visual_pipeline(
                request_payload,
                organization_id=organization_id,
                options=request_options_builder(payload=payload, dry_run=False),
            )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "create_or_update_pipeline_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "create_or_update_pipeline_failed", "detail": str(exc)}]


def create_visual_pipeline(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    if dry_run:
        return {"status": "skipped", "dry_run": True, "name": payload.get("name")}, []

    try:
        request_payload = _normalize_visual_pipeline_payload(payload)
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.create_visual_pipeline(
            request_payload,
            organization_id=payload.get("organization_id"),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("create_visual_pipeline_failed", exc)]
    except Exception as exc:
        return None, [{"error": "create_visual_pipeline_failed", "detail": str(exc)}]


def create_pipeline_shell(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    name = str(payload.get("name") or "").strip()
    if not name:
        return None, [{"error": "missing_fields", "fields": ["name"]}]

    pipeline_type = str(payload.get("pipeline_type") or "retrieval").strip().lower()
    if pipeline_type != "retrieval":
        return None, [{
            "error": "unsupported_pipeline_type",
            "fields": ["pipeline_type"],
            "message": "rag.create_pipeline_shell currently supports retrieval pipelines only.",
        }]

    request_payload: Dict[str, Any] = {
        "name": name,
        "pipeline_type": pipeline_type,
        **_retrieval_pipeline_shell_graph(),
    }
    description = payload.get("description")
    if isinstance(description, str) and description.strip():
        request_payload["description"] = description.strip()
    organization_id = payload.get("organization_id")

    if dry_run:
        return {"status": "skipped", "dry_run": True, "name": name, "pipeline_type": pipeline_type}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.create_visual_pipeline(
            request_payload,
            organization_id=organization_id,
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("create_pipeline_shell_failed", exc)]
    except Exception as exc:
        return None, [{"error": "create_pipeline_shell_failed", "detail": str(exc)}]


def update_visual_pipeline(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    pipeline_id = payload.get("pipeline_id") or payload.get("id")
    if not pipeline_id:
        return None, [{"error": "missing_fields", "fields": ["pipeline_id"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "pipeline_id": str(pipeline_id)}, []

    patch_payload = dict(payload.get("patch")) if isinstance(payload.get("patch"), dict) else dict(payload)
    patch_payload.pop("pipeline_id", None)
    patch_payload.pop("id", None)
    patch_payload = _normalize_visual_pipeline_patch(patch_payload)
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.update_visual_pipeline(
            str(pipeline_id),
            patch_payload,
            organization_id=payload.get("organization_id"),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "update_visual_pipeline_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "update_visual_pipeline_failed", "detail": str(exc)}]


def graph_get(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    pipeline_id = payload.get("pipeline_id") or payload.get("id")
    if not pipeline_id:
        return None, [{"error": "missing_fields", "fields": ["pipeline_id"]}]
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.get_pipeline_graph(str(pipeline_id), organization_id=payload.get("organization_id"))
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("get_pipeline_graph_failed", exc, pipeline_id=pipeline_id)]
    except Exception as exc:
        return None, [{"error": "get_pipeline_graph_failed", "detail": str(exc), "pipeline_id": pipeline_id}]


def graph_validate_patch(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    pipeline_id = payload.get("pipeline_id") or payload.get("id")
    operations = payload.get("operations") if isinstance(payload.get("operations"), list) else []
    if not pipeline_id:
        return None, [{"error": "missing_fields", "fields": ["pipeline_id"]}]
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.validate_graph_patch(
            str(pipeline_id),
            operations,
            organization_id=payload.get("organization_id"),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("validate_pipeline_graph_patch_failed", exc, pipeline_id=pipeline_id)]
    except Exception as exc:
        return None, [{"error": "validate_pipeline_graph_patch_failed", "detail": str(exc), "pipeline_id": pipeline_id}]


def graph_apply_patch(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    pipeline_id = payload.get("pipeline_id") or payload.get("id")
    operations = payload.get("operations") if isinstance(payload.get("operations"), list) else []
    if not pipeline_id:
        return None, [{"error": "missing_fields", "fields": ["pipeline_id"]}]
    if dry_run:
        return {"status": "skipped", "dry_run": True, "pipeline_id": str(pipeline_id), "operations": operations}, []
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.apply_graph_patch(
            str(pipeline_id),
            operations,
            organization_id=payload.get("organization_id"),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("apply_pipeline_graph_patch_failed", exc, pipeline_id=pipeline_id)]
    except Exception as exc:
        return None, [{"error": "apply_pipeline_graph_patch_failed", "detail": str(exc), "pipeline_id": pipeline_id}]


def graph_attach_knowledge_store_to_node(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    pipeline_id = payload.get("pipeline_id") or payload.get("id")
    node_id = payload.get("node_id")
    knowledge_store_id = payload.get("knowledge_store_id")
    missing = [
        name
        for name, value in (
            ("pipeline_id", pipeline_id),
            ("node_id", node_id),
            ("knowledge_store_id", knowledge_store_id),
        )
        if not value
    ]
    if missing:
        return None, [{"error": "missing_fields", "fields": missing}]
    if dry_run:
        return {
            "status": "skipped",
            "dry_run": True,
            "pipeline_id": str(pipeline_id),
            "node_id": str(node_id),
            "knowledge_store_id": str(knowledge_store_id),
        }, []
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.attach_knowledge_store_to_node(
            str(pipeline_id),
            node_id=str(node_id),
            knowledge_store_id=str(knowledge_store_id),
            organization_id=payload.get("organization_id"),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("attach_knowledge_store_to_node_failed", exc, pipeline_id=pipeline_id)]
    except Exception as exc:
        return None, [{"error": "attach_knowledge_store_to_node_failed", "detail": str(exc), "pipeline_id": pipeline_id}]


def graph_set_pipeline_node_config(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    pipeline_id = payload.get("pipeline_id") or payload.get("id")
    node_id = payload.get("node_id")
    path = payload.get("path")
    missing = [name for name, value in (("pipeline_id", pipeline_id), ("node_id", node_id), ("path", path)) if not value]
    if missing:
        return None, [{"error": "missing_fields", "fields": missing}]
    if "value" not in payload:
        return None, [{"error": "missing_fields", "fields": ["value"]}]
    if dry_run:
        return {
            "status": "skipped",
            "dry_run": True,
            "pipeline_id": str(pipeline_id),
            "node_id": str(node_id),
            "path": str(path),
        }, []
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.set_pipeline_node_config(
            str(pipeline_id),
            node_id=str(node_id),
            path=str(path),
            value=payload.get("value"),
            organization_id=payload.get("organization_id"),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [_sdk_error_payload("set_pipeline_node_config_failed", exc, pipeline_id=pipeline_id)]
    except Exception as exc:
        return None, [{"error": "set_pipeline_node_config_failed", "detail": str(exc), "pipeline_id": pipeline_id}]


def compile_pipeline(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    pipeline_id = payload.get("pipeline_id") or payload.get("id")
    if not pipeline_id:
        return None, [{"error": "missing_fields", "fields": ["pipeline_id"]}]

    if dry_run:
        return {"status": "skipped", "dry_run": True, "pipeline_id": str(pipeline_id)}, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.compile_visual_pipeline(
            str(pipeline_id),
            organization_id=payload.get("organization_id"),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "compile_pipeline_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "compile_pipeline_failed", "detail": str(exc)}]


def compile_visual_pipeline(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    return compile_pipeline(
        client,
        payload,
        dry_run,
        control_client_factory=control_client_factory,
        request_options_builder=request_options_builder,
    )


def create_job(
    client: Client,
    payload: Dict[str, Any],
    dry_run: bool,
    *,
    control_client_factory=control_client,
    request_options_builder=request_options,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    executable_pipeline_id = payload.get("executable_pipeline_id")
    organization_id = payload.get("organization_id")
    input_params = payload.get("input_params") if isinstance(payload.get("input_params"), dict) else {}

    missing: List[str] = []
    if not executable_pipeline_id:
        missing.append("executable_pipeline_id")
    if not organization_id:
        missing.append("organization_id")
    if missing:
        return None, [{"error": "missing_fields", "fields": missing}]

    if dry_run:
        return {
            "status": "skipped",
            "dry_run": True,
            "executable_pipeline_id": str(executable_pipeline_id),
            "request": {"input_params": input_params},
        }, []

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.create_job(
            str(executable_pipeline_id),
            input_params,
            organization_id=str(organization_id),
            options=request_options_builder(payload=payload, dry_run=False),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "create_job_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "create_job_failed", "detail": str(exc)}]


def get_job(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    job_id = payload.get("job_id") or payload.get("id")
    if not job_id:
        return None, [{"error": "missing_fields", "fields": ["job_id"]}]

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.get_job(str(job_id), organization_id=payload.get("organization_id"))
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "get_job_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "get_job_failed", "detail": str(exc)}]


def get_executable_pipeline(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    exec_id = payload.get("exec_id") or payload.get("executable_pipeline_id") or payload.get("id")
    if not exec_id:
        return None, [{"error": "missing_fields", "fields": ["exec_id"]}]
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.get_executable_pipeline(str(exec_id), organization_id=payload.get("organization_id"))
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "get_executable_pipeline_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "get_executable_pipeline_failed", "detail": str(exc)}]


def get_executable_input_schema(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    exec_id = payload.get("exec_id") or payload.get("executable_pipeline_id") or payload.get("id")
    if not exec_id:
        return None, [{"error": "missing_fields", "fields": ["exec_id"]}]
    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.get_executable_input_schema(str(exec_id), organization_id=payload.get("organization_id"))
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "get_executable_input_schema_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "get_executable_input_schema_failed", "detail": str(exc)}]


def get_step_data(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    job_id = payload.get("job_id")
    step_id = payload.get("step_id")
    data_type = payload.get("data_type") or payload.get("type")

    missing: List[str] = []
    if not job_id:
        missing.append("job_id")
    if not step_id:
        missing.append("step_id")
    if not data_type:
        missing.append("data_type")
    if missing:
        return None, [{"error": "missing_fields", "fields": missing}]

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.rag.get_step_data(
            str(job_id),
            str(step_id),
            str(data_type),
            page=int(payload.get("page", 1) or 1),
            limit=int(payload.get("limit", 20) or 20),
            organization_id=payload.get("organization_id"),
        )
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "get_step_data_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "get_step_data_failed", "detail": str(exc)}]
