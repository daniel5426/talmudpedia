from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update

from app.db.postgres.session import get_db
from app.api.dependencies import get_organization_context
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
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.contracts import ListQuery
from app.services.control_plane.credentials_admin_service import serialize_credential
from app.services.control_plane.credentials_admin_service import CredentialsAdminService
from app.services.control_plane.errors import ControlPlaneError

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================

class CredentialResponse(BaseModel):
    id: uuid.UUID
    organization_id: Optional[uuid.UUID]
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
    builtin_key: Optional[str] = None
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
        organization_id=credential.organization_id,
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


def _service_context(*, organization_ctx: Dict[str, Any], current_user: Any) -> ControlPlaneContext:
    return ControlPlaneContext.from_organization_context(
        {
            "organization_id": organization_ctx.get("organization_id") or organization_ctx.get("organization_id"),
            "project_id": organization_ctx.get("project_id"),
        },
        user=current_user,
        user_id=getattr(current_user, "id", None),
    )


async def _get_credential_usage(
    db: AsyncSession,
    organization_id: uuid.UUID,
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
                ModelProviderBinding.organization_id == organization_id,
                ModelProviderBinding.credentials_ref == credential_id,
            )
            .order_by(ModelRegistry.name.asc(), ModelProviderBinding.provider_model_id.asc())
        )
    ).all()

    store_rows = (
        await db.execute(
            select(KnowledgeStore.id, KnowledgeStore.name, KnowledgeStore.backend)
            .where(
                KnowledgeStore.organization_id == organization_id,
                KnowledgeStore.credentials_ref == credential_id,
            )
            .order_by(KnowledgeStore.name.asc())
        )
    ).all()

    tool_rows = (
        await db.execute(
            select(ToolRegistry.id, ToolRegistry.name, ToolRegistry.builtin_key, ToolRegistry.implementation_type, ToolRegistry.config_schema)
            .where(ToolRegistry.organization_id == organization_id)
            .order_by(ToolRegistry.name.asc())
        )
    ).all()

    tool_usage: List[CredentialUsageTool] = []
    credential_id_str = str(credential_id)
    for tool_id, tool_name, builtin_key, implementation_type, config_schema in tool_rows:
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
                builtin_key=builtin_key,
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

@router.get("/credentials", response_model=Dict[str, Any])
async def list_credentials(
    category: Optional[IntegrationCredentialCategory] = Query(None),
    skip: int = 0,
    limit: int = 20,
    view: str = "summary",
    db: AsyncSession = Depends(get_db),
    organization_ctx=Depends(get_organization_context),
    current_user=Depends(get_current_user),
):
    try:
        query = ListQuery.from_payload({"skip": skip, "limit": limit, "view": view})
        credentials = await CredentialsAdminService(db).list_credentials(
            ctx=_service_context(organization_ctx=organization_ctx, current_user=current_user),
            category=category,
        )
        sliced = credentials[query.skip: query.skip + query.limit]
        return {
            "items": [serialize_credential(c, view=query.view) for c in sliced],
            "total": len(credentials),
            "has_more": query.skip + len(sliced) < len(credentials),
            "skip": query.skip,
            "limit": query.limit,
            "view": query.view,
        }
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.post("/credentials", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_credential(
    request: CreateCredentialRequest,
    db: AsyncSession = Depends(get_db),
    organization_ctx=Depends(get_organization_context),
    current_user=Depends(get_current_user),
):
    try:
        credential = await CredentialsAdminService(db).create_credential(
            ctx=_service_context(organization_ctx=organization_ctx, current_user=current_user),
            category=request.category,
            provider_key=request.provider_key,
            provider_variant=request.provider_variant,
            display_name=request.display_name,
            credentials=request.credentials,
            is_enabled=request.is_enabled,
            is_default=request.is_default,
        )
        return _credential_to_response(credential)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.patch("/credentials/{credential_id}", response_model=CredentialResponse)
async def update_credential(
    credential_id: uuid.UUID,
    request: UpdateCredentialRequest,
    db: AsyncSession = Depends(get_db),
    organization_ctx=Depends(get_organization_context),
    current_user=Depends(get_current_user),
):
    try:
        patch = request.model_dump(exclude_unset=True)
        credential = await CredentialsAdminService(db).update_credential(
            ctx=_service_context(organization_ctx=organization_ctx, current_user=current_user),
            credential_id=credential_id,
            patch=patch,
        )
        return _credential_to_response(credential)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.delete("/credentials/{credential_id}")
async def delete_credential(
    credential_id: uuid.UUID,
    force_disconnect: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    organization_ctx=Depends(get_organization_context),
    current_user=Depends(get_current_user),
):
    tid = uuid.UUID(organization_ctx["organization_id"])

    stmt = select(IntegrationCredential).where(
        and_(IntegrationCredential.id == credential_id, IntegrationCredential.organization_id == tid)
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
                ModelProviderBinding.organization_id == tid,
                ModelProviderBinding.credentials_ref == credential_id,
            )
            .values(credentials_ref=None)
        )
        await db.execute(
            update(KnowledgeStore)
            .where(
                KnowledgeStore.organization_id == tid,
                KnowledgeStore.credentials_ref == credential_id,
            )
            .values(credentials_ref=None)
        )

        tools_stmt = select(ToolRegistry).where(ToolRegistry.organization_id == tid)
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
    organization_ctx=Depends(get_organization_context),
    current_user=Depends(get_current_user),
):
    tid = uuid.UUID(organization_ctx["organization_id"])
    stmt = select(IntegrationCredential).where(
        and_(IntegrationCredential.id == credential_id, IntegrationCredential.organization_id == tid)
    )
    res = await db.execute(stmt)
    credential = res.scalar_one_or_none()
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    return await _get_credential_usage(db, tid, credential_id)


@router.get("/credentials/status", response_model=List[CredentialStatus])
async def credentials_status(
    db: AsyncSession = Depends(get_db),
    organization_ctx=Depends(get_organization_context),
    current_user=Depends(get_current_user),
):
    tid = uuid.UUID(organization_ctx["organization_id"])
    stmt = select(IntegrationCredential).where(IntegrationCredential.organization_id == tid)
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
