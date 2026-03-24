from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.session import get_db
from app.services.artifact_runtime.outbound_auth_service import (
    ArtifactOutboundAuthError,
    resolve_injected_headers,
)


router = APIRouter(prefix="/internal/artifact-runtime", tags=["artifact-runtime-internal"])


class ArtifactOutboundAuthRequest(BaseModel):
    grant: str = Field(min_length=1)
    credential_id: str = Field(min_length=1)
    url: str = Field(min_length=1)


class ArtifactOutboundAuthResponse(BaseModel):
    inject_headers: dict[str, str]


def _expected_internal_secret() -> str:
    return (
        str(os.getenv("ARTIFACT_RUNTIME_SHARED_SECRET") or "").strip()
        or str(os.getenv("ARTIFACT_CF_DISPATCH_TOKEN") or "").strip()
    )


async def require_internal_secret(
    authorization: str | None = Header(None),
) -> None:
    expected = _expected_internal_secret()
    provided = str(authorization or "").strip()
    if not expected or provided != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Unauthorized internal runtime request")


@router.post("/outbound-auth", response_model=ArtifactOutboundAuthResponse)
async def resolve_artifact_outbound_auth(
    request: ArtifactOutboundAuthRequest,
    _: None = Depends(require_internal_secret),
    db: AsyncSession = Depends(get_db),
):
    try:
        inject_headers = await resolve_injected_headers(
            db=db,
            grant=request.grant,
            credential_id=request.credential_id,
            url=request.url,
        )
    except ArtifactOutboundAuthError as exc:
        raise HTTPException(status_code=403, detail={"code": "ARTIFACT_OUTBOUND_DENIED", "message": str(exc)}) from exc
    return ArtifactOutboundAuthResponse(inject_headers=inject_headers)
