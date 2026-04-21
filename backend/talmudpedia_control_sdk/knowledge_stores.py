from __future__ import annotations

from typing import Any, Dict, Optional

from .types import RequestOptions, ResponseEnvelope


def _organization_params(organization_id: Optional[str]) -> Dict[str, Any]:
    if not organization_id:
        return {}
    return {"organization_id": organization_id}


class KnowledgeStoresAPI:
    def __init__(self, client: Any) -> None:
        self._client = client

    def list(
        self,
        organization_id: str,
        *,
        skip: int = 0,
        limit: int = 20,
        view: str = "summary",
    ) -> ResponseEnvelope:
        return self._client.request(
            "GET",
            "/admin/knowledge-stores",
            params={"organization_id": organization_id, "skip": skip, "limit": limit, "view": view},
        )

    def create(
        self,
        spec: Dict[str, Any],
        organization_id: str,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/admin/knowledge-stores",
            params={"organization_id": organization_id},
            json_body=spec,
            options=options,
            mutation=True,
        )

    def get(self, store_id: str, organization_id: Optional[str] = None) -> ResponseEnvelope:
        return self._client.request(
            "GET",
            f"/admin/knowledge-stores/{store_id}",
            params=_organization_params(organization_id),
        )

    def update(
        self,
        store_id: str,
        patch: Dict[str, Any],
        organization_id: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "PATCH",
            f"/admin/knowledge-stores/{store_id}",
            params=_organization_params(organization_id),
            json_body=patch,
            options=options,
            mutation=True,
        )

    def delete(
        self,
        store_id: str,
        organization_id: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "DELETE",
            f"/admin/knowledge-stores/{store_id}",
            params=_organization_params(organization_id),
            options=options,
            mutation=True,
        )

    def stats(self, store_id: str, organization_id: Optional[str] = None) -> ResponseEnvelope:
        return self._client.request(
            "GET",
            f"/admin/knowledge-stores/{store_id}/stats",
            params=_organization_params(organization_id),
        )
