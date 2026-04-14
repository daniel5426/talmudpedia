from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.api.routers.rag_pipelines import get_pipeline_context, sync_custom_operators
from app.db.postgres.session import get_db
from app.rag.pipeline.registry import ConfigFieldType, OperatorRegistry
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.errors import ControlPlaneError
from app.services.control_plane.rag_admin_service import RagAdminService

router = APIRouter()


class OperatorSchemaRequest(BaseModel):
    operator_ids: list[str] = Field(default_factory=list)


def _runtime_binding_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {"runtime": {"type": "boolean", "const": True}},
        "required": ["runtime"],
        "additionalProperties": False,
    }


def _scalar_value_schema(field_type: Any, *, options: list[str] | None, json_schema: dict[str, Any] | None) -> Dict[str, Any]:
    if field_type == ConfigFieldType.INTEGER:
        return {"type": "integer"}
    if field_type == ConfigFieldType.FLOAT:
        return {"type": "number"}
    if field_type == ConfigFieldType.BOOLEAN:
        return {"type": "boolean"}
    if field_type == ConfigFieldType.JSON:
        if isinstance(json_schema, dict) and json_schema:
            return dict(json_schema)
        return {"type": ["object", "array"]}
    if field_type == ConfigFieldType.SELECT:
        schema: Dict[str, Any] = {"type": "string"}
        if options:
            schema["enum"] = list(options)
        return schema
    return {"type": "string"}


def _field_value_schema(field: Any) -> Dict[str, Any]:
    raw = field.model_dump() if hasattr(field, "model_dump") else dict(field)
    schema = _scalar_value_schema(
        getattr(field, "field_type", None),
        options=list(raw.get("options") or []),
        json_schema=raw.get("json_schema") if isinstance(raw.get("json_schema"), dict) else None,
    )
    min_value = raw.get("min_value")
    max_value = raw.get("max_value")
    if min_value is not None:
        schema["minimum"] = min_value
    if max_value is not None:
        schema["maximum"] = max_value
    if raw.get("runtime"):
        schema = {"anyOf": [schema, _runtime_binding_schema()]}
    return schema


def _config_field_payload(field: Any) -> Dict[str, Any]:
    raw = field.model_dump() if hasattr(field, "model_dump") else dict(field)
    raw["value_schema"] = _field_value_schema(field)
    return raw


def _config_contract(required: list[dict[str, Any]], optional: list[dict[str, Any]]) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    for field in required + optional:
        name = str(field.get("name") or "").strip()
        if not name:
            continue
        properties[name] = field.get("value_schema") if isinstance(field.get("value_schema"), dict) else {}
    return {
        "type": "object",
        "properties": properties,
        "required": [str(field.get("name")) for field in required if field.get("name")],
        "additionalProperties": True,
    }


def _config_example(required: list[dict[str, Any]], optional: list[dict[str, Any]]) -> Dict[str, Any]:
    example: Dict[str, Any] = {}
    for field in required + optional:
        name = str(field.get("name") or "").strip()
        if not name:
            continue
        if field.get("runtime"):
            example[name] = {"runtime": True}
            continue
        if field.get("default") is not None:
            example[name] = field.get("default")
            continue
        field_type = field.get("field_type")
        if field_type in {ConfigFieldType.INTEGER.value, ConfigFieldType.FLOAT.value}:
            example[name] = 0
        elif field_type == ConfigFieldType.BOOLEAN.value:
            example[name] = False
        elif field_type == ConfigFieldType.JSON.value:
            example[name] = {}
        else:
            example[name] = f"<{name}>"
    return example


def _visual_node_contract(spec: Any, *, config_contract: Dict[str, Any], config_example: Dict[str, Any]) -> Dict[str, Any]:
    operator_id = getattr(spec, "operator_id", None)
    category = getattr(getattr(spec, "category", None), "value", getattr(spec, "category", None))
    display_name = getattr(spec, "display_name", None)
    return {
        "required_fields": ["id", "category", "operator", "position"],
        "field_shapes": {
            "id": {"type": "string"},
            "category": {"type": "string", "const": category},
            "operator": {"type": "string", "const": operator_id},
            "position": {
                "type": "object",
                "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                "required": ["x", "y"],
                "additionalProperties": False,
            },
            "config": config_contract,
        },
        "example_node": {
            "id": f"{operator_id}_1" if operator_id else "node_1",
            "category": category,
            "operator": operator_id,
            "position": {"x": 0, "y": 0},
            "display_name": display_name,
            "config": config_example,
        },
    }


