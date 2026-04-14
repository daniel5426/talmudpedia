from __future__ import annotations

from typing import Any, Dict, Optional

from .types import RequestOptions, ResponseEnvelope


class CredentialsAPI:
    def __init__(self, client: Any) -> None:
        self._client = client

    def list(
        self,
        category: Optional[str] = None,
        *,
        skip: int = 0,
        limit: int = 20,
        view: str = "summary",
    ) -> ResponseEnvelope:
        params: Dict[str, Any] = {"skip": skip, "limit": limit, "view": view}
        if category:
            params["category"] = category
        return self._client.request("GET", "/admin/settings/credentials", params=params)

    def create(self, spec: Dict[str, Any], options: Optional[RequestOptions] = None) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/admin/settings/credentials",
            json_body=spec,
            options=options,
            mutation=True,
        )

    def update(
        self,
        credential_id: str,
        patch: Dict[str, Any],
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "PATCH",
            f"/admin/settings/credentials/{credential_id}",
            json_body=patch,
            options=options,
            mutation=True,
        )

    def delete(
        self,
        credential_id: str,
        *,
        force_disconnect: bool = False,
        options: Optional[RequestOptions] = None,
    ) -> ResponseEnvelope:
        return self._client.request(
            "DELETE",
            f"/admin/settings/credentials/{credential_id}",
            params={"force_disconnect": force_disconnect},
            options=options,
            mutation=True,
        )

    def usage(self, credential_id: str) -> ResponseEnvelope:
        return self._client.request("GET", f"/admin/settings/credentials/{credential_id}/usage")

    def status(self) -> ResponseEnvelope:
        return self._client.request("GET", "/admin/settings/credentials/status")
