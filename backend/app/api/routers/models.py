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
from app.services.integration_provider_catalog import (
    is_model_provider_supported,
    is_tenant_managed_pricing_provider,
)
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.errors import ControlPlaneError
from app.services.control_plane.models_service import (
    CreateModelInput,
    ListModelsInput,
    ModelRegistryService,
    UpdateModelInput,
    apply_default_invariant,
    enum_filter,
    enum_value,
    model_scope_clause,
    validate_default_state,
    validate_provider_support,
    validate_registry_pricing_policy,
)


def _validate_provider_support(*, provider: ModelProviderType, capability_type: ModelCapabilityType) -> None:
    try:
        validate_provider_support(provider=provider, capability_type=capability_type)
    except ControlPlaneError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message) from exc


def _validate_registry_pricing_policy(*, provider: ModelProviderType, pricing_config: dict | None) -> dict:
    try:
        return validate_registry_pricing_policy(provider=provider, pricing_config=pricing_config)
    except ControlPlaneError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message) from exc

router = APIRouter(prefix="/models", tags=["models"])


class CreateProviderRequest(BaseModel):
    provider: ModelProviderType
    provider_model_id: str
    priority: int = 0
    config: dict | None = None
    credentials_ref: uuid.UUID | None = None
    pricing_config: dict | None = None


class UpdateProviderRequest(BaseModel):
    provider_model_id: str | None = None
    priority: int | None = None
    is_enabled: bool | None = None
    config: dict | None = None
    credentials_ref: uuid.UUID | None = None
    pricing_config: dict | None = None


class ModelProviderSummary(BaseModel):
    id: uuid.UUID
    provider: ModelProviderType
    provider_model_id: str
    priority: int
    is_enabled: bool
    config: dict
    credentials_ref: uuid.UUID | None = None
    pricing_config: dict


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
        pricing_config=binding.pricing_config or {},
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


def _service_context(*, tenant_ctx: dict[str, Any], principal: dict[str, Any]) -> ControlPlaneContext:
    return ControlPlaneContext.from_tenant_context(
        tenant_ctx,
        user=principal.get("user"),
        user_id=uuid.UUID(str(principal["user_id"])) if principal.get("user_id") else None,
        auth_token=principal.get("auth_token"),
        scopes=principal.get("scopes"),
        is_service=bool(principal.get("type") == "workload"),
    )


def _model_filters(
    *,
    tenant_id: uuid.UUID,
    capability_type: ModelCapabilityType | None,
    status: ModelStatus | None,
    is_active: bool | None,
):
    filters: list[Any] = [model_scope_clause(tenant_id)]
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


_SUPPORTED_BILLING_MODES = {
    "per_token",
    "per_1k_tokens",
    "flat_per_request",
    "manual",
    "unknown",
}


def _coerce_optional_float(value: Any, *, field_name: str) -> float:
    try:
        parsed = float(value)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid numeric value for pricing_config.{field_name}") from exc
    if parsed < 0:
        raise HTTPException(status_code=422, detail=f"pricing_config.{field_name} must be >= 0")
    return parsed


