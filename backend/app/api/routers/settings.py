from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update

from app.db.postgres.session import get_db
from app.api.dependencies import get_tenant_context
from app.api.routers.auth import get_current_user
from app.db.postgres.models.registry import (
    IntegrationCredential,
    IntegrationCredentialCategory,
    ToolRegistry,
    ModelRegistry,
)
from app.db.postgres.models.registry import ModelProviderBinding
from app.db.postgres.models.rag import KnowledgeStore
from app.services.credentials_service import CredentialsService
from app.services.integration_provider_catalog import is_provider_key_allowed

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================

class CredentialResponse(BaseModel):
    id: uuid.UUID
    tenant_id: Optional[uuid.UUID]
    category: IntegrationCredentialCategory
    provider_key: str
    provider_variant: Optional[str]
    display_name: str
    credential_keys: List[str]
    is_enabled: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime


class CreateCredentialRequest(BaseModel):
    category: IntegrationCredentialCategory
    provider_key: str
    provider_variant: Optional[str] = None
    display_name: str
    credentials: Dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True
    is_default: bool = True


class UpdateCredentialRequest(BaseModel):
    category: Optional[IntegrationCredentialCategory] = None
    provider_key: Optional[str] = None
    provider_variant: Optional[str] = None
    display_name: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None
    is_default: Optional[bool] = None


class CredentialStatus(BaseModel):
    id: uuid.UUID
    category: IntegrationCredentialCategory
    provider_key: str
    provider_variant: Optional[str]
    is_enabled: bool
    is_default: bool
    updated_at: datetime


class CredentialUsageModelProvider(BaseModel):
    binding_id: uuid.UUID
    model_id: uuid.UUID
    model_name: str
    provider: str
    provider_model_id: str


class CredentialUsageKnowledgeStore(BaseModel):
    store_id: uuid.UUID
    store_name: str
    backend: str


class CredentialUsageTool(BaseModel):
    tool_id: uuid.UUID
    tool_name: str
    tool_slug: str
    implementation_type: Optional[str] = None


class CredentialUsageResponse(BaseModel):
    credential_id: uuid.UUID
    model_providers: List[CredentialUsageModelProvider]
    knowledge_stores: List[CredentialUsageKnowledgeStore]
    tools: List[CredentialUsageTool]

    @property
    def total_links(self) -> int:
        return len(self.model_providers) + len(self.knowledge_stores) + len(self.tools)


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
        is_default=credential.is_default,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


def _normalize_provider_key(category: IntegrationCredentialCategory, provider_key: str) -> str:
    key = (provider_key or "").strip().lower()
    if not key:
        raise HTTPException(status_code=422, detail="provider_key is required")
    if not is_provider_key_allowed(category, key):
        raise HTTPException(status_code=422, detail=f"Unsupported provider_key '{provider_key}' for category '{category.value}'")
    return key


