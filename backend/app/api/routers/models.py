from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import String, and_, cast, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_current_principal, get_tenant_context, require_scopes
from app.db.postgres.models.registry import (
    ModelCapabilityType,
    ModelProviderBinding,
    ModelProviderType,
    ModelRegistry,
    ModelStatus,
)
from app.db.postgres.session import get_db
from app.services.integration_provider_catalog import is_model_provider_supported

router = APIRouter(prefix="/models", tags=["models"])


class CreateProviderRequest(BaseModel):
    provider: ModelProviderType
    provider_model_id: str
    priority: int = 0
    config: dict | None = None
    credentials_ref: uuid.UUID | None = None


class UpdateProviderRequest(BaseModel):
    provider_model_id: str | None = None
    priority: int | None = None
    is_enabled: bool | None = None
    config: dict | None = None
    credentials_ref: uuid.UUID | None = None


class ModelProviderSummary(BaseModel):
    id: uuid.UUID
    provider: ModelProviderType
    provider_model_id: str
    priority: int
    is_enabled: bool
    config: dict
    credentials_ref: uuid.UUID | None = None


class CreateModelRequest(BaseModel):
    name: str
    description: str | None = None
    capability_type: ModelCapabilityType = ModelCapabilityType.CHAT
    metadata: dict | None = None
    default_resolution_policy: dict | None = None
    is_default: bool = False
    is_active: bool = True
    status: ModelStatus = ModelStatus.ACTIVE


class UpdateModelRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: ModelStatus | None = None
    is_active: bool | None = None
    is_default: bool | None = None
    metadata: dict | None = None
    default_resolution_policy: dict | None = None


class ModelResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    name: str
    description: str | None
    capability_type: ModelCapabilityType
    status: ModelStatus
    version: int
    metadata: dict
    default_resolution_policy: dict
    is_active: bool
    is_default: bool
    providers: list[ModelProviderSummary] = []
    created_at: datetime
    updated_at: datetime


class ModelListResponse(BaseModel):
    models: list[ModelResponse]
    total: int


def _serialize_provider(binding: ModelProviderBinding) -> ModelProviderSummary:
    return ModelProviderSummary(
        id=binding.id,
        provider=binding.provider,
        provider_model_id=binding.provider_model_id,
        priority=binding.priority,
        is_enabled=binding.is_enabled,
        config=binding.config or {},
        credentials_ref=binding.credentials_ref,
    )


def _serialize_model(model: ModelRegistry) -> ModelResponse:
    return ModelResponse(
        id=model.id,
        tenant_id=model.tenant_id,
        name=model.name,
        description=model.description,
        capability_type=model.capability_type,
        status=model.status,
        version=model.version,
        metadata=model.metadata_ or {},
        default_resolution_policy=model.default_resolution_policy or {},
        is_active=model.is_active,
        is_default=model.is_default,
        providers=[_serialize_provider(binding) for binding in model.providers],
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _model_scope_clause(tenant_id: uuid.UUID):
    return or_(ModelRegistry.tenant_id == tenant_id, ModelRegistry.tenant_id.is_(None))


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value)).strip().lower()


def _enum_filter(column, value):
    if value is None:
        return None
    enum_str = str(value)
    value_str = str(getattr(value, "value", value))
    name_str = str(getattr(value, "name", value))
    lowered = value_str.lower()
    return or_(
        column == value,
        cast(column, String) == enum_str,
        cast(column, String) == value_str,
        cast(column, String) == name_str,
        func.lower(cast(column, String)) == lowered,
    )


def _model_filters(
    *,
    tenant_id: uuid.UUID,
    capability_type: ModelCapabilityType | None,
    status: ModelStatus | None,
    is_active: bool | None,
):
    filters: list[Any] = [_model_scope_clause(tenant_id)]
    if capability_type is not None:
        filters.append(_enum_filter(ModelRegistry.capability_type, capability_type))
    if status is not None:
        filters.append(_enum_filter(ModelRegistry.status, status))
    if is_active is not None:
        filters.append(ModelRegistry.is_active == is_active)
    return filters


