from __future__ import annotations

from typing import Any, Dict

from .types import ResponseEnvelope


class AuthAPI:
    def __init__(self, client: Any) -> None:
        self._client = client

    def create_delegation_grant(self, payload: Dict[str, Any]) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/internal/auth/delegation-grants",
            json_body=payload,
            mutation=True,
        )

    def mint_workload_token(self, payload: Dict[str, Any]) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/internal/auth/workload-token",
            json_body=payload,
            mutation=True,
        )

    def get_workload_jwks(self) -> ResponseEnvelope:
        return self._client.request("GET", "/.well-known/jwks.json")
