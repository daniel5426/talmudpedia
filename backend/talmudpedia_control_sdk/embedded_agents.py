from __future__ import annotations

from typing import Any, Dict, Optional

from .types import RequestOptions, ResponseEnvelope


class EmbeddedAgentsAPI:
    def __init__(self, client: Any) -> None:
        self._client = client

    def stream_agent(self, agent_id: str, payload: Dict[str, Any]):
        return self._client.request_raw(
            "POST",
            f"/public/embed/agents/{agent_id}/chat/stream",
            json_body=payload,
        )

    def list_agent_threads(
        self,
        agent_id: str,
        *,
        external_user_id: str,
        external_session_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> ResponseEnvelope:
        params: Dict[str, Any] = {
            "external_user_id": external_user_id,
            "skip": skip,
            "limit": limit,
        }
        if external_session_id:
            params["external_session_id"] = external_session_id
        return self._client.request(
            "GET",
            f"/public/embed/agents/{agent_id}/threads",
            params=params,
        )

    def get_agent_thread(
        self,
        agent_id: str,
        thread_id: str,
        *,
        external_user_id: str,
        external_session_id: Optional[str] = None,
    ) -> ResponseEnvelope:
        params: Dict[str, Any] = {
            "external_user_id": external_user_id,
        }
        if external_session_id:
            params["external_session_id"] = external_session_id
        return self._client.request(
            "GET",
            f"/public/embed/agents/{agent_id}/threads/{thread_id}",
            params=params,
        )
