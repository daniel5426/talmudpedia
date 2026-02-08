from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
import uuid
import os

import jwt

from app.core.jwt_keys import current_signing_material, LocalJWKSProvider

WORKLOAD_TOKEN_USE = "workload_delegated"
WORKLOAD_ISSUER = os.getenv("WORKLOAD_JWT_ISSUER", "talmudpedia-internal")
WORKLOAD_DEFAULT_TTL_SECONDS = int(os.getenv("WORKLOAD_JWT_TTL_SECONDS", "300"))


def issue_workload_token(
    *,
    audience: str,
    tenant_id: str,
    principal_id: str,
    grant_id: str,
    initiator_user_id: str | None,
    scopes: List[str],
    run_id: str | None = None,
    expires_in_seconds: int | None = None,
) -> tuple[str, Dict[str, Any]]:
    material = current_signing_material()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=expires_in_seconds or WORKLOAD_DEFAULT_TTL_SECONDS)
    jti = str(uuid.uuid4())

    payload: Dict[str, Any] = {
        "iss": WORKLOAD_ISSUER,
        "aud": audience,
        "sub": f"wp:{principal_id}",
        "tenant_id": str(tenant_id),
        "grant_id": str(grant_id),
        "scope": list(scopes),
        "jti": jti,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "token_use": WORKLOAD_TOKEN_USE,
    }
    if initiator_user_id:
        payload["act"] = f"user:{initiator_user_id}"
    if run_id:
        payload["run_id"] = str(run_id)

    token = jwt.encode(
        payload,
        material.private_key_pem,
        algorithm=material.algorithm,
        headers={"kid": material.kid},
    )
    return token, payload


def decode_workload_token(token: str, audience: str | None = None) -> Dict[str, Any]:
    material = current_signing_material()
    options = {"require": ["exp", "iss", "sub", "tenant_id", "grant_id", "jti", "token_use"]}

    payload = jwt.decode(
        token,
        material.public_key_pem,
        algorithms=[material.algorithm],
        audience=audience,
        options=options,
        issuer=WORKLOAD_ISSUER,
    )

    if payload.get("token_use") != WORKLOAD_TOKEN_USE:
        raise jwt.InvalidTokenError("Invalid workload token_use")
    if not str(payload.get("sub", "")).startswith("wp:"):
        raise jwt.InvalidTokenError("Invalid workload subject")
    if not payload.get("scope") or not isinstance(payload.get("scope"), list):
        raise jwt.InvalidTokenError("Invalid workload scopes")

    return payload


def get_workload_jwks() -> Dict[str, Any]:
    return LocalJWKSProvider().get_jwks()