async def _get_tenant_owned_model(
    *,
    db: AsyncSession,
    model_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> ModelRegistry | None:
    result = await db.execute(
        select(ModelRegistry)
        .where(and_(ModelRegistry.id == model_id, ModelRegistry.tenant_id == tenant_id))
        .options(selectinload(ModelRegistry.providers))
    )
    return result.scalar_one_or_none()


async def _apply_default_invariant(
    *,
    db: AsyncSession,
    tenant_id: uuid.UUID | None,
    capability_type: ModelCapabilityType,
    selected_model_id: uuid.UUID,
) -> None:
    await db.execute(
        update(ModelRegistry)
        .where(
            ModelRegistry.id != selected_model_id,
            ModelRegistry.capability_type == capability_type,
            (
                ModelRegistry.tenant_id == tenant_id
                if tenant_id is not None
                else ModelRegistry.tenant_id.is_(None)
            ),
            ModelRegistry.is_default.is_(True),
        )
        .values(is_default=False)
    )


def _validate_default_state(
    *,
    is_default: bool,
    is_active: bool,
    status: ModelStatus,
) -> None:
    if is_default and (not is_active or status == ModelStatus.DISABLED):
        raise HTTPException(
            status_code=400,
            detail="Default models must remain active and cannot be disabled",
        )


def _validate_provider_support(
    *,
    provider: ModelProviderType,
    capability_type: ModelCapabilityType,
) -> None:
    if not is_model_provider_supported(provider=provider, capability=capability_type):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Provider '{provider.value}' is not supported for "
                f"capability '{capability_type.value}'"
            ),
        )


@router.get("", response_model=ModelListResponse)
async def list_models(
    capability_type: ModelCapabilityType | None = Query(None),
    status: ModelStatus | None = Query(None),
    is_active: bool | None = Query(default=True),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    _: dict[str, Any] = Depends(require_scopes("models.read")),
    principal: dict[str, Any] = Depends(get_current_principal),
):
    del principal
    tenant_id = uuid.UUID(tenant_ctx["tenant_id"])
    result = await db.execute(
        select(ModelRegistry)
        .where(_model_scope_clause(tenant_id))
        .options(selectinload(ModelRegistry.providers))
        .order_by(ModelRegistry.name.asc())
    )
    scoped_models = result.scalars().all()
    filtered_models = [
        model
        for model in scoped_models
        if (
            capability_type is None
            or _enum_value(model.capability_type) == _enum_value(capability_type)
        )
        and (
            status is None
            or _enum_value(model.status) == _enum_value(status)
        )
        and (
            is_active is None
            or bool(model.is_active) is is_active
        )
    ]
    models = filtered_models[skip : skip + limit]
    total = len(filtered_models)

    return ModelListResponse(
        models=[_serialize_model(model) for model in models],
        total=total,
    )


@router.post("", response_model=ModelResponse)
async def create_model(
    request: CreateModelRequest,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    _: dict[str, Any] = Depends(require_scopes("models.write")),
    principal: dict[str, Any] = Depends(get_current_principal),
):
    del principal
    tenant_id = uuid.UUID(tenant_ctx["tenant_id"])
    _validate_default_state(
        is_default=request.is_default,
        is_active=request.is_active,
        status=request.status,
    )

    model = ModelRegistry(
        tenant_id=tenant_id,
        name=request.name.strip(),
        description=request.description,
        capability_type=request.capability_type,
        status=request.status,
        metadata_=request.metadata or {},
        default_resolution_policy=request.default_resolution_policy or {},
        is_active=request.is_active,
        is_default=False,
    )
    db.add(model)
    await db.flush()

    if request.is_default:
        await _apply_default_invariant(
            db=db,
            tenant_id=tenant_id,
            capability_type=model.capability_type,
            selected_model_id=model.id,
        )
        model.is_default = True

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Model registry invariant violation") from exc

    stored = await _get_model_response_record(db=db, model_id=model.id, tenant_id=tenant_id)
    return _serialize_model(stored)


async def _get_model_response_record(
    *,
    db: AsyncSession,
    model_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> ModelRegistry:
    result = await db.execute(
        select(ModelRegistry)
        .where(and_(ModelRegistry.id == model_id, _model_scope_clause(tenant_id)))
        .options(selectinload(ModelRegistry.providers))
    )
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    _: dict[str, Any] = Depends(require_scopes("models.read")),
    principal: dict[str, Any] = Depends(get_current_principal),
):
    del principal
    tenant_id = uuid.UUID(tenant_ctx["tenant_id"])
    model = await _get_model_response_record(db=db, model_id=model_id, tenant_id=tenant_id)
    return _serialize_model(model)


