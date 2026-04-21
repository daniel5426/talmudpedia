from __future__ import annotations

from typing import Any, Dict, Optional

from .types import RequestOptions, ResponseEnvelope


def _organization_params(organization_id: Optional[str]) -> Dict[str, Any]:
    if not organization_id:
        return {}
    return {"organization_id": organization_id}


class ArtifactsAPI:
    def __init__(self, client: Any) -> None:
        self._client = client

    def list(
        self,
        organization_id: Optional[str] = None,
        *,
        skip: int = 0,
        limit: int = 20,
        view: str = "summary",
    ) -> ResponseEnvelope:
        params = _organization_params(organization_id)
        params.update({"skip": skip, "limit": limit, "view": view})
        return self._client.request("GET", "/admin/artifacts", params=params)

    def get(self, artifact_id: str, organization_id: Optional[str] = None) -> ResponseEnvelope:
        return self._client.request(
            "GET",
            f"/admin/artifacts/{artifact_id}",
            params=_organization_params(organization_id),
        )

    def create(
        self,
        spec: Dict[str, Any],
        *,
        organization_id: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/admin/artifacts",
            params=_organization_params(organization_id),
            json_body=spec,
            options=options,
            mutation=True,
        )

    def update(
        self,
        artifact_id: str,
        patch: Dict[str, Any],
        *,
        organization_id: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "PUT",
            f"/admin/artifacts/{artifact_id}",
            params=_organization_params(organization_id),
            json_body=patch,
            options=options,
            mutation=True,
        )

    def delete(
        self,
        artifact_id: str,
        *,
        organization_id: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "DELETE",
            f"/admin/artifacts/{artifact_id}",
            params=_organization_params(organization_id),
            options=options,
            mutation=True,
        )

    def convert_kind(
        self,
        artifact_id: str,
        request: Dict[str, Any],
        *,
        organization_id: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/admin/artifacts/{artifact_id}/convert-kind",
            params=_organization_params(organization_id),
            json_body=request,
            options=options,
            mutation=True,
        )

    def publish(
        self,
        artifact_id: str,
        *,
        organization_id: Optional[str] = None,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/admin/artifacts/{artifact_id}/publish",
            params=_organization_params(organization_id),
            options=options,
            mutation=True,
        )

    def create_test_run(self, request: Dict[str, Any], organization_id: Optional[str] = None) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/admin/artifacts/test-runs",
            params=_organization_params(organization_id),
            json_body=request,
        )
