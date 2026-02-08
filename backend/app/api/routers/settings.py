from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.db.postgres.session import get_db
from app.api.dependencies import get_tenant_context
from app.api.routers.auth import get_current_user
from app.db.postgres.models.registry import IntegrationCredential, IntegrationCredentialCategory
from app.db.postgres.models.registry import ModelProviderBinding
from app.db.postgres.models.rag import KnowledgeStore

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================

class CredentialResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    category: IntegrationCredentialCategory
    provider_key: str
    provider_variant: Optional[str]
    display_name: str
    credential_keys: List[str]
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class CreateCredentialRequest(BaseModel):
    category: IntegrationCredentialCategory
    provider_key: str
    provider_variant: Optional[str] = None
    display_name: str
    credentials: Dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True


class UpdateCredentialRequest(BaseModel):
    category: Optional[IntegrationCredentialCategory] = None
    provider_key: Optional[str] = None
    provider_variant: Optional[str] = None
    display_name: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None


class CredentialStatus(BaseModel):
    id: uuid.UUID
    category: IntegrationCredentialCategory
    provider_key: str
    provider_variant: Optional[str]
    is_enabled: bool
    updated_at: datetime


# =============================================================================
# Helpers
# =============================================================================

def _credential_to_response(credential: IntegrationCredential) -> CredentialResponse:
    keys = list((credential.credentials or {}).keys())
    return CredentialResponse(
        id=credential.id,
        tenant_id=credential.tenant_id,
        category=credential.category,
        provider_key=credential.provider_key,
        provider_variant=credential.provider_variant,
        display_name=credential.display_name,
        credential_keys=keys,
        is_enabled=credential.is_enabled,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/credentials", response_model=List[CredentialResponse])
async def list_credentials(
    category: Optional[IntegrationCredentialCategory] = Query(None),
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    stmt = select(IntegrationCredential).where(IntegrationCredential.tenant_id == tid)
    if category:
        stmt = stmt.where(IntegrationCredential.category == category)
    stmt = stmt.order_by(IntegrationCredential.provider_key.asc(), IntegrationCredential.display_name.asc())
    res = await db.execute(stmt)
    credentials = res.scalars().all()
    return [_credential_to_response(c) for c in credentials]


@router.post("/credentials", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_credential(
    request: CreateCredentialRequest,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    credential = IntegrationCredential(
        tenant_id=tid,
        category=request.category,
        provider_key=request.provider_key,
        provider_variant=request.provider_variant,
        display_name=request.display_name,
        credentials=request.credentials or {},
        is_enabled=request.is_enabled,
    )
    db.add(credential)
    await db.commit()
    await db.refresh(credential)
    return _credential_to_response(credential)


@router.patch("/credentials/{credential_id}", response_model=CredentialResponse)
async def update_credential(
    credential_id: uuid.UUID,
    request: UpdateCredentialRequest,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    stmt = select(IntegrationCredential).where(
        and_(IntegrationCredential.id == credential_id, IntegrationCredential.tenant_id == tid)
    )
    res = await db.execute(stmt)
    credential = res.scalar_one_or_none()
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")

    if request.category is not None:
        credential.category = request.category
    if request.provider_key is not None:
        credential.provider_key = request.provider_key
    if "provider_variant" in request.model_fields_set:
        credential.provider_variant = request.provider_variant
    if request.display_name is not None:
        credential.display_name = request.display_name
    if request.credentials is not None:
        credential.credentials = request.credentials
    if request.is_enabled is not None:
        credential.is_enabled = request.is_enabled

    await db.commit()
    await db.refresh(credential)
    return _credential_to_response(credential)


@router.delete("/credentials/{credential_id}")
async def delete_credential(
    credential_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    tid = uuid.UUID(tenant_ctx["tenant_id"])

    # Block delete if referenced
    binding_stmt = select(func.count(ModelProviderBinding.id)).where(
        ModelProviderBinding.tenant_id == tid,
        ModelProviderBinding.credentials_ref == credential_id,
    )
    binding_count = (await db.execute(binding_stmt)).scalar() or 0

    store_stmt = select(func.count(KnowledgeStore.id)).where(
        KnowledgeStore.tenant_id == tid,
        KnowledgeStore.credentials_ref == credential_id,
    )
    store_count = (await db.execute(store_stmt)).scalar() or 0

    if binding_count or store_count:
        raise HTTPException(
            status_code=409,
            detail="Credential is in use by models or knowledge stores",
        )

    stmt = select(IntegrationCredential).where(
        and_(IntegrationCredential.id == credential_id, IntegrationCredential.tenant_id == tid)
    )
    res = await db.execute(stmt)
    credential = res.scalar_one_or_none()
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")

    await db.delete(credential)
    await db.commit()
    return {"status": "deleted", "id": credential_id}


@router.get("/credentials/status", response_model=List[CredentialStatus])
async def credentials_status(
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    stmt = select(IntegrationCredential).where(IntegrationCredential.tenant_id == tid)
    res = await db.execute(stmt)
    credentials = res.scalars().all()
    return [
        CredentialStatus(
            id=c.id,
            category=c.category,
            provider_key=c.provider_key,
            provider_variant=c.provider_variant,
            is_enabled=c.is_enabled,
            updated_at=c.updated_at,
        )
        for c in credentials
    ]
