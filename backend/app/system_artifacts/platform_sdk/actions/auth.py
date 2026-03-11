from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sdk import Client
from talmudpedia_control_sdk import ControlPlaneSDKError

from .shared import control_client


def create_delegation_grant(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    grant_payload = payload.get("grant") if isinstance(payload.get("grant"), dict) else payload.get("payload")
    if not isinstance(grant_payload, dict):
        grant_payload = payload

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.auth.create_delegation_grant(grant_payload)
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "create_delegation_grant_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "create_delegation_grant_failed", "detail": str(exc)}]


def mint_workload_token(
    client: Client,
    payload: Dict[str, Any],
    *,
    control_client_factory=control_client,
) -> Tuple[Optional[Any], List[Dict[str, Any]]]:
    token_payload = payload.get("token_request") if isinstance(payload.get("token_request"), dict) else payload.get("payload")
    if not isinstance(token_payload, dict):
        token_payload = payload

    try:
        sdk_client = control_client_factory(client)
        response = sdk_client.auth.mint_workload_token(token_payload)
        return response.get("data"), []
    except ControlPlaneSDKError as exc:
        return None, [{"error": "mint_workload_token_failed", "detail": str(exc), "code": exc.code, "http_status": exc.http_status}]
    except Exception as exc:
        return None, [{"error": "mint_workload_token_failed", "detail": str(exc)}]