@router.put("/{model_id}", response_model=ModelResponse)
async def update_model(
    model_id: uuid.UUID,
    request: UpdateModelRequest,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    _: dict[str, Any] = Depends(require_scopes("models.write")),
    principal: dict[str, Any] = Depends(get_current_principal),
):
    del principal
    tenant_id = uuid.UUID(tenant_ctx["tenant_id"])
    model = await _get_tenant_owned_model(db=db, model_id=model_id, tenant_id=tenant_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found or permission denied")

    if request.name is not None:
        model.name = request.name.strip()
    if request.description is not None:
        model.description = request.description
    if request.status is not None:
        model.status = request.status
    if request.is_active is not None:
        model.is_active = request.is_active
    if request.metadata is not None:
        model.metadata_ = request.metadata
    if request.default_resolution_policy is not None:
        model.default_resolution_policy = request.default_resolution_policy
    _validate_default_state(
        is_default=request.is_default if request.is_default is not None else model.is_default,
        is_active=model.is_active,
        status=model.status,
    )

    if request.is_default is True:
        await _apply_default_invariant(
            db=db,
            tenant_id=tenant_id,
            capability_type=model.capability_type,
            selected_model_id=model.id,
        )
        model.is_default = True
    elif request.is_default is False:
        model.is_default = False

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Model registry invariant violation") from exc

    stored = await _get_model_response_record(db=db, model_id=model.id, tenant_id=tenant_id)
    return _serialize_model(stored)


@router.delete("/{model_id}")
async def delete_model(
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    _: dict[str, Any] = Depends(require_scopes("models.write")),
    principal: dict[str, Any] = Depends(get_current_principal),
):
    del principal
    tenant_id = uuid.UUID(tenant_ctx["tenant_id"])
    model = await _get_tenant_owned_model(db=db, model_id=model_id, tenant_id=tenant_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found or permission denied")

    await db.delete(model)
    await db.commit()
    return {"status": "deleted", "id": model_id}


@router.post("/{model_id}/providers", response_model=ModelProviderSummary)
async def add_provider_binding(
    model_id: uuid.UUID,
    request: CreateProviderRequest,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    _: dict[str, Any] = Depends(require_scopes("models.write")),
    principal: dict[str, Any] = Depends(get_current_principal),
):
    del principal
    tenant_id = uuid.UUID(tenant_ctx["tenant_id"])
    model = await _get_tenant_owned_model(db=db, model_id=model_id, tenant_id=tenant_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")

    _validate_provider_support(
        provider=request.provider,
        capability_type=model.capability_type,
    )

    binding = ModelProviderBinding(
        model_id=model_id,
        tenant_id=tenant_id,
        provider=request.provider,
        provider_model_id=request.provider_model_id.strip(),
        priority=request.priority,
        config=request.config or {},
        credentials_ref=request.credentials_ref,
    )
    db.add(binding)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate provider binding") from exc

    await db.refresh(binding)
    return _serialize_provider(binding)


@router.patch("/{model_id}/providers/{provider_id}", response_model=ModelProviderSummary)
async def update_provider_binding(
    model_id: uuid.UUID,
    provider_id: uuid.UUID,
    request: UpdateProviderRequest,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    _: dict[str, Any] = Depends(require_scopes("models.write")),
    principal: dict[str, Any] = Depends(get_current_principal),
):
    del principal
    tenant_id = uuid.UUID(tenant_ctx["tenant_id"])

    model = await _get_tenant_owned_model(db=db, model_id=model_id, tenant_id=tenant_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")

    result = await db.execute(
        select(ModelProviderBinding).where(
            and_(
                ModelProviderBinding.id == provider_id,
                ModelProviderBinding.model_id == model_id,
                ModelProviderBinding.tenant_id == tenant_id,
            )
        )
    )
    binding = result.scalar_one_or_none()
    if binding is None:
        raise HTTPException(status_code=404, detail="Provider binding not found")

    _validate_provider_support(
        provider=binding.provider,
        capability_type=model.capability_type,
    )

    if request.provider_model_id is not None:
        binding.provider_model_id = request.provider_model_id.strip()
    if request.priority is not None:
        binding.priority = request.priority
    if request.is_enabled is not None:
        binding.is_enabled = request.is_enabled
    if request.config is not None:
        binding.config = request.config
    if "credentials_ref" in request.model_fields_set:
        binding.credentials_ref = request.credentials_ref

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate provider binding") from exc

    await db.refresh(binding)
    return _serialize_provider(binding)


@router.delete("/{model_id}/providers/{provider_id}")
async def remove_provider_binding(
    model_id: uuid.UUID,
    provider_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    _: dict[str, Any] = Depends(require_scopes("models.write")),
    principal: dict[str, Any] = Depends(get_current_principal),
):
    del principal
    tenant_id = uuid.UUID(tenant_ctx["tenant_id"])

    result = await db.execute(
        select(ModelProviderBinding).where(
            and_(
                ModelProviderBinding.id == provider_id,
                ModelProviderBinding.model_id == model_id,
                ModelProviderBinding.tenant_id == tenant_id,
            )
        )
    )
    binding = result.scalar_one_or_none()
    if binding is None:
        raise HTTPException(status_code=404, detail="Provider binding not found")

    await db.delete(binding)
    await db.commit()
    return {"status": "deleted"}
