from __future__ import annotations

from typing import Any

from app.agent.registry import AgentOperatorSpec
from app.graph_authoring.schema import enrich_schema_with_ui, required_config_fields, schema_for_value_type
from app.graph_authoring.types import BranchingHint, GraphHints, NodeAuthoringSpec, NodeCatalogItem
from app.agent.graph.contracts import contract_fields_from_schema, schema_to_value_type


def _editor_for_type(node_type: str) -> str:
    if node_type in {"start", "end", "classify", "set_state"}:
        return node_type
    return "generic"


def _branching_for_agent(spec: AgentOperatorSpec) -> BranchingHint | None:
    ui = spec.ui if isinstance(spec.ui, dict) else {}
    static_handles = ui.get("staticHandles")
    if isinstance(static_handles, list) and static_handles:
        return BranchingHint(kind="static", static_handles=[str(item) for item in static_handles])

    if spec.type == "if_else":
        return BranchingHint(
            kind="config_array",
            field="conditions",
            id_key="id",
            label_key="name",
            default_handles=["else"],
        )
    if spec.type == "classify":
        return BranchingHint(kind="config_array", field="categories", id_key="id", label_key="name")
    if spec.type == "router":
        return BranchingHint(kind="route_table", field="route_table", label_key="name", default_handles=["default"])
    if spec.type == "judge":
        return BranchingHint(kind="outcomes", field="route_table", label_key="name")
    if spec.type == "join":
        return BranchingHint(
            kind="static",
            static_handles=["completed", "completed_with_errors", "failed", "timed_out", "pending"],
        )
    if spec.type == "replan":
        return BranchingHint(kind="static", static_handles=["replan", "continue"])
    return None


def _output_schema_from_contract(spec: AgentOperatorSpec) -> dict[str, Any] | None:
    output_contract = spec.output_contract if isinstance(spec.output_contract, dict) else {}
    fields = output_contract.get("fields")
    if not isinstance(fields, list) or not fields:
        return None
    properties: dict[str, Any] = {}
    for field in fields:
        if not isinstance(field, dict):
            continue
        key = str(field.get("key") or "").strip()
        if not key:
            continue
        field_schema = schema_for_value_type(str(field.get("type") or ""))
        if field.get("label"):
            field_schema["title"] = str(field["label"])
        properties[key] = field_schema
    if not properties:
        return None
    return {"type": "object", "properties": properties, "additionalProperties": True}


def agent_node_spec(spec: AgentOperatorSpec) -> NodeAuthoringSpec:
    ui = spec.ui if isinstance(spec.ui, dict) else {}
    config_schema = enrich_schema_with_ui(
        spec.config_schema if isinstance(spec.config_schema, dict) else {},
        list(ui.get("configFields") or []) if isinstance(ui.get("configFields"), list) else [],
    )
    config_schema = _canonicalize_route_table_fields(spec.type, config_schema)
    graph_hints = GraphHints(
        editor=_editor_for_type(spec.type),
        branching=_branching_for_agent(spec),
    )
    return NodeAuthoringSpec(
        type=spec.type,
        title=spec.display_name,
        description=spec.description,
        category=spec.category,
        input_type=str(ui.get("inputType") or "any"),
        output_type=str(ui.get("outputType") or "any"),
        config_schema=config_schema,
        output_schema=_output_schema_from_contract(spec),
        field_contracts=spec.field_contracts or None,
        graph_hints=graph_hints,
    )


def agent_catalog_item(spec: AgentOperatorSpec) -> NodeCatalogItem:
    authoring = agent_node_spec(spec)
    ui = spec.ui if isinstance(spec.ui, dict) else {}
    return NodeCatalogItem(
        type=authoring.type,
        title=authoring.title,
        description=authoring.description,
        category=authoring.category,
        input_type=authoring.input_type,
        output_type=authoring.output_type,
        required_config_fields=required_config_fields(authoring.config_schema),
        icon=str(ui.get("icon") or "Circle"),
        color=str(ui.get("color") or "#64748b"),
        editor=authoring.graph_hints.editor if authoring.graph_hints else "generic",
    )


