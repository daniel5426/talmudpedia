from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import re
from typing import Any, Callable


class GraphMutationError(Exception):
    def __init__(self, errors: list[dict[str, Any]]):
        self.errors = errors
        message = "; ".join(str(item.get("message") or item.get("code") or "Graph mutation failed") for item in errors)
        super().__init__(message or "Graph mutation failed")


@dataclass
class GraphMutationResult:
    graph: dict[str, Any]
    applied_operations: list[dict[str, Any]] = field(default_factory=list)
    changed_node_ids: list[str] = field(default_factory=list)
    changed_edge_ids: list[str] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)


_PATH_TOKEN_RE = re.compile(r"([^\.\[\]]+)|\[(\d+)\]")


def apply_graph_operations(
    graph_definition: dict[str, Any],
    operations: list[dict[str, Any]],
    *,
    validate_node_config_path: Callable[[dict[str, Any], list[str | int]], None] | None = None,
) -> GraphMutationResult:
    graph = deepcopy(graph_definition if isinstance(graph_definition, dict) else {})
    graph.setdefault("nodes", [])
    graph.setdefault("edges", [])
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise GraphMutationError(
            [
                {
                    "code": "GRAPH_MUTATION_INVALID_GRAPH",
                    "message": "graph_definition must contain list-valued nodes and edges",
                }
            ]
        )

    result = GraphMutationResult(graph=graph)
    changed_node_ids: set[str] = set()
    changed_edge_ids: set[str] = set()

    for index, raw_operation in enumerate(operations or []):
        if not isinstance(raw_operation, dict):
            raise GraphMutationError(
                [
                    {
                        "code": "GRAPH_MUTATION_INVALID_OPERATION",
                        "message": f"Operation at index {index} must be an object",
                        "operation_index": index,
                    }
                ]
            )
        operation = dict(raw_operation)
        op_name = str(operation.get("op") or "").strip()
        if not op_name:
            raise GraphMutationError(
                [
                    {
                        "code": "GRAPH_MUTATION_MISSING_OP",
                        "message": f"Operation at index {index} is missing op",
                        "operation_index": index,
                    }
                ]
            )

        handler = _OP_HANDLERS.get(op_name)
        if handler is None:
            raise GraphMutationError(
                [
                    {
                        "code": "GRAPH_MUTATION_UNSUPPORTED_OP",
                        "message": f"Unsupported graph mutation op '{op_name}'",
                        "operation_index": index,
                        "op": op_name,
                    }
                ]
            )

        applied = handler(
            graph,
            operation,
            validate_node_config_path=validate_node_config_path,
        )
        result.applied_operations.append(applied)
        changed_node_ids.update(applied.get("changed_node_ids", []))
        changed_edge_ids.update(applied.get("changed_edge_ids", []))
        warnings = applied.get("warnings")
        if isinstance(warnings, list):
            result.warnings.extend([item for item in warnings if isinstance(item, dict)])

    result.changed_node_ids = sorted(changed_node_ids)
    result.changed_edge_ids = sorted(changed_edge_ids)
    return result


def _parse_path(path: Any) -> list[str | int]:
    if not isinstance(path, str) or not path.strip():
        raise GraphMutationError(
            [{"code": "GRAPH_MUTATION_INVALID_PATH", "message": "Operation path must be a non-empty string"}]
        )
    tokens: list[str | int] = []
    for match in _PATH_TOKEN_RE.finditer(path.strip()):
        key, index = match.groups()
        if key is not None:
            tokens.append(key)
        elif index is not None:
            tokens.append(int(index))
    if not tokens:
        raise GraphMutationError(
            [{"code": "GRAPH_MUTATION_INVALID_PATH", "message": f"Unable to parse operation path '{path}'"}]
        )
    return tokens


