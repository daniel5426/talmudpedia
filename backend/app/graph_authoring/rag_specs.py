from __future__ import annotations

from typing import Any

from app.graph_authoring.schema import enrich_schema_with_ui, required_config_fields
from app.graph_authoring.types import GraphHints, NodeAuthoringSpec, NodeCatalogItem
from app.rag.pipeline.registry import ConfigFieldSpec, ConfigFieldType, DataType, OperatorSpec


def rag_node_spec(spec: OperatorSpec) -> NodeAuthoringSpec:
    fields = [_rag_field_payload(field) for field in list(spec.required_config or []) + list(spec.optional_config or [])]
    rows = None
    if spec.operator_id == "web_crawler":
        rows = [
            ["max_depth", "max_pages", "page_timeout_ms"],
            ["respect_robots_txt", "scan_full_page"],
            ["content_preference", "wait_until"],
        ]
    config_schema = enrich_schema_with_ui({"type": "object", "additionalProperties": True}, fields, rows=rows)
    input_schema = spec.resolved_input_schema() or {}
    output_schema = spec.resolved_output_schema() or {}
    category = _ui_category(str(getattr(spec.category, "value", spec.category)))
    return NodeAuthoringSpec(
        type=spec.operator_id,
        title=spec.display_name,
        description=spec.description,
        category=category,
        input_type=str(getattr(spec.input_type, "value", spec.input_type)),
        output_type=str(getattr(spec.output_type, "value", spec.output_type)),
        config_schema=config_schema,
        output_schema=output_schema or None,
        field_contracts=None,
        graph_hints=GraphHints(editor="generic"),
    )


def rag_catalog_item(spec: OperatorSpec) -> NodeCatalogItem:
    authoring = rag_node_spec(spec)
    return NodeCatalogItem(
        type=authoring.type,
        title=authoring.title,
        description=authoring.description,
        category=authoring.category,
        input_type=authoring.input_type,
        output_type=authoring.output_type,
        required_config_fields=required_config_fields(authoring.config_schema),
        icon=_category_icon(authoring.category),
        color=_category_color(authoring.category),
        editor="generic",
    )


def _rag_field_payload(field: ConfigFieldSpec) -> dict[str, Any]:
    if hasattr(field, "model_dump"):
        raw = field.model_dump()
    elif hasattr(field, "__dict__"):
        raw = dict(getattr(field, "__dict__") or {})
    else:
        raw = {}
    payload: dict[str, Any] = {
        "name": str(getattr(field, "name", "") or ""),
        "label": str(getattr(field, "name", "") or "").replace("_", " ").title(),
        "fieldType": _widget_for_rag_field(getattr(field, "field_type", ConfigFieldType.STRING)),
        "required": bool(getattr(field, "required", False)),
        "default": getattr(field, "default", None),
        "description": getattr(field, "description", None),
    }
    if raw.get("options"):
        payload["options"] = [{"value": option, "label": option} for option in list(raw.get("options") or [])]
    if raw.get("runtime"):
        payload["runtime"] = True
    if raw.get("placeholder"):
        payload["placeholder"] = raw["placeholder"]
    return payload


def _widget_for_rag_field(field_type: ConfigFieldType) -> str:
    mapping = {
        ConfigFieldType.STRING: "string",
        ConfigFieldType.INTEGER: "number",
        ConfigFieldType.FLOAT: "number",
        ConfigFieldType.BOOLEAN: "boolean",
        ConfigFieldType.SECRET: "string",
        ConfigFieldType.SELECT: "select",
        ConfigFieldType.MODEL_SELECT: "model",
        ConfigFieldType.KNOWLEDGE_STORE_SELECT: "knowledge_store_select",
        ConfigFieldType.RETRIEVAL_PIPELINE_SELECT: "retrieval_pipeline_select",
        ConfigFieldType.JSON: "json",
        ConfigFieldType.CODE: "text",
        ConfigFieldType.FILE_PATH: "string",
    }
    return mapping.get(field_type, "string")


def _category_icon(category: str) -> str:
    mapping = {
        "source": "FolderInput",
        "normalization": "ShieldCheck",
        "enrichment": "Sparkle",
        "chunking": "Scissors",
        "utility": "ArrowRightLeft",
        "embedding": "Sparkles",
        "storage": "Database",
        "retrieval": "Search",
        "reranking": "SortAsc",
        "input": "FolderInput",
        "output": "Database",
        "custom": "Code",
    }
    return mapping.get(category, "Hash")


def _category_color(category: str) -> str:
    mapping = {
        "source": "var(--pipeline-source)",
        "normalization": "var(--pipeline-transform)",
        "enrichment": "var(--pipeline-transform)",
        "chunking": "var(--pipeline-transform)",
        "utility": "var(--pipeline-transform)",
        "embedding": "var(--pipeline-embedding)",
        "storage": "var(--pipeline-storage)",
        "retrieval": "var(--pipeline-source)",
        "reranking": "var(--pipeline-transform)",
        "input": "var(--pipeline-source)",
        "output": "var(--pipeline-storage)",
        "custom": "var(--pipeline-embedding)",
    }
    return mapping.get(category, "#64748b")


def _ui_category(category: str) -> str:
    if category == "utility":
        return "transform"
    return category


def rag_instance_contract() -> dict[str, Any]:
    return {
        "required_fields": ["name", "nodes", "edges"],
        "optional_fields": ["description", "pipeline_type", "org_unit_id"],
        "top_level_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "pipeline_type": {"type": "string", "enum": ["ingestion", "retrieval"]},
                "nodes": {"type": "array", "items": {"type": "object"}},
                "edges": {"type": "array", "items": {"type": "object"}},
                "org_unit_id": {"type": "string"},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        "edge_contract": {
            "required_fields": ["id", "source", "target"],
            "field_shapes": {
                "id": {"type": "string"},
                "source": {"type": "string"},
                "target": {"type": "string"},
                "source_handle": {"type": "string"},
                "target_handle": {"type": "string"},
            },
        },
    }
