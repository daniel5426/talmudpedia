from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.session import get_db
from app.services.tenant_api_key_service import TenantAPIKeyNotFoundError, TenantAPIKeyService


router = APIRouter(prefix="/admin/security/api-keys", tags=["tenant-api-keys"])


class CreateTenantAPIKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["agents.embed"])


def _serialize_api_key(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "name": row.name,
        "key_prefix": row.key_prefix,
        "scopes": list(row.scopes or []),
        "status": row.status.value if hasattr(row.status, "value") else str(row.status),
        "created_by": str(row.created_by) if row.created_by else None,
        "created_at": row.created_at,
        "revoked_at": row.revoked_at,
        "last_used_at": row.last_used_at,
    }


@router.get("")
async def list_tenant_api_keys(
    _: dict[str, Any] = Depends(require_scopes("api_keys.read")),
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if principal.get("type") != "user":
        raise HTTPException(status_code=403, detail="Only users can list tenant API keys")

    tenant_id = UUID(str(principal["tenant_id"]))
    rows = await TenantAPIKeyService(db).list_api_keys(tenant_id=tenant_id)
    return {"items": [_serialize_api_key(row) for row in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_tenant_api_key(
    request: CreateTenantAPIKeyRequest,
    _: dict[str, Any] = Depends(require_scopes("api_keys.write")),
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if principal.get("type") != "user":
        raise HTTPException(status_code=403, detail="Only users can create tenant API keys")

    tenant_id = UUID(str(principal["tenant_id"]))
    created_by = UUID(str(principal["user_id"])) if principal.get("user_id") else None
    api_key, token = await TenantAPIKeyService(db).create_api_key(
        tenant_id=tenant_id,
        name=request.name,
        scopes=request.scopes,
        created_by=created_by,
    )
    await db.commit()
    return {
        "api_key": _serialize_api_key(api_key),
        "token": token,
        "token_type": "bearer",
    }


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant_api_key(
    key_id: UUID,
    _: dict[str, Any] = Depends(require_scopes("api_keys.write")),
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if principal.get("type") != "user":
        raise HTTPException(status_code=403, detail="Only users can delete tenant API keys")

    tenant_id = UUID(str(principal["tenant_id"]))
    try:
        await TenantAPIKeyService(db).delete_api_key(tenant_id=tenant_id, key_id=key_id)
    except TenantAPIKeyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()


@router.post("/{key_id}/revoke")
async def revoke_tenant_api_key(
    key_id: UUID,
    _: dict[str, Any] = Depends(require_scopes("api_keys.write")),
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if principal.get("type") != "user":
        raise HTTPException(status_code=403, detail="Only users can revoke tenant API keys")

    tenant_id = UUID(str(principal["tenant_id"]))
    try:
        api_key = await TenantAPIKeyService(db).revoke_api_key(tenant_id=tenant_id, key_id=key_id)
    except TenantAPIKeyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return {"api_key": _serialize_api_key(api_key)}