def artifact_node_spec(
    *,
    artifact_id: str,
    artifact_revision_id: str,
    display_name: str,
    description: str,
    config_schema: dict[str, Any],
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
    node_ui: dict[str, Any],
    reads: list[str] | None = None,
    writes: list[str] | None = None,
) -> tuple[NodeAuthoringSpec, NodeCatalogItem]:
    del reads, writes
    inputs = _artifact_input_specs(input_schema, node_ui)
    schema = enrich_schema_with_ui(
        config_schema,
        _artifact_config_fields_from_schema(config_schema),
    )
    root_ui = schema.get("x-ui")
    root_ui = dict(root_ui) if isinstance(root_ui, dict) else {}
    root_ui["artifactInputs"] = inputs
    schema["x-ui"] = root_ui

    spec = NodeAuthoringSpec(
        type=f"artifact:{artifact_id}",
        title=display_name,
        description=description,
        category="action",
        input_type=str(node_ui.get("inputType") or "any"),
        output_type=str(node_ui.get("outputType") or "context"),
        config_schema=schema,
        output_schema=output_schema or None,
        field_contracts=None,
        graph_hints=GraphHints(editor="generic"),
    )
    item = NodeCatalogItem(
        type=spec.type,
        title=spec.title,
        description=spec.description,
        category=spec.category,
        input_type=spec.input_type,
        output_type=spec.output_type,
        required_config_fields=required_config_fields(schema),
        icon=str(node_ui.get("icon") or "Package"),
        color=str(node_ui.get("color") or "#64748b"),
        editor="generic",
    )
    item_dict = item.model_dump()
    item_dict["artifact_revision_id"] = artifact_revision_id
    return spec, NodeCatalogItem.model_validate(item_dict)


def _artifact_config_fields_from_schema(config_schema: dict[str, Any]) -> list[dict[str, Any]]:
    properties = config_schema.get("properties") if isinstance(config_schema.get("properties"), dict) else {}
    required = set(config_schema.get("required") or []) if isinstance(config_schema.get("required"), list) else set()
    fields: list[dict[str, Any]] = []
    for key, value in properties.items():
        value = value if isinstance(value, dict) else {}
        field: dict[str, Any] = {
            "name": str(key),
            "label": str(value.get("title") or key),
            "fieldType": _artifact_field_type(value.get("type")),
            "required": key in required,
            "description": value.get("description"),
        }
        enum_values = value.get("enum")
        if isinstance(enum_values, list) and enum_values:
            field["fieldType"] = "select"
            field["options"] = [{"value": str(item), "label": str(item)} for item in enum_values]
        if "default" in value:
            field["default"] = value.get("default")
        fields.append(field)
    return fields


def _artifact_field_type(json_type: str) -> str:
    mapping = {
        "string": "string",
        "integer": "number",
        "number": "number",
        "boolean": "boolean",
        "array": "text",
        "object": "text",
    }
    return mapping.get(str(json_type or "").strip().lower(), "string")


def _artifact_input_specs(input_schema: dict[str, Any], node_ui: dict[str, Any]) -> list[dict[str, Any]]:
    properties = input_schema.get("properties") if isinstance(input_schema.get("properties"), dict) else {}
    required = set(input_schema.get("required") or []) if isinstance(input_schema.get("required"), list) else set()
    ui_inputs = node_ui.get("inputs") if isinstance(node_ui.get("inputs"), list) else []
    input_labels = {
        str(item.get("name") or "").strip(): str(item.get("label") or item.get("title") or item.get("name") or "").strip()
        for item in ui_inputs
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    }
    specs: list[dict[str, Any]] = []
    for key, value in properties.items():
        value = value if isinstance(value, dict) else {}
        specs.append(
            {
                "name": str(key),
                "type": schema_to_value_type(value),
                "required": key in required,
                "default": value.get("default"),
                "description": value.get("description"),
                "label": input_labels.get(str(key)) or str(value.get("title") or key),
            }
        )
    return specs


def agent_instance_contract() -> dict[str, Any]:
    return {
        "required_fields": ["nodes", "edges"],
        "node_required_fields": ["id", "type", "position"],
        "edge_required_fields": ["id", "source", "target"],
        "edge_field_shapes": {
            "id": {"type": "string"},
            "source": {"type": "string"},
            "target": {"type": "string"},
            "type": {"type": "string", "enum": ["control", "data"]},
            "source_handle": {"type": "string"},
            "target_handle": {"type": "string"},
            "label": {"type": "string"},
            "condition": {"type": "string"},
        },
    }


def _canonicalize_route_table_fields(node_type: str, config_schema: dict[str, Any]) -> dict[str, Any]:
    if node_type not in {"router", "judge"}:
        return config_schema
    properties = config_schema.get("properties")
    if not isinstance(properties, dict):
        return config_schema
    original_key = "routes" if node_type == "router" else "outcomes"
    if original_key not in properties or "route_table" in properties:
        return config_schema

    properties = dict(properties)
    properties["route_table"] = properties.pop(original_key)
    config_schema = dict(config_schema)
    config_schema["properties"] = properties

    required = config_schema.get("required")
    if isinstance(required, list):
        config_schema["required"] = ["route_table" if item == original_key else item for item in required]

    root_ui = config_schema.get("x-ui")
    if isinstance(root_ui, dict):
        next_ui = dict(root_ui)
        order = next_ui.get("order")
        if isinstance(order, list):
            next_ui["order"] = ["route_table" if item == original_key else item for item in order]
        config_schema["x-ui"] = next_ui
    return config_schema
