from __future__ import annotations

from typing import Any, Dict, Optional

from .types import RequestOptions, ResponseEnvelope


class OrchestrationAPI:
    def __init__(self, client: Any) -> None:
        self._client = client

    def spawn_run(self, payload: Dict[str, Any], options: Optional[RequestOptions] = None) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/internal/orchestration/spawn-run",
            json_body=payload,
            options=options,
            mutation=True,
        )

    def spawn_group(self, payload: Dict[str, Any], options: Optional[RequestOptions] = None) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/internal/orchestration/spawn-group",
            json_body=payload,
            options=options,
            mutation=True,
        )

    def join(self, payload: Dict[str, Any], options: Optional[RequestOptions] = None) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/internal/orchestration/join",
            json_body=payload,
            options=options,
            mutation=True,
        )

    def cancel_subtree(self, payload: Dict[str, Any], options: Optional[RequestOptions] = None) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/internal/orchestration/cancel-subtree",
            json_body=payload,
            options=options,
            mutation=True,
        )

    def evaluate_and_replan(
        self,
        payload: Dict[str, Any],
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/internal/orchestration/evaluate-and-replan",
            json_body=payload,
            options=options,
            mutation=True,
        )

    def query_tree(self, run_id: str) -> ResponseEnvelope:
        return self._client.request("GET", f"/internal/orchestration/runs/{run_id}/tree")
