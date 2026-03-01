from __future__ import annotations

from typing import Any, Dict, Optional

from .types import RequestOptions, ResponseEnvelope


class ToolsAPI:
    def __init__(self, client: Any) -> None:
        self._client = client

    def list(
        self,
        *,
        scope: Optional[str] = None,
        is_active: Optional[bool] = None,
        status: Optional[str] = None,
        implementation_type: Optional[str] = None,
        tool_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> ResponseEnvelope:
        params: Dict[str, Any] = {"skip": skip, "limit": limit}
        if scope is not None:
            params["scope"] = scope
        if is_active is not None:
            params["is_active"] = is_active
        if status is not None:
            params["status"] = status
        if implementation_type is not None:
            params["implementation_type"] = implementation_type
        if tool_type is not None:
            params["tool_type"] = tool_type
        return self._client.request("GET", "/tools", params=params)

    def list_builtin_catalog(self, *, skip: int = 0, limit: int = 100) -> ResponseEnvelope:
        return self._client.request(
            "GET",
            "/tools/builtins/templates",
            params={"skip": skip, "limit": limit},
        )

    def create(self, spec: Dict[str, Any], options: Optional[RequestOptions] = None) -> ResponseEnvelope:
        return self._client.request("POST", "/tools", json_body=spec, options=options, mutation=True)

    def get(self, tool_id: str) -> ResponseEnvelope:
        return self._client.request("GET", f"/tools/{tool_id}")

    def update(
        self,
        tool_id: str,
        patch: Dict[str, Any],
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "PUT",
            f"/tools/{tool_id}",
            json_body=patch,
            options=options,
            mutation=True,
        )

    def publish(self, tool_id: str, options: Optional[RequestOptions] = None) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/tools/{tool_id}/publish",
            json_body={},
            options=options,
            mutation=True,
        )

    def create_version(
        self,
        tool_id: str,
        new_version: str,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/tools/{tool_id}/version",
            params={"new_version": new_version},
            json_body={},
            options=options,
            mutation=True,
        )

    def delete(self, tool_id: str, options: Optional[RequestOptions] = None) -> ResponseEnvelope:
        return self._client.request("DELETE", f"/tools/{tool_id}", options=options, mutation=True)
