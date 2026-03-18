from __future__ import annotations

from backend.tests.node_contract_harness import (
    agent_node_contract_rows,
    rag_operator_contract_rows,
    rows_by_key,
)


def test_all_registered_agent_nodes_have_executor_category_and_contract_lists():
    rows = agent_node_contract_rows()

    assert rows
    assert all(row["has_executor"] is True for row in rows)
    assert all(isinstance(row["category"], str) and row["category"] for row in rows)
    assert all(isinstance(row["reads"], list) for row in rows)
    assert all(isinstance(row["writes"], list) for row in rows)


def test_all_registered_agent_node_types_are_unique():
    rows = agent_node_contract_rows()
    types = [row["type"] for row in rows]

    assert len(types) == len(set(types))


def test_all_rag_operator_ids_are_unique_and_have_io_contracts():
    rows = rag_operator_contract_rows()
    operator_ids = [row["operator_id"] for row in rows]

    assert rows
    assert len(operator_ids) == len(set(operator_ids))
    assert all(isinstance(row["category"], str) and row["category"] for row in rows)
    assert all(isinstance(row["input_type"], str) and row["input_type"] for row in rows)
    assert all(isinstance(row["output_type"], str) and row["output_type"] for row in rows)


def test_core_contract_rows_stay_addressable_by_identifier():
    agent_rows = rows_by_key(agent_node_contract_rows(), "type")
    rag_rows = rows_by_key(rag_operator_contract_rows(), "operator_id")

    assert agent_rows["agent"]["required_config_fields"] == ["model_id"]
    assert agent_rows["tool"]["has_executor"] is True
    assert "knowledge_store_id" in rag_rows["vector_search"]["required_config_fields"]
    assert rag_rows["query_input"]["input_type"] == "none"
