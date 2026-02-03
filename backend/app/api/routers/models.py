from datetime import datetime
from typing import Optional, List
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete, func

from sqlalchemy.orm import selectinload

from app.db.postgres.models.registry import (
    ModelRegistry, 
    ModelProviderType, 
    ModelCapabilityType, 
    ModelStatus,
    ModelProviderBinding,
    ProviderConfig
)
from app.db.postgres.session import get_db
from app.api.dependencies import get_current_user, get_tenant_context

router = APIRouter(prefix="/models", tags=["models"])

# ============================================================================
# Request/Response Schemas
# ============================================================================

class CreateProviderRequest(BaseModel):
    provider: ModelProviderType
    provider_model_id: str
    priority: int = 0
    config: Optional[dict] = None

class ModelProviderSummary(BaseModel):
    id: uuid.UUID
    provider: ModelProviderType
    provider_model_id: str
    priority: int
    is_enabled: bool
    config: dict

class CreateModelRequest(BaseModel):
    name: str # Display Name
    slug: str # Unique ID
    description: Optional[str] = None
    capability_type: ModelCapabilityType = ModelCapabilityType.CHAT
    metadata: Optional[dict] = None
    default_resolution_policy: Optional[dict] = None

class UpdateModelRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ModelStatus] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    metadata: Optional[dict] = None
    default_resolution_policy: Optional[dict] = None

class ModelResponse(BaseModel):
    id: uuid.UUID
    tenant_id: Optional[uuid.UUID]
    name: str
    slug: str
    description: Optional[str]
    capability_type: ModelCapabilityType
    status: ModelStatus
    version: int
    metadata: dict
    default_resolution_policy: dict
    is_active: bool
    is_default: bool
    providers: List[ModelProviderSummary] = []
    created_at: datetime
    updated_at: datetime

class ModelListResponse(BaseModel):
    models: List[ModelResponse]
    total: int

# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=ModelListResponse)
async def list_models(
    capability_type: Optional[ModelCapabilityType] = Query(None),
    is_active: Optional[bool] = Query(default=True),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """List all logical models."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    
    stmt = select(ModelRegistry).where(
        and_(
            (ModelRegistry.tenant_id == tid) | (ModelRegistry.tenant_id == None),
            ModelRegistry.is_active == is_active if is_active is not None else True
        )
    )
    
    if capability_type:
        stmt = stmt.where(ModelRegistry.capability_type == capability_type)
        
    stmt = stmt.offset(skip).limit(limit).order_by(ModelRegistry.name.asc()).options(selectinload(ModelRegistry.providers))
    
    result = await db.execute(stmt)
    models = result.scalars().all()
    
    # Count total
    count_stmt = select(func.count(ModelRegistry.id)).where(
        (ModelRegistry.tenant_id == tid) | (ModelRegistry.tenant_id == None)
    )
    if capability_type:
        count_stmt = count_stmt.where(ModelRegistry.capability_type == capability_type)
        
    total_res = await db.execute(count_stmt)
    total = total_res.scalar()
    
    return ModelListResponse(
        models=[ModelResponse(
            id=m.id,
            tenant_id=m.tenant_id,
            name=m.name,
            slug=m.slug,
            description=m.description,
            capability_type=m.capability_type,
            status=m.status,
            version=m.version,
            metadata=m.metadata_ or {},
            default_resolution_policy=m.default_resolution_policy or {},
            is_active=m.is_active,
            is_default=m.is_default,
            created_at=m.created_at,
            updated_at=m.updated_at,
            providers=[ModelProviderSummary(
                id=p.id,
                provider=p.provider,
                provider_model_id=p.provider_model_id,
                priority=p.priority,
                is_enabled=p.is_enabled,
                config=p.config or {}
            ) for p in m.providers]
        ) for m in models],
        total=total
    )

@router.post("", response_model=ModelResponse)
async def create_model(
    request: CreateModelRequest,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Register a new logical model."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    
    # Check for existing slug in tenant
    stmt = select(ModelRegistry).where(
        and_(
            ModelRegistry.tenant_id == tid,
            ModelRegistry.slug == request.slug
        )
    )
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Model slug '{request.slug}' already exists for this tenant")

    model = ModelRegistry(
        tenant_id=tid,
        name=request.name,
        slug=request.slug,
        description=request.description,
        capability_type=request.capability_type,
        metadata_=request.metadata or {},
        default_resolution_policy=request.default_resolution_policy or {}
    )
    
    db.add(model)
    await db.commit()
    await db.refresh(model)
    
    # Re-fetch with providers
    return await get_model(model.id, db, tenant_ctx, current_user)

@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Get details for a specific model."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    
    stmt = select(ModelRegistry).where(
        and_(
            ModelRegistry.id == model_id,
            (ModelRegistry.tenant_id == tid) | (ModelRegistry.tenant_id == None)
        )
    ).options(selectinload(ModelRegistry.providers))
    
    res = await db.execute(stmt)
    model = res.scalar_one_or_none()
    
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
        
    return ModelResponse(
        id=model.id,
        tenant_id=model.tenant_id,
        name=model.name,
        slug=model.slug,
        description=model.description,
        capability_type=model.capability_type,
        status=model.status,
        version=model.version,
        metadata=model.metadata_ or {},
        default_resolution_policy=model.default_resolution_policy or {},
        is_active=model.is_active,
        is_default=model.is_default,
        created_at=model.created_at,
        updated_at=model.updated_at,
        providers=[ModelProviderSummary(
            id=p.id,
            provider=p.provider,
            provider_model_id=p.provider_model_id,
            priority=p.priority,
            is_enabled=p.is_enabled,
            config=p.config or {}
        ) for p in model.providers]
    )

@router.put("/{model_id}", response_model=ModelResponse)
async def update_model(
    model_id: uuid.UUID,
    request: UpdateModelRequest,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Update a logical model definition."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    
    stmt = select(ModelRegistry).where(
        and_(ModelRegistry.id == model_id, ModelRegistry.tenant_id == tid)
    )
    res = await db.execute(stmt)
    model = res.scalar_one_or_none()
    
    if not model:
        raise HTTPException(status_code=404, detail="Model not found or permission denied")
        
    if request.name is not None:
        model.name = request.name
    if request.description is not None:
        model.description = request.description
    if request.status is not None:
        model.status = request.status
    if request.is_active is not None:
        model.is_active = request.is_active
    if request.is_default is not None:
        model.is_default = request.is_default
    if request.metadata is not None:
        model.metadata_ = request.metadata
    if request.default_resolution_policy is not None:
        model.default_resolution_policy = request.default_resolution_policy
        
    await db.commit()
    return await get_model(model.id, db, tenant_ctx, current_user)

@router.delete("/{model_id}")
async def delete_model(
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Remove a model from the registry."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    
    stmt = select(ModelRegistry).where(
        and_(ModelRegistry.id == model_id, ModelRegistry.tenant_id == tid)
    )
    res = await db.execute(stmt)
    model = res.scalar_one_or_none()
    
    if not model:
        raise HTTPException(status_code=404, detail="Model not found or permission denied")
        
    await db.delete(model)
    await db.commit()
    
    return {"status": "deleted", "id": model_id}

# --- Provider Binding Endpoints ---

@router.post("/{model_id}/providers", response_model=ModelProviderSummary)
async def add_provider_binding(
    model_id: uuid.UUID,
    request: CreateProviderRequest,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Add a provider binding to a logical model."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    
    # Verify model exists and belongs to tenant
    stmt = select(ModelRegistry).where(
        and_(ModelRegistry.id == model_id, ModelRegistry.tenant_id == tid)
    )
    res = await db.execute(stmt)
    model = res.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
        
    binding = ModelProviderBinding(
        model_id=model_id,
        tenant_id=tid,
        provider=request.provider,
        provider_model_id=request.provider_model_id,
        priority=request.priority,
        config=request.config or {}
    )
    
    db.add(binding)
    await db.commit()
    await db.refresh(binding)
    
    return ModelProviderSummary(
        id=binding.id,
        provider=binding.provider,
        provider_model_id=binding.provider_model_id,
        priority=binding.priority,
        is_enabled=binding.is_enabled,
        config=binding.config or {}
    )

@router.delete("/{model_id}/providers/{provider_id}")
async def remove_provider_binding(
    model_id: uuid.UUID,
    provider_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Remove a provider binding."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    
    stmt = select(ModelProviderBinding).where(
        and_(
            ModelProviderBinding.id == provider_id,
            ModelProviderBinding.model_id == model_id,
            ModelProviderBinding.tenant_id == tid
        )
    )
    res = await db.execute(stmt)
    binding = res.scalar_one_or_none()
    
    if not binding:
        raise HTTPException(status_code=404, detail="Provider binding not found")
        
    await db.delete(binding)
    await db.commit()
    
    return {"status": "deleted"}


# ============================================================================
# Provider Config Endpoints
# ============================================================================

class ProviderConfigResponse(BaseModel):
    id: uuid.UUID
    provider: ModelProviderType
    provider_variant: Optional[str]
    is_enabled: bool
    source: str # "tenant" or "global"
    updated_at: datetime

class CreateProviderConfigRequest(BaseModel):
    provider: ModelProviderType
    provider_variant: Optional[str] = None
    credentials: dict = Field(..., description="API Keys, Base URL, etc.")
    is_enabled: bool = True

class ProviderStatus(BaseModel):
    provider: ModelProviderType
    provider_variant: Optional[str]
    is_configured: bool
    source: Optional[str] # tenant | global
    is_enabled: bool

@router.post("/providers", response_model=ProviderConfigResponse)
async def configure_provider(
    request: CreateProviderConfigRequest,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Set credentials for a provider."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    
    # Check if exists
    stmt = select(ProviderConfig).where(
        ProviderConfig.tenant_id == tid,
        ProviderConfig.provider == request.provider,
        ProviderConfig.provider_variant == request.provider_variant
    )
    res = await db.execute(stmt)
    config = res.scalar_one_or_none()
    
    if config:
        # Update
        config.credentials = request.credentials
        config.is_enabled = request.is_enabled
    else:
        # Create
        config = ProviderConfig(
            tenant_id=tid,
            provider=request.provider,
            provider_variant=request.provider_variant,
            credentials=request.credentials,
            is_enabled=request.is_enabled
        )
        db.add(config)
        
    await db.commit()
    await db.refresh(config)
    
    return ProviderConfigResponse(
        id=config.id,
        provider=config.provider,
        provider_variant=config.provider_variant,
        is_enabled=config.is_enabled,
        source="tenant",
        updated_at=config.updated_at
    )

@router.get("/providers", response_model=List[ProviderConfigResponse])
async def list_configured_providers(
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """List configured providers (masked)."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    
    # Get Tenant Configs
    stmt = select(ProviderConfig).where(ProviderConfig.tenant_id == tid)
    res = await db.execute(stmt)
    tenant_configs = res.scalars().all()
    
    # We could also show global configs that are available?
    # For now, let's just show what the tenant has configured.
    
    return [
        ProviderConfigResponse(
            id=c.id,
            provider=c.provider,
            provider_variant=c.provider_variant,
            is_enabled=c.is_enabled,
            source="tenant",
            updated_at=c.updated_at
        ) for c in tenant_configs
    ]

@router.get("/providers/status", response_model=List[ProviderStatus])
async def get_provider_status(
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Check status of all known providers (Tenant > Global)."""
    tid = uuid.UUID(tenant_ctx["tenant_id"])
    
    # List of all relevant provider types/variants could be hardcoded or distinct from DB
    # For now, distinct from DB is safer.
    
    # 1. Fetch all tenant configs
    t_stmt = select(ProviderConfig).where(ProviderConfig.tenant_id == tid)
    t_res = await db.execute(t_stmt)
    t_configs = t_res.scalars().all()
    
    # 2. Fetch all global configs
    g_stmt = select(ProviderConfig).where(ProviderConfig.tenant_id == None)
    g_res = await db.execute(g_stmt)
    g_configs = g_res.scalars().all()
    
    # Map (provider, variant) -> Config
    status_map = {}
    
    # Process Global First
    for c in g_configs:
        key = (c.provider, c.provider_variant)
        status_map[key] = ProviderStatus(
            provider=c.provider,
            provider_variant=c.provider_variant,
            is_configured=True,
            source="global",
            is_enabled=c.is_enabled
        )
        
    # Override with Tenant
    for c in t_configs:
        key = (c.provider, c.provider_variant)
        status_map[key] = ProviderStatus(
            provider=c.provider,
            provider_variant=c.provider_variant,
            is_configured=True,
            source="tenant",
            is_enabled=c.is_enabled
        )
        
    return list(status_map.values())