def _node_index(graph: dict[str, Any], node_id: str) -> tuple[int, dict[str, Any]]:
    for idx, node in enumerate(graph.get("nodes") or []):
        if isinstance(node, dict) and str(node.get("id")) == str(node_id):
            return idx, node
    raise GraphMutationError(
        [{"code": "GRAPH_MUTATION_NODE_NOT_FOUND", "message": f"Node '{node_id}' was not found", "node_id": node_id}]
    )


def _edge_index(graph: dict[str, Any], edge_id: str) -> tuple[int, dict[str, Any]]:
    for idx, edge in enumerate(graph.get("edges") or []):
        if isinstance(edge, dict) and str(edge.get("id")) == str(edge_id):
            return idx, edge
    raise GraphMutationError(
        [{"code": "GRAPH_MUTATION_EDGE_NOT_FOUND", "message": f"Edge '{edge_id}' was not found", "edge_id": edge_id}]
    )


def _ensure_node_absent(graph: dict[str, Any], node_id: str) -> None:
    try:
        _node_index(graph, node_id)
    except GraphMutationError:
        return
    raise GraphMutationError(
        [{"code": "GRAPH_MUTATION_DUPLICATE_NODE", "message": f"Node '{node_id}' already exists", "node_id": node_id}]
    )


def _ensure_edge_absent(graph: dict[str, Any], edge_id: str) -> None:
    try:
        _edge_index(graph, edge_id)
    except GraphMutationError:
        return
    raise GraphMutationError(
        [{"code": "GRAPH_MUTATION_DUPLICATE_EDGE", "message": f"Edge '{edge_id}' already exists", "edge_id": edge_id}]
    )


def _config_root(node: dict[str, Any]) -> dict[str, Any]:
    config = node.get("config")
    if not isinstance(config, dict):
        config = {}
        node["config"] = config
    return config


def _set_path_value(root: Any, segments: list[str | int], value: Any) -> None:
    current = root
    for idx, segment in enumerate(segments[:-1]):
        next_segment = segments[idx + 1]
        if isinstance(segment, int):
            if not isinstance(current, list) or segment >= len(current):
                raise GraphMutationError(
                    [{"code": "GRAPH_MUTATION_INVALID_PATH", "message": f"List index '{segment}' is out of range"}]
                )
            current = current[segment]
            continue

        if not isinstance(current, dict):
            raise GraphMutationError(
                [{"code": "GRAPH_MUTATION_INVALID_PATH", "message": f"Cannot descend into non-object at '{segment}'"}]
            )
        if segment not in current or current[segment] is None:
            current[segment] = [] if isinstance(next_segment, int) else {}
        current = current[segment]
    last = segments[-1]
    if isinstance(last, int):
        if not isinstance(current, list):
            raise GraphMutationError(
                [{"code": "GRAPH_MUTATION_INVALID_PATH", "message": f"Expected list before index '{last}'"}]
            )
        if last == len(current):
            current.append(value)
        elif 0 <= last < len(current):
            current[last] = value
        else:
            raise GraphMutationError(
                [{"code": "GRAPH_MUTATION_INVALID_PATH", "message": f"List index '{last}' is out of range"}]
            )
        return
    if not isinstance(current, dict):
        raise GraphMutationError(
            [{"code": "GRAPH_MUTATION_INVALID_PATH", "message": f"Cannot set key '{last}' on non-object"}]
        )
    current[last] = value


def _remove_path_value(root: Any, segments: list[str | int]) -> Any:
    current = root
    for segment in segments[:-1]:
        if isinstance(segment, int):
            if not isinstance(current, list) or segment >= len(current):
                raise GraphMutationError(
                    [{"code": "GRAPH_MUTATION_INVALID_PATH", "message": f"List index '{segment}' is out of range"}]
                )
            current = current[segment]
            continue
        if not isinstance(current, dict) or segment not in current:
            raise GraphMutationError(
                [{"code": "GRAPH_MUTATION_INVALID_PATH", "message": f"Path segment '{segment}' was not found"}]
            )
        current = current[segment]
    last = segments[-1]
    if isinstance(last, int):
        if not isinstance(current, list) or last >= len(current):
            raise GraphMutationError(
                [{"code": "GRAPH_MUTATION_INVALID_PATH", "message": f"List index '{last}' is out of range"}]
            )
        return current.pop(last)
    if not isinstance(current, dict) or last not in current:
        raise GraphMutationError(
            [{"code": "GRAPH_MUTATION_INVALID_PATH", "message": f"Path segment '{last}' was not found"}]
        )
    return current.pop(last)


