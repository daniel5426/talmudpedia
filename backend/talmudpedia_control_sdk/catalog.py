from __future__ import annotations

from typing import Any, Dict, Optional

from .types import ResponseEnvelope


class CatalogAPI:
    def __init__(self, client: Any) -> None:
        self._client = client

    def get_rag_operator_catalog(self, tenant_slug: Optional[str] = None) -> ResponseEnvelope:
        params: Dict[str, Any] = {}
        if tenant_slug:
            params["tenant_slug"] = tenant_slug
        return self._client.request("GET", "/admin/pipelines/catalog", params=params)

    def get_rag_operator(self, operator_id: str, tenant_slug: Optional[str] = None) -> ResponseEnvelope:
        params: Dict[str, Any] = {}
        if tenant_slug:
            params["tenant_slug"] = tenant_slug
        return self._client.request(
            "GET",
            f"/admin/pipelines/operators/{operator_id}",
            params=params,
        )

    def list_rag_operators(self, tenant_slug: Optional[str] = None) -> ResponseEnvelope:
        params: Dict[str, Any] = {}
        if tenant_slug:
            params["tenant_slug"] = tenant_slug
        return self._client.request("GET", "/admin/pipelines/operators", params=params)

    def list_agent_operators(self) -> ResponseEnvelope:
        return self._client.request("GET", "/agents/operators")
