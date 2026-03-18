from __future__ import annotations

from app.services.node_surface_inventory import (
    build_node_surface_inventory,
    render_node_surface_inventory_markdown,
)


def test_inventory_reports_executor_coverage_for_registered_agent_nodes():
    inventory = build_node_surface_inventory()

    agent_nodes = inventory["agent_nodes"]["items"]
    by_type = {item["type"]: item for item in agent_nodes}

    assert by_type["start"]["has_executor"] is True
    assert by_type["tool"]["has_executor"] is True
    assert by_type["agent"]["has_executor"] is True
    assert by_type["human_input"]["has_executor"] is True


def test_inventory_exposes_schema_registry_drift_explicitly():
    inventory = build_node_surface_inventory()

    schema_only = set(inventory["agent_nodes"]["schema_only_types"])
    registered_only = set(inventory["agent_nodes"]["registered_only_types"])

    assert {"llm_call", "tool_call", "rag_pipeline"}.issubset(schema_only)
    assert {"agent", "tool", "classify", "rag", "vector_search"}.issubset(registered_only)


def test_inventory_captures_core_rag_operator_contract_surface():
    inventory = build_node_surface_inventory()

    rag_by_id = {item["operator_id"]: item for item in inventory["rag_operators"]["items"]}

    assert rag_by_id["query_input"]["category"] == "input"
    assert rag_by_id["vector_search"]["category"] == "retrieval"
    assert rag_by_id["retrieval_result"]["category"] == "output"
    assert "knowledge_store_id" in rag_by_id["vector_search"]["required_config_fields"]


def test_inventory_markdown_calls_out_drift_sections():
    inventory = build_node_surface_inventory()

    markdown = render_node_surface_inventory_markdown(inventory, last_updated="2026-03-18")

    assert "# Generated Node Surface Inventory" in markdown
    assert "## Agent Registry Drift" in markdown
    assert "`agent`" in markdown
    assert "`vector_search`" in markdown