def _resolve_path_value(root: Any, segments: list[str | int]) -> Any:
    current = root
    for segment in segments:
        if isinstance(segment, int):
            if not isinstance(current, list) or segment >= len(current):
                raise GraphMutationError(
                    [{"code": "GRAPH_MUTATION_INVALID_PATH", "message": f"List index '{segment}' is out of range"}]
                )
            current = current[segment]
            continue
        if not isinstance(current, dict) or segment not in current:
            raise GraphMutationError(
                [{"code": "GRAPH_MUTATION_INVALID_PATH", "message": f"Path segment '{segment}' was not found"}]
            )
        current = current[segment]
    return current


def _validate_path(node: dict[str, Any], segments: list[str | int], validate_node_config_path: Callable[[dict[str, Any], list[str | int]], None] | None) -> None:
    if validate_node_config_path is None:
        return
    validate_node_config_path(node, segments)


def _op_set_node_config_value(
    graph: dict[str, Any],
    operation: dict[str, Any],
    *,
    validate_node_config_path: Callable[[dict[str, Any], list[str | int]], None] | None,
) -> dict[str, Any]:
    node_id = str(operation.get("node_id") or "")
    if not node_id:
        raise GraphMutationError([{"code": "GRAPH_MUTATION_MISSING_NODE_ID", "message": "set_node_config_value requires node_id"}])
    path = _parse_path(operation.get("path"))
    _, node = _node_index(graph, node_id)
    _validate_path(node, path, validate_node_config_path)
    config = _config_root(node)
    _set_path_value(config, path, deepcopy(operation.get("value")))
    return {**operation, "changed_node_ids": [node_id], "changed_edge_ids": []}


def _op_remove_node_config_value(
    graph: dict[str, Any],
    operation: dict[str, Any],
    *,
    validate_node_config_path: Callable[[dict[str, Any], list[str | int]], None] | None,
) -> dict[str, Any]:
    node_id = str(operation.get("node_id") or "")
    if not node_id:
        raise GraphMutationError([{"code": "GRAPH_MUTATION_MISSING_NODE_ID", "message": "remove_node_config_value requires node_id"}])
    path = _parse_path(operation.get("path"))
    _, node = _node_index(graph, node_id)
    _validate_path(node, path, validate_node_config_path)
    config = _config_root(node)
    _remove_path_value(config, path)
    return {**operation, "changed_node_ids": [node_id], "changed_edge_ids": []}


def _op_append_unique_node_config_list_item(
    graph: dict[str, Any],
    operation: dict[str, Any],
    *,
    validate_node_config_path: Callable[[dict[str, Any], list[str | int]], None] | None,
) -> dict[str, Any]:
    node_id = str(operation.get("node_id") or "")
    if not node_id:
        raise GraphMutationError([{"code": "GRAPH_MUTATION_MISSING_NODE_ID", "message": "append_unique_node_config_list_item requires node_id"}])
    path = _parse_path(operation.get("path"))
    _, node = _node_index(graph, node_id)
    _validate_path(node, path, validate_node_config_path)
    config = _config_root(node)
    try:
        target = _resolve_path_value(config, path)
        if not isinstance(target, list):
            raise GraphMutationError([{"code": "GRAPH_MUTATION_INVALID_PATH", "message": f"Path '{operation.get('path')}' must point to a list"}])
    except GraphMutationError:
        _set_path_value(config, path, [])
        target = _resolve_path_value(config, path)
    value = deepcopy(operation.get("value"))
    if value not in target:
        target.append(value)
    return {**operation, "changed_node_ids": [node_id], "changed_edge_ids": []}


