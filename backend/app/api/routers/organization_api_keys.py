from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.session import get_db
from app.services.organization_api_key_service import OrganizationAPIKeyNotFoundError, OrganizationAPIKeyService


router = APIRouter(prefix="/admin/organizations/api-keys", tags=["organization-api-keys"])


class CreateOrganizationAPIKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["agents.embed"])


def _serialize_api_key(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "organization_id": str(row.organization_id),
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
async def list_organization_api_keys(
    _: dict[str, Any] = Depends(require_scopes("api_keys.read")),
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if principal.get("type") != "user":
        raise HTTPException(status_code=403, detail="Only users can list organization API keys")

    organization_id = UUID(str(principal["organization_id"]))
    rows = await OrganizationAPIKeyService(db).list_api_keys(organization_id=organization_id)
    return {"items": [_serialize_api_key(row) for row in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization_api_key(
    request: CreateOrganizationAPIKeyRequest,
    _: dict[str, Any] = Depends(require_scopes("api_keys.write")),
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if principal.get("type") != "user":
        raise HTTPException(status_code=403, detail="Only users can create organization API keys")

    organization_id = UUID(str(principal["organization_id"]))
    created_by = UUID(str(principal["user_id"])) if principal.get("user_id") else None
    api_key, token = await OrganizationAPIKeyService(db).create_api_key(
        organization_id=organization_id,
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
async def delete_organization_api_key(
    key_id: UUID,
    _: dict[str, Any] = Depends(require_scopes("api_keys.write")),
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if principal.get("type") != "user":
        raise HTTPException(status_code=403, detail="Only users can delete organization API keys")

    organization_id = UUID(str(principal["organization_id"]))
    try:
        await OrganizationAPIKeyService(db).delete_api_key(organization_id=organization_id, key_id=key_id)
    except OrganizationAPIKeyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()


@router.post("/{key_id}/revoke")
async def revoke_organization_api_key(
    key_id: UUID,
    _: dict[str, Any] = Depends(require_scopes("api_keys.write")),
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if principal.get("type") != "user":
        raise HTTPException(status_code=403, detail="Only users can revoke organization API keys")

    organization_id = UUID(str(principal["organization_id"]))
    try:
        api_key = await OrganizationAPIKeyService(db).revoke_api_key(organization_id=organization_id, key_id=key_id)
    except OrganizationAPIKeyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return {"api_key": _serialize_api_key(api_key)}
