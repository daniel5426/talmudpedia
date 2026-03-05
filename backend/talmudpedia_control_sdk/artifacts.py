from __future__ import annotations

from typing import Any, Dict, Optional

from .types import RequestOptions, ResponseEnvelope


def _tenant_params(tenant_slug: Optional[str]) -> Dict[str, Any]:
    if not tenant_slug:
        return {}
    return {"tenant_slug": tenant_slug}


class ArtifactsAPI:
    def __init__(self, client: Any) -> None:
        self._client = client

    def list(self, tenant_slug: Optional[str] = None) -> ResponseEnvelope:
        return self._client.request("GET", "/admin/artifacts", params=_tenant_params(tenant_slug))

    def get(self, artifact_id: str, tenant_slug: Optional[str] = None) -> ResponseEnvelope:
        return self._client.request(
            "GET",
            f"/admin/artifacts/{artifact_id}",
            params=_tenant_params(tenant_slug),
        )

    def create_draft(
        self,
        spec: Dict[str, Any],
        *,
        tenant_slug: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/admin/artifacts",
            params=_tenant_params(tenant_slug),
            json_body=spec,
            options=options,
            mutation=True,
        )

    def update_draft(
        self,
        artifact_id: str,
        patch: Dict[str, Any],
        *,
        tenant_slug: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "PUT",
            f"/admin/artifacts/{artifact_id}",
            params=_tenant_params(tenant_slug),
            json_body=patch,
            options=options,
            mutation=True,
        )

    def delete(
        self,
        artifact_id: str,
        *,
        tenant_slug: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "DELETE",
            f"/admin/artifacts/{artifact_id}",
            params=_tenant_params(tenant_slug),
            options=options,
            mutation=True,
        )

    def promote(
        self,
        artifact_id: str,
        *,
        namespace: str,
        version: Optional[str] = None,
        tenant_slug: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        payload: Dict[str, Any] = {"namespace": namespace}
        if version:
            payload["version"] = version
        return self._client.request(
            "POST",
            f"/admin/artifacts/{artifact_id}/promote",
            params=_tenant_params(tenant_slug),
            json_body=payload,
            options=options,
            mutation=True,
        )

    def test(self, request: Dict[str, Any], tenant_slug: Optional[str] = None) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/admin/artifacts/test",
            params=_tenant_params(tenant_slug),
            json_body=request,
        )