def _op_remove_node_config_list_item(
    graph: dict[str, Any],
    operation: dict[str, Any],
    *,
    validate_node_config_path: Callable[[dict[str, Any], list[str | int]], None] | None,
) -> dict[str, Any]:
    node_id = str(operation.get("node_id") or "")
    if not node_id:
        raise GraphMutationError([{"code": "GRAPH_MUTATION_MISSING_NODE_ID", "message": "remove_node_config_list_item requires node_id"}])
    path = _parse_path(operation.get("path"))
    _, node = _node_index(graph, node_id)
    _validate_path(node, path, validate_node_config_path)
    config = _config_root(node)
    target = _resolve_path_value(config, path)
    if not isinstance(target, list):
        raise GraphMutationError([{"code": "GRAPH_MUTATION_INVALID_PATH", "message": f"Path '{operation.get('path')}' must point to a list"}])
    value = operation.get("value")
    if value in target:
        target.remove(value)
    return {**operation, "changed_node_ids": [node_id], "changed_edge_ids": []}


def _op_insert_node(
    graph: dict[str, Any],
    operation: dict[str, Any],
    *,
    validate_node_config_path: Callable[[dict[str, Any], list[str | int]], None] | None,
) -> dict[str, Any]:
    del validate_node_config_path
    node = deepcopy(operation.get("node"))
    node_id = str(node.get("id") or "") if isinstance(node, dict) else ""
    if not node_id:
        raise GraphMutationError([{"code": "GRAPH_MUTATION_INVALID_NODE", "message": "insert_node requires node with id"}])
    _ensure_node_absent(graph, node_id)
    graph["nodes"].append(node)
    return {**operation, "changed_node_ids": [node_id], "changed_edge_ids": []}


def _op_remove_node(
    graph: dict[str, Any],
    operation: dict[str, Any],
    *,
    validate_node_config_path: Callable[[dict[str, Any], list[str | int]], None] | None,
) -> dict[str, Any]:
    del validate_node_config_path
    node_id = str(operation.get("node_id") or "")
    if not node_id:
        raise GraphMutationError([{"code": "GRAPH_MUTATION_MISSING_NODE_ID", "message": "remove_node requires node_id"}])
    idx, _node = _node_index(graph, node_id)
    graph["nodes"].pop(idx)
    removed_edge_ids = [str(edge.get("id")) for edge in list(graph["edges"]) if isinstance(edge, dict) and (str(edge.get("source")) == node_id or str(edge.get("target")) == node_id)]
    graph["edges"] = [edge for edge in graph["edges"] if not (isinstance(edge, dict) and (str(edge.get("source")) == node_id or str(edge.get("target")) == node_id))]
    warnings = []
    if removed_edge_ids:
        warnings.append(
            {
                "code": "GRAPH_MUTATION_REMOVED_CONNECTED_EDGES",
                "message": f"Removing node '{node_id}' also removed {len(removed_edge_ids)} connected edges",
                "edge_ids": removed_edge_ids,
            }
        )
    return {**operation, "changed_node_ids": [node_id], "changed_edge_ids": removed_edge_ids, "warnings": warnings}


def _op_replace_node(
    graph: dict[str, Any],
    operation: dict[str, Any],
    *,
    validate_node_config_path: Callable[[dict[str, Any], list[str | int]], None] | None,
) -> dict[str, Any]:
    del validate_node_config_path
    node = deepcopy(operation.get("node"))
    node_id = str(operation.get("node_id") or (node.get("id") if isinstance(node, dict) else "") or "")
    if not node_id or not isinstance(node, dict):
        raise GraphMutationError([{"code": "GRAPH_MUTATION_INVALID_NODE", "message": "replace_node requires node_id and node"}])
    idx, _existing = _node_index(graph, node_id)
    node["id"] = node_id
    graph["nodes"][idx] = node
    return {**operation, "changed_node_ids": [node_id], "changed_edge_ids": []}


