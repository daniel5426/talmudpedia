from __future__ import annotations

from typing import Any, Dict, List, Optional

from .types import RequestOptions, ResponseEnvelope


class AgentsAPI:
    def __init__(self, client: Any) -> None:
        self._client = client

    def list(
        self,
        *,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        view: str = "summary",
    ) -> ResponseEnvelope:
        params: Dict[str, Any] = {"skip": skip, "limit": limit, "view": view}
        if status:
            params["status"] = status
        return self._client.request("GET", "/agents", params=params)

    def create(self, spec: Dict[str, Any], options: Optional[RequestOptions] = None) -> ResponseEnvelope:
        return self._client.request("POST", "/agents", json_body=spec, options=options, mutation=True)

    def get(self, agent_id: str) -> ResponseEnvelope:
        return self._client.request("GET", f"/agents/{agent_id}")

    def update(
        self,
        agent_id: str,
        patch: Dict[str, Any],
        *,
        method: str = "PATCH",
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        if method.upper() not in {"PATCH", "PUT"}:
            raise ValueError("method must be PATCH or PUT")
        return self._client.request(
            method.upper(),
            f"/agents/{agent_id}",
            json_body=patch,
            options=options,
            mutation=True,
        )

    def update_graph(
        self,
        agent_id: str,
        graph: Dict[str, Any],
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "PUT",
            f"/agents/{agent_id}/graph",
            json_body=graph,
            options=options,
            mutation=True,
        )

    def get_graph(self, agent_id: str) -> ResponseEnvelope:
        return self._client.request("GET", f"/agents/{agent_id}/graph")

    def validate_graph_patch(
        self,
        agent_id: str,
        operations: List[Dict[str, Any]],
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/agents/{agent_id}/graph/validate-patch",
            json_body={"operations": list(operations or [])},
            mutation=False,
        )

    def apply_graph_patch(
        self,
        agent_id: str,
        operations: List[Dict[str, Any]],
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/agents/{agent_id}/graph/apply-patch",
            json_body={"operations": list(operations or [])},
            options=options,
            mutation=True,
        )

    def add_tool_to_agent_node(
        self,
        agent_id: str,
        *,
        node_id: str,
        tool_id: str,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/agents/{agent_id}/graph/add-tool-to-agent-node",
            json_body={"node_id": node_id, "tool_id": tool_id},
            options=options,
            mutation=True,
        )

    def remove_tool_from_agent_node(
        self,
        agent_id: str,
        *,
        node_id: str,
        tool_id: str,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/agents/{agent_id}/graph/remove-tool-from-agent-node",
            json_body={"node_id": node_id, "tool_id": tool_id},
            options=options,
            mutation=True,
        )

    def set_agent_model(
        self,
        agent_id: str,
        *,
        node_id: str,
        model_id: str,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/agents/{agent_id}/graph/set-agent-model",
            json_body={"node_id": node_id, "model_id": model_id},
            options=options,
            mutation=True,
        )

    def set_agent_instructions(
        self,
        agent_id: str,
        *,
        node_id: str,
        instructions: str,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/agents/{agent_id}/graph/set-agent-instructions",
            json_body={"node_id": node_id, "instructions": instructions},
            options=options,
            mutation=True,
        )

    def delete(self, agent_id: str, options: Optional[RequestOptions] = None) -> ResponseEnvelope:
        return self._client.request("DELETE", f"/agents/{agent_id}", options=options, mutation=True)

    def validate(self, agent_id: str, payload: Optional[Dict[str, Any]] = None) -> ResponseEnvelope:
        return self._client.request("POST", f"/agents/{agent_id}/validate", json_body=payload or {})

    def list_nodes_catalog(self) -> ResponseEnvelope:
        return self._client.request("GET", "/agents/nodes/catalog")

    def get_nodes_schema(self, node_types: List[str]) -> ResponseEnvelope:
        return self._client.request("POST", "/agents/nodes/schema", json_body={"node_types": list(node_types or [])})

    def validate_nodes(self, agent_id: str) -> ResponseEnvelope:
        return self._client.request("POST", f"/agents/{agent_id}/validate", json_body={})

    def publish(self, agent_id: str, options: Optional[RequestOptions] = None) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/agents/{agent_id}/publish",
            json_body={},
            options=options,
            mutation=True,
        )

    def list_versions(self, agent_id: str) -> ResponseEnvelope:
        return self._client.request("GET", f"/agents/{agent_id}/versions")

    def get_version(self, agent_id: str, version: int) -> ResponseEnvelope:
        return self._client.request("GET", f"/agents/{agent_id}/versions/{version}")

    def execute(self, agent_id: str, payload: Dict[str, Any]) -> ResponseEnvelope:
        return self._client.request("POST", f"/agents/{agent_id}/execute", json_body=payload)

    def stream(self, agent_id: str, payload: Dict[str, Any], mode: Optional[str] = None):
        params: Dict[str, Any] = {}
        if mode:
            params["mode"] = mode
        return self._client.request_raw(
            "POST",
            f"/agents/{agent_id}/stream",
            params=params,
            json_body=payload,
        )

    def start_run(self, agent_id: str, payload: Dict[str, Any]) -> ResponseEnvelope:
        return self._client.request("POST", f"/agents/{agent_id}/run", json_body=payload, mutation=True)

    def resume_run(self, run_id: str, payload: Dict[str, Any]) -> ResponseEnvelope:
        return self._client.request("POST", f"/agents/runs/{run_id}/resume", json_body=payload, mutation=True)

    def get_run(self, run_id: str, include_tree: bool = False) -> ResponseEnvelope:
        return self._client.request(
            "GET",
            f"/agents/runs/{run_id}",
            params={"include_tree": include_tree},
        )

    def get_run_tree(self, run_id: str) -> ResponseEnvelope:
        return self._client.request("GET", f"/agents/runs/{run_id}/tree")