async def _get_credential_usage(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    credential_id: uuid.UUID,
) -> CredentialUsageResponse:
    model_rows = (
        await db.execute(
            select(
                ModelProviderBinding.id,
                ModelProviderBinding.model_id,
                ModelRegistry.name,
                ModelProviderBinding.provider,
                ModelProviderBinding.provider_model_id,
            )
            .join(ModelRegistry, ModelRegistry.id == ModelProviderBinding.model_id)
            .where(
                ModelProviderBinding.tenant_id == tenant_id,
                ModelProviderBinding.credentials_ref == credential_id,
            )
            .order_by(ModelRegistry.name.asc(), ModelProviderBinding.provider_model_id.asc())
        )
    ).all()

    store_rows = (
        await db.execute(
            select(KnowledgeStore.id, KnowledgeStore.name, KnowledgeStore.backend)
            .where(
                KnowledgeStore.tenant_id == tenant_id,
                KnowledgeStore.credentials_ref == credential_id,
            )
            .order_by(KnowledgeStore.name.asc())
        )
    ).all()

    tool_rows = (
        await db.execute(
            select(ToolRegistry.id, ToolRegistry.name, ToolRegistry.slug, ToolRegistry.implementation_type, ToolRegistry.config_schema)
            .where(ToolRegistry.tenant_id == tenant_id)
            .order_by(ToolRegistry.name.asc())
        )
    ).all()

    tool_usage: List[CredentialUsageTool] = []
    credential_id_str = str(credential_id)
    for tool_id, tool_name, tool_slug, implementation_type, config_schema in tool_rows:
        schema_dict = config_schema if isinstance(config_schema, dict) else {}
        impl = schema_dict.get("implementation")
        impl_dict = impl if isinstance(impl, dict) else {}
        linked_ref = impl_dict.get("credentials_ref")
        if str(linked_ref or "") != credential_id_str:
            continue
        tool_usage.append(
            CredentialUsageTool(
                tool_id=tool_id,
                tool_name=tool_name,
                tool_slug=tool_slug,
                implementation_type=str(getattr(implementation_type, "value", implementation_type)) if implementation_type else None,
            )
        )

    return CredentialUsageResponse(
        credential_id=credential_id,
        model_providers=[
            CredentialUsageModelProvider(
                binding_id=row[0],
                model_id=row[1],
                model_name=row[2],
                provider=str(getattr(row[3], "value", row[3])),
                provider_model_id=row[4],
            )
            for row in model_rows
        ],
        knowledge_stores=[
            CredentialUsageKnowledgeStore(
                store_id=row[0],
                store_name=row[1],
                backend=str(getattr(row[2], "value", row[2])),
            )
            for row in store_rows
        ],
        tools=tool_usage,
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
    provider_key = _normalize_provider_key(request.category, request.provider_key)
    credential = IntegrationCredential(
        tenant_id=tid,
        category=request.category,
        provider_key=provider_key,
        provider_variant=request.provider_variant,
        display_name=request.display_name,
        credentials=request.credentials or {},
        is_enabled=request.is_enabled,
        is_default=request.is_default,
    )
    db.add(credential)
    with db.no_autoflush:
        await CredentialsService(db, tid).enforce_single_default(credential)
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
        if request.provider_key is None:
            credential.provider_key = _normalize_provider_key(credential.category, credential.provider_key)
    if request.provider_key is not None:
        effective_category = request.category if request.category is not None else credential.category
        credential.provider_key = _normalize_provider_key(effective_category, request.provider_key)
    if "provider_variant" in request.model_fields_set:
        credential.provider_variant = request.provider_variant
    if request.display_name is not None:
        credential.display_name = request.display_name
    if request.credentials is not None:
        credential.credentials = request.credentials
    if request.is_enabled is not None:
        credential.is_enabled = request.is_enabled
    if request.is_default is not None:
        credential.is_default = request.is_default

    with db.no_autoflush:
        await CredentialsService(db, tid).enforce_single_default(credential)
    await db.commit()
    await db.refresh(credential)
    return _credential_to_response(credential)


@router.delete("/credentials/{credential_id}")
async def delete_credential(
    credential_id: uuid.UUID,
    force_disconnect: bool = Query(False),
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

    usage = await _get_credential_usage(db, tid, credential_id)
    if usage.total_links and not force_disconnect:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Credential is in use",
                "usage": usage.model_dump(mode="json"),
                "hint": "Re-run delete with force_disconnect=true to detach linked resources and use platform defaults.",
            },
        )

    if usage.total_links and force_disconnect:
        await db.execute(
            update(ModelProviderBinding)
            .where(
                ModelProviderBinding.tenant_id == tid,
                ModelProviderBinding.credentials_ref == credential_id,
            )
            .values(credentials_ref=None)
        )
        await db.execute(
            update(KnowledgeStore)
            .where(
                KnowledgeStore.tenant_id == tid,
                KnowledgeStore.credentials_ref == credential_id,
            )
            .values(credentials_ref=None)
        )

        tools_stmt = select(ToolRegistry).where(ToolRegistry.tenant_id == tid)
        tools = (await db.execute(tools_stmt)).scalars().all()
        credential_id_str = str(credential_id)
        for tool in tools:
            schema_dict = tool.config_schema if isinstance(tool.config_schema, dict) else {}
            impl = schema_dict.get("implementation")
            impl_dict = impl if isinstance(impl, dict) else {}
            linked_ref = impl_dict.get("credentials_ref")
            if str(linked_ref or "") != credential_id_str:
                continue
            impl_dict = dict(impl_dict)
            impl_dict.pop("credentials_ref", None)
            updated_schema = dict(schema_dict)
            updated_schema["implementation"] = impl_dict
            tool.config_schema = updated_schema

    await db.delete(credential)
    await db.commit()
    return {"status": "deleted", "id": credential_id}


@router.get("/credentials/{credential_id}/usage", response_model=CredentialUsageResponse)
async def get_credential_usage(
    credential_id: uuid.UUID,
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
    return await _get_credential_usage(db, tid, credential_id)


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
            is_default=c.is_default,
            updated_at=c.updated_at,
        )
        for c in credentials
    ]