def _pipeline_create_contract() -> Dict[str, Any]:
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
            "example_edge": {"id": "edge_1", "source": "node_a", "target": "node_b"},
        },
        "notes": [
            "Use operator ids exactly as returned by rag.operators.catalog/schema.",
            "Each pipeline node must use operator as a string, not an object wrapper.",
            "Each pipeline node must set category to the operator's declared category.",
        ],
    }


def _operator_schema_payload(spec: Any) -> Dict[str, Any]:
    required = [_config_field_payload(field) for field in list(getattr(spec, "required_config", []) or [])]
    optional = [_config_field_payload(field) for field in list(getattr(spec, "optional_config", []) or [])]
    config_contract = _config_contract(required, optional)
    config_example = _config_example(required, optional)
    input_schema = getattr(spec, "resolved_input_schema", lambda: getattr(spec, "input_schema", None))()
    output_schema = getattr(spec, "resolved_output_schema", lambda: getattr(spec, "output_schema", None))()
    return {
        "operator_id": getattr(spec, "operator_id", None),
        "display_name": getattr(spec, "display_name", None),
        "category": getattr(getattr(spec, "category", None), "value", getattr(spec, "category", None)),
        "description": getattr(spec, "description", None),
        "version": getattr(spec, "version", None),
        "input_type": getattr(getattr(spec, "input_type", None), "value", getattr(spec, "input_type", None)),
        "output_type": getattr(getattr(spec, "output_type", None), "value", getattr(spec, "output_type", None)),
        "is_custom": bool(getattr(spec, "is_custom", False)),
        "deprecated": bool(getattr(spec, "deprecated", False)),
        "tags": list(getattr(spec, "tags", []) or []),
        "required_config": required,
        "optional_config": optional,
        "required_config_fields": [str(field.get("name")) for field in required if field.get("name")],
        "optional_config_fields": [str(field.get("name")) for field in optional if field.get("name")],
        "input_schema": input_schema or {},
        "output_schema": output_schema or {},
        "terminal_output_schema": input_schema if getattr(getattr(spec, "category", None), "value", getattr(spec, "category", None)) == "output" else output_schema or {},
        "config_schema": config_contract,
        "visual_node_contract": _visual_node_contract(
            spec,
            config_contract=config_contract,
            config_example=config_example,
        ),
    }


@router.post("/operators/schema", response_model=Dict[str, Any])
async def get_operator_schemas(
    request: OperatorSchemaRequest,
    tenant_slug: Optional[str] = None,
    context: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("pipelines.catalog.read")),
    db: AsyncSession = Depends(get_db),
):
    tenant, _user, _db = await get_pipeline_context(
        tenant_slug,
        current_user=context.get("user"),
        db=db,
        context=context,
    )
    if tenant is None:
        registry = OperatorRegistry.get_instance()
        tenant_id: Optional[str] = None
        operator_ids = [str(item).strip() for item in (request.operator_ids or []) if str(item).strip()]
        schemas: Dict[str, Dict[str, Any]] = {}
        unknown: list[str] = []
        for operator_id in operator_ids:
            spec = registry.get(operator_id, tenant_id=tenant_id)
            if spec is None:
                unknown.append(operator_id)
                continue
            schemas[operator_id] = _operator_schema_payload(spec)
        return {"schemas": schemas, "unknown": unknown, "pipeline_create_contract": _pipeline_create_contract()}
    try:
        result = await RagAdminService(db).operators_schema(
            ctx=ControlPlaneContext(
                tenant_id=tenant.id,
                user=context.get("user"),
                user_id=getattr(context.get("user"), "id", None),
                auth_token=context.get("auth_token"),
                scopes=tuple(context.get("scopes") or ()),
                is_service=bool(context.get("type") == "workload"),
                tenant_slug=tenant.slug,
            ),
            operator_ids=list(request.operator_ids or []),
        )
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc
    return {"schemas": result["schemas"], "unknown": [], "pipeline_create_contract": _pipeline_create_contract()}