def _op_insert_edge(
    graph: dict[str, Any],
    operation: dict[str, Any],
    *,
    validate_node_config_path: Callable[[dict[str, Any], list[str | int]], None] | None,
) -> dict[str, Any]:
    del validate_node_config_path
    edge = deepcopy(operation.get("edge"))
    edge_id = str(edge.get("id") or "") if isinstance(edge, dict) else ""
    if not edge_id:
        raise GraphMutationError([{"code": "GRAPH_MUTATION_INVALID_EDGE", "message": "insert_edge requires edge with id"}])
    _ensure_edge_absent(graph, edge_id)
    graph["edges"].append(edge)
    return {**operation, "changed_node_ids": [], "changed_edge_ids": [edge_id]}


def _op_remove_edge(
    graph: dict[str, Any],
    operation: dict[str, Any],
    *,
    validate_node_config_path: Callable[[dict[str, Any], list[str | int]], None] | None,
) -> dict[str, Any]:
    del validate_node_config_path
    edge_id = str(operation.get("edge_id") or "")
    if not edge_id:
        raise GraphMutationError([{"code": "GRAPH_MUTATION_MISSING_EDGE_ID", "message": "remove_edge requires edge_id"}])
    idx, _edge = _edge_index(graph, edge_id)
    graph["edges"].pop(idx)
    return {**operation, "changed_node_ids": [], "changed_edge_ids": [edge_id]}


def _op_rewire_edge(
    graph: dict[str, Any],
    operation: dict[str, Any],
    *,
    validate_node_config_path: Callable[[dict[str, Any], list[str | int]], None] | None,
) -> dict[str, Any]:
    del validate_node_config_path
    edge_id = str(operation.get("edge_id") or "")
    if not edge_id:
        raise GraphMutationError([{"code": "GRAPH_MUTATION_MISSING_EDGE_ID", "message": "rewire_edge requires edge_id"}])
    idx, edge = _edge_index(graph, edge_id)
    next_edge = deepcopy(edge)
    for key in ("source", "target", "source_handle", "target_handle"):
        if key in operation:
            next_edge[key] = operation.get(key)
    graph["edges"][idx] = next_edge
    return {**operation, "changed_node_ids": [], "changed_edge_ids": [edge_id]}


def _op_set_graph_metadata_value(
    graph: dict[str, Any],
    operation: dict[str, Any],
    *,
    validate_node_config_path: Callable[[dict[str, Any], list[str | int]], None] | None,
) -> dict[str, Any]:
    del validate_node_config_path
    path = _parse_path(operation.get("path"))
    if path and path[0] in {"nodes", "edges"}:
        raise GraphMutationError(
            [{"code": "GRAPH_MUTATION_INVALID_PATH", "message": "set_graph_metadata_value cannot target nodes or edges root"}]
        )
    _set_path_value(graph, path, deepcopy(operation.get("value")))
    return {**operation, "changed_node_ids": [], "changed_edge_ids": []}


_OP_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "set_node_config_value": _op_set_node_config_value,
    "remove_node_config_value": _op_remove_node_config_value,
    "append_unique_node_config_list_item": _op_append_unique_node_config_list_item,
    "remove_node_config_list_item": _op_remove_node_config_list_item,
    "insert_node": _op_insert_node,
    "remove_node": _op_remove_node,
    "replace_node": _op_replace_node,
    "insert_edge": _op_insert_edge,
    "remove_edge": _op_remove_edge,
    "rewire_edge": _op_rewire_edge,
    "set_graph_metadata_value": _op_set_graph_metadata_value,
}
