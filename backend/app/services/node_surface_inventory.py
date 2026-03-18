from __future__ import annotations

from typing import Any

from app.agent.executors.standard import register_standard_operators
from app.agent.graph.schema import NodeType
from app.agent.registry import AgentExecutorRegistry, AgentOperatorRegistry
from app.rag.pipeline.registry import OperatorRegistry


def _required_fields(config_schema: dict[str, Any]) -> list[str]:
    raw = config_schema.get("required")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def build_node_surface_inventory() -> dict[str, Any]:
    register_standard_operators()

    agent_schema_enum_types = sorted({item.value for item in NodeType})
    agent_specs = sorted(AgentOperatorRegistry.list_operators(), key=lambda item: item.type)
    rag_specs = sorted(
        OperatorRegistry.get_instance().list_all(),
        key=lambda item: (str(getattr(item.category, "value", item.category)), item.operator_id),
    )

    agent_nodes: list[dict[str, Any]] = []
    for spec in agent_specs:
        config_schema = spec.config_schema if isinstance(spec.config_schema, dict) else {}
        agent_nodes.append(
            {
                "type": spec.type,
                "display_name": spec.display_name,
                "category": spec.category,
                "description": spec.description,
                "reads": [str(item) for item in list(spec.reads or [])],
                "writes": [str(item) for item in list(spec.writes or [])],
                "required_config_fields": _required_fields(config_schema),
                "has_executor": AgentExecutorRegistry.get_executor_cls(spec.type) is not None,
                "declared_in_graph_schema_enum": spec.type in agent_schema_enum_types,
            }
        )

    rag_operators: list[dict[str, Any]] = []
    for spec in rag_specs:
        required_config = list(spec.required_config or [])
        optional_config = list(spec.optional_config or [])
        rag_operators.append(
            {
                "operator_id": spec.operator_id,
                "display_name": spec.display_name,
                "category": getattr(spec.category, "value", spec.category),
                "input_type": getattr(spec.input_type, "value", spec.input_type),
                "output_type": getattr(spec.output_type, "value", spec.output_type),
                "required_config_fields": [field.name for field in required_config],
                "optional_config_fields": [field.name for field in optional_config],
                "is_custom": bool(spec.is_custom),
                "deprecated": bool(spec.deprecated),
            }
        )

    registered_agent_types = sorted(item["type"] for item in agent_nodes)
    rag_operator_ids = sorted(item["operator_id"] for item in rag_operators)
    schema_only_agent_types = sorted(set(agent_schema_enum_types) - set(registered_agent_types))
    registered_only_agent_types = sorted(set(registered_agent_types) - set(agent_schema_enum_types))

    return {
        "agent_nodes": {
            "schema_enum_types": agent_schema_enum_types,
            "registered_types": registered_agent_types,
            "schema_only_types": schema_only_agent_types,
            "registered_only_types": registered_only_agent_types,
            "items": agent_nodes,
        },
        "rag_operators": {
            "registered_operator_ids": rag_operator_ids,
            "items": rag_operators,
        },
        "summary": {
            "agent_schema_enum_count": len(agent_schema_enum_types),
            "agent_registered_count": len(registered_agent_types),
            "rag_operator_count": len(rag_operator_ids),
        },
    }


def render_node_surface_inventory_markdown(inventory: dict[str, Any], *, last_updated: str) -> str:
    lines: list[str] = [
        "# Generated Node Surface Inventory",
        "",
        f"Last Updated: {last_updated}",
        "",
        "This file is generated from the live agent-node and RAG-operator registries.",
        "",
        "## Scope",
        "- Agent graph schema enum types.",
        "- Registered agent node operators and executor coverage.",
        "- Registered RAG pipeline operators and their contract surfaces.",
        "",
        "## Summary",
        f"- Agent schema enum types: {inventory['summary']['agent_schema_enum_count']}",
        f"- Registered agent node types: {inventory['summary']['agent_registered_count']}",
        f"- Registered RAG operators: {inventory['summary']['rag_operator_count']}",
        "",
        "## Agent Schema Enum Types",
    ]
    lines.extend(f"- `{item}`" for item in inventory["agent_nodes"]["schema_enum_types"])

    lines.extend(
        [
            "",
            "## Agent Registry Drift",
            "- Schema enum types without a registered operator:",
        ]
    )
    schema_only = inventory["agent_nodes"]["schema_only_types"]
    if schema_only:
        lines.extend(f"  - `{item}`" for item in schema_only)
    else:
        lines.append("  - none")

    lines.extend(
        [
            "- Registered agent node types not declared in the graph schema enum:",
        ]
    )
    registered_only = inventory["agent_nodes"]["registered_only_types"]
    if registered_only:
        lines.extend(f"  - `{item}`" for item in registered_only)
    else:
        lines.append("  - none")

    lines.extend(
        [
            "",
            "## Registered Agent Nodes",
            "| Type | Category | Executor | In Schema Enum | Required Config Fields |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in inventory["agent_nodes"]["items"]:
        required = ", ".join(item["required_config_fields"]) or "-"
        lines.append(
            f"| `{item['type']}` | `{item['category']}` | "
            f"{'yes' if item['has_executor'] else 'no'} | "
            f"{'yes' if item['declared_in_graph_schema_enum'] else 'no'} | "
            f"{required} |"
        )

    lines.extend(
        [
            "",
            "## Registered RAG Operators",
            "| Operator | Category | Input | Output | Required Config Fields |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in inventory["rag_operators"]["items"]:
        required = ", ".join(item["required_config_fields"]) or "-"
        lines.append(
            f"| `{item['operator_id']}` | `{item['category']}` | "
            f"`{item['input_type']}` | `{item['output_type']}` | {required} |"
        )

    lines.append("")
    return "\n".join(lines)