def _validate_pricing_config(pricing_config: dict | None) -> dict:
    if pricing_config is None:
        return {}
    if not isinstance(pricing_config, dict):
        raise HTTPException(status_code=422, detail="pricing_config must be an object")

    normalized = dict(pricing_config)
    currency = str(normalized.get("currency") or "USD").strip().upper()
    billing_mode = str(normalized.get("billing_mode") or "unknown").strip().lower()
    if billing_mode not in _SUPPORTED_BILLING_MODES:
        raise HTTPException(status_code=422, detail="pricing_config.billing_mode is invalid")
    if billing_mode == "manual":
        raise HTTPException(status_code=422, detail="pricing_config.billing_mode 'manual' is reserved for internal overrides")

    normalized["currency"] = currency
    normalized["billing_mode"] = billing_mode

    rates = normalized.get("rates")
    if rates is not None and not isinstance(rates, dict):
        raise HTTPException(status_code=422, detail="pricing_config.rates must be an object")
    normalized_rates: dict[str, float] = {}
    for key, value in dict(rates or {}).items():
        normalized_rates[str(key)] = _coerce_optional_float(value, field_name=f"rates.{key}")
    if normalized_rates:
        normalized["rates"] = normalized_rates
    else:
        normalized.pop("rates", None)

    if "minimum_charge" in normalized and normalized.get("minimum_charge") is not None:
        normalized["minimum_charge"] = _coerce_optional_float(
            normalized.get("minimum_charge"),
            field_name="minimum_charge",
        )

    if "flat_amount" in normalized and normalized.get("flat_amount") is not None:
        normalized["flat_amount"] = _coerce_optional_float(
            normalized.get("flat_amount"),
            field_name="flat_amount",
        )

    if billing_mode in {"per_token", "per_1k_tokens"} and not normalized.get("rates"):
        raise HTTPException(status_code=422, detail="pricing_config.rates is required for token pricing")
    if billing_mode == "flat_per_request" and normalized.get("flat_amount") is None:
        raise HTTPException(status_code=422, detail="pricing_config.flat_amount is required for flat pricing")

    if billing_mode != "flat_per_request":
        normalized.pop("flat_amount", None)
    if billing_mode not in {"per_token", "per_1k_tokens"}:
        normalized.pop("rates", None)
    normalized.pop("manual_total_cost", None)

    return normalized


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
    try:
        models, total = await ModelRegistryService(db).list_models(
            ctx=_service_context(tenant_ctx=tenant_ctx, principal=principal),
            params=ListModelsInput(
                capability_type=capability_type,
                status=status,
                is_active=is_active,
                skip=skip,
                limit=limit,
            ),
        )
        return ModelListResponse(models=[_serialize_model(model) for model in models], total=total)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.post("", response_model=ModelResponse)
async def create_model(
    request: CreateModelRequest,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    _: dict[str, Any] = Depends(require_scopes("models.write")),
    principal: dict[str, Any] = Depends(get_current_principal),
):
    try:
        model = await ModelRegistryService(db).create_model(
            ctx=_service_context(tenant_ctx=tenant_ctx, principal=principal),
            params=CreateModelInput(
                name=request.name,
                description=request.description,
                capability_type=request.capability_type,
                metadata=request.metadata,
                default_resolution_policy=request.default_resolution_policy,
                is_default=request.is_default,
                is_active=request.is_active,
                status=request.status,
            ),
        )
        return _serialize_model(model)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


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
    try:
        model = await ModelRegistryService(db).get_model(
            ctx=_service_context(tenant_ctx=tenant_ctx, principal=principal),
            model_id=model_id,
        )
        return _serialize_model(model)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


@router.put("/{model_id}", response_model=ModelResponse)
async def update_model(
    model_id: uuid.UUID,
    request: UpdateModelRequest,
    db: AsyncSession = Depends(get_db),
    tenant_ctx=Depends(get_tenant_context),
    _: dict[str, Any] = Depends(require_scopes("models.write")),
    principal: dict[str, Any] = Depends(get_current_principal),
):
    try:
        model = await ModelRegistryService(db).update_model(
            ctx=_service_context(tenant_ctx=tenant_ctx, principal=principal),
            model_id=model_id,
            params=UpdateModelInput(
                name=request.name,
                description=request.description,
                status=request.status,
                is_active=request.is_active,
                is_default=request.is_default,
                metadata=request.metadata,
                default_resolution_policy=request.default_resolution_policy,
            ),
        )
        return _serialize_model(model)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc


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
        pricing_config=_validate_registry_pricing_policy(
            provider=request.provider,
            pricing_config=request.pricing_config,
        ),
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
    if "pricing_config" in request.model_fields_set:
        binding.pricing_config = _validate_registry_pricing_policy(
            provider=binding.provider,
            pricing_config=request.pricing_config,
        )

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
