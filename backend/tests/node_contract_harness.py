from __future__ import annotations

from typing import Any

from app.services.node_surface_inventory import build_node_surface_inventory


def agent_node_contract_rows() -> list[dict[str, Any]]:
    inventory = build_node_surface_inventory()
    return list(inventory["agent_nodes"]["items"])


def rag_operator_contract_rows() -> list[dict[str, Any]]:
    inventory = build_node_surface_inventory()
    return list(inventory["rag_operators"]["items"])


def rows_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(row[key]): row for row in rows}
