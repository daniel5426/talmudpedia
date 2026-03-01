from __future__ import annotations

from typing import Any, Dict, Optional

from .types import RequestOptions, ResponseEnvelope


def _tenant_params(tenant_slug: Optional[str]) -> Dict[str, Any]:
    if not tenant_slug:
        return {}
    return {"tenant_slug": tenant_slug}


class KnowledgeStoresAPI:
    def __init__(self, client: Any) -> None:
        self._client = client

    def list(self, tenant_slug: str) -> ResponseEnvelope:
        return self._client.request(
            "GET",
            "/admin/knowledge-stores",
            params={"tenant_slug": tenant_slug},
        )

    def create(
        self,
        spec: Dict[str, Any],
        tenant_slug: str,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/admin/knowledge-stores",
            params={"tenant_slug": tenant_slug},
            json_body=spec,
            options=options,
            mutation=True,
        )

    def get(self, store_id: str, tenant_slug: Optional[str] = None) -> ResponseEnvelope:
        return self._client.request(
            "GET",
            f"/admin/knowledge-stores/{store_id}",
            params=_tenant_params(tenant_slug),
        )

    def update(
        self,
        store_id: str,
        patch: Dict[str, Any],
        tenant_slug: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "PATCH",
            f"/admin/knowledge-stores/{store_id}",
            params=_tenant_params(tenant_slug),
            json_body=patch,
            options=options,
            mutation=True,
        )

    def delete(
        self,
        store_id: str,
        tenant_slug: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "DELETE",
            f"/admin/knowledge-stores/{store_id}",
            params=_tenant_params(tenant_slug),
            options=options,
            mutation=True,
        )

    def stats(self, store_id: str, tenant_slug: Optional[str] = None) -> ResponseEnvelope:
        return self._client.request(
            "GET",
            f"/admin/knowledge-stores/{store_id}/stats",
            params=_tenant_params(tenant_slug),
        )
