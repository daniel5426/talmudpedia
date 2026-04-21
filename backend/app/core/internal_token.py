from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import os
import jwt


SERVICE_TOKEN_ROLE = "platform-service"
SERVICE_TOKEN_TTL_MINUTES = 5
SERVICE_TOKEN_ALGORITHM = "HS256"


def _get_service_secret() -> str:
    secret = os.getenv("PLATFORM_SERVICE_SECRET")
    if not secret:
        raise ValueError("PLATFORM_SERVICE_SECRET is not set")
    return secret


def create_service_token(
    organization_id: str,
    subject: str = SERVICE_TOKEN_ROLE,
    expires_delta: Optional[timedelta] = None,
) -> str:
    if not organization_id:
        raise ValueError("organization_id is required for service tokens")

    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=SERVICE_TOKEN_TTL_MINUTES))
    payload: Dict[str, Any] = {
        "exp": expire,
        "sub": str(subject),
        "role": SERVICE_TOKEN_ROLE,
        "organization_id": str(organization_id),
    }
    return jwt.encode(payload, _get_service_secret(), algorithm=SERVICE_TOKEN_ALGORITHM)


def decode_service_token(token: str) -> Dict[str, Any]:
    payload = jwt.decode(token, _get_service_secret(), algorithms=[SERVICE_TOKEN_ALGORITHM])
    if payload.get("role") != SERVICE_TOKEN_ROLE:
        raise jwt.InvalidTokenError("Invalid service token role")
    if not payload.get("organization_id"):
        raise jwt.InvalidTokenError("Service token missing organization_id")
    return payload
