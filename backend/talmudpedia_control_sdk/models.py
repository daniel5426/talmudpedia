from __future__ import annotations

from typing import Any, Dict, Optional

from .types import RequestOptions, ResponseEnvelope


class ModelsAPI:
    def __init__(self, client: Any) -> None:
        self._client = client

    def list(
        self,
        *,
        capability_type: Optional[str] = None,
        is_active: Optional[bool] = True,
        skip: int = 0,
        limit: int = 20,
        view: str = "summary",
    ) -> ResponseEnvelope:
        params: Dict[str, Any] = {"skip": skip, "limit": limit, "view": view}
        if capability_type is not None:
            params["capability_type"] = capability_type
        if is_active is not None:
            params["is_active"] = is_active
        return self._client.request("GET", "/models", params=params)

    def create(self, spec: Dict[str, Any], options: Optional[RequestOptions] = None) -> ResponseEnvelope:
        return self._client.request("POST", "/models", json_body=spec, options=options, mutation=True)

    def get(self, model_id: str) -> ResponseEnvelope:
        return self._client.request("GET", f"/models/{model_id}")

    def update(
        self,
        model_id: str,
        patch: Dict[str, Any],
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "PUT",
            f"/models/{model_id}",
            json_body=patch,
            options=options,
            mutation=True,
        )

    def delete(self, model_id: str, options: Optional[RequestOptions] = None) -> ResponseEnvelope:
        return self._client.request("DELETE", f"/models/{model_id}", options=options, mutation=True)

    def add_provider(
        self,
        model_id: str,
        spec: Dict[str, Any],
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/models/{model_id}/providers",
            json_body=spec,
            options=options,
            mutation=True,
        )

    def update_provider(
        self,
        model_id: str,
        provider_id: str,
        patch: Dict[str, Any],
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "PATCH",
            f"/models/{model_id}/providers/{provider_id}",
            json_body=patch,
            options=options,
            mutation=True,
        )

    def delete_provider(
        self,
        model_id: str,
        provider_id: str,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "DELETE",
            f"/models/{model_id}/providers/{provider_id}",
            options=options,
            mutation=True,
        )
