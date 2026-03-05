from __future__ import annotations

from typing import Any, Dict, Optional

from .types import ResponseEnvelope


class WorkloadSecurityAPI:
    def __init__(self, client: Any) -> None:
        self._client = client

    def list_pending_scope_policies(self) -> ResponseEnvelope:
        return self._client.request("GET", "/admin/security/workloads/pending")

    def approve_scope_policy(self, principal_id: str, approved_scopes: list[str]) -> ResponseEnvelope:
        payload = {"approved_scopes": approved_scopes}
        return self._client.request(
            "POST",
            f"/admin/security/workloads/principals/{principal_id}/approve",
            json_body=payload,
            mutation=True,
        )

    def reject_scope_policy(self, principal_id: str) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            f"/admin/security/workloads/principals/{principal_id}/reject",
            json_body={},
            mutation=True,
        )

    def list_action_approvals(
        self,
        *,
        subject_type: Optional[str] = None,
        subject_id: Optional[str] = None,
        action_scope: Optional[str] = None,
    ) -> ResponseEnvelope:
        params: Dict[str, Any] = {}
        if subject_type:
            params["subject_type"] = subject_type
        if subject_id:
            params["subject_id"] = subject_id
        if action_scope:
            params["action_scope"] = action_scope
        return self._client.request("GET", "/admin/security/workloads/approvals", params=params)

    def decide_action_approval(self, payload: Dict[str, Any]) -> ResponseEnvelope:
        return self._client.request(
            "POST",
            "/admin/security/workloads/approvals/decide",
            json_body=payload,
            mutation=True,
        )
