from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal
from app.db.postgres.session import get_db
from app.db.postgres.models.security import WorkloadPrincipalType
from app.services.workload_identity_service import WorkloadIdentityService
from app.services.delegation_service import DelegationService
from app.services.token_broker_service import TokenBrokerService
from app.core.workload_jwt import get_workload_jwks


router = APIRouter(prefix="/internal/auth", tags=["internal-auth"])
jwks_router = APIRouter(tags=["internal-auth"])


class DelegationGrantCreateRequest(BaseModel):
    tenant_id: UUID
    principal_id: Optional[UUID] = None
    principal_slug: Optional[str] = None
    principal_name: Optional[str] = None
    principal_type: WorkloadPrincipalType = WorkloadPrincipalType.SYSTEM
    initiator_user_id: Optional[UUID] = None
    requested_scopes: list[str] = Field(default_factory=list)
    run_id: Optional[UUID] = None


class DelegationGrantCreateResponse(BaseModel):
    grant_id: UUID
    principal_id: UUID
    effective_scopes: list[str]
    expires_at: datetime
    approval_required: bool


class WorkloadTokenRequest(BaseModel):
    grant_id: UUID
    audience: str
    scope_subset: Optional[list[str]] = None


class WorkloadTokenResponse(BaseModel):
    token: str
    token_type: str = "Bearer"
    scope: list[str]
    expires_at: datetime


@router.post("/delegation-grants", response_model=DelegationGrantCreateResponse)
async def create_delegation_grant(
    request: DelegationGrantCreateRequest,
    principal_ctx: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    caller_tenant_id = principal_ctx.get("tenant_id")
    if str(caller_tenant_id) != str(request.tenant_id) and "*" not in set(principal_ctx.get("scopes") or []):
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    initiator_user_id = request.initiator_user_id
    if principal_ctx.get("type") == "user" and not initiator_user_id:
        initiator_user_id = UUID(principal_ctx["user_id"])

    identity = WorkloadIdentityService(db)
    if request.principal_id:
        principal = await identity.get_principal_by_id(request.principal_id)
        if principal is None:
            raise HTTPException(status_code=404, detail="Workload principal not found")
        if str(principal.tenant_id) != str(request.tenant_id):
            raise HTTPException(status_code=403, detail="Principal tenant mismatch")
    else:
        if not request.principal_slug:
            raise HTTPException(status_code=400, detail="principal_id or principal_slug is required")
        principal = await identity.ensure_principal(
            tenant_id=request.tenant_id,
            slug=request.principal_slug,
            name=request.principal_name or request.principal_slug,
            principal_type=request.principal_type,
            created_by=initiator_user_id,
            requested_scopes=request.requested_scopes,
            auto_approve_system=True,
        )

    delegation = DelegationService(db)
    grant, approval_required = await delegation.create_delegation_grant(
        tenant_id=request.tenant_id,
        principal_id=principal.id,
        initiator_user_id=initiator_user_id,
        requested_scopes=request.requested_scopes,
        run_id=request.run_id,
    )
    await db.commit()

    return DelegationGrantCreateResponse(
        grant_id=grant.id,
        principal_id=principal.id,
        effective_scopes=grant.effective_scopes or [],
        expires_at=grant.expires_at,
        approval_required=approval_required,
    )


@router.post("/workload-token", response_model=WorkloadTokenResponse)
async def mint_workload_token(
    request: WorkloadTokenRequest,
    principal_ctx: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    broker = TokenBrokerService(db)
    grant = await broker.get_grant(request.grant_id)
    if grant is None:
        raise HTTPException(status_code=404, detail="Delegation grant not found")

    caller_tenant_id = principal_ctx.get("tenant_id")
    if str(caller_tenant_id) != str(grant.tenant_id) and "*" not in set(principal_ctx.get("scopes") or []):
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    try:
        token, payload = await broker.mint_workload_token(
            grant_id=request.grant_id,
            audience=request.audience,
            scope_subset=request.scope_subset,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    await db.commit()

    return WorkloadTokenResponse(
        token=token,
        scope=payload.get("scope", []),
        expires_at=datetime.fromtimestamp(payload["exp"]),
    )


@jwks_router.get("/.well-known/jwks.json")
async def workload_jwks():
    return get_workload_jwks()
