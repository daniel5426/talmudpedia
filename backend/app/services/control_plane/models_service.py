from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import String, and_, cast, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.postgres.models.registry import (
    ModelCapabilityType,
    ModelProviderBinding,
    ModelProviderType,
    ModelRegistry,
    ModelStatus,
)
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.errors import conflict, not_found, validation
from app.services.integration_provider_catalog import (
    is_model_provider_supported,
    is_tenant_managed_pricing_provider,
)


@dataclass(frozen=True)
class ListModelsInput:
    capability_type: ModelCapabilityType | None = None
    status: ModelStatus | None = None
    is_active: bool | None = True
    skip: int = 0
    limit: int = 50


@dataclass(frozen=True)
class CreateModelInput:
    name: str
    description: str | None = None
    capability_type: ModelCapabilityType = ModelCapabilityType.CHAT
    metadata: dict | None = None
    default_resolution_policy: dict | None = None
    is_default: bool = False
    is_active: bool = True
    status: ModelStatus = ModelStatus.ACTIVE


@dataclass(frozen=True)
class UpdateModelInput:
    name: str | None = None
    description: str | None = None
    status: ModelStatus | None = None
    is_active: bool | None = None
    is_default: bool | None = None
    metadata: dict | None = None
    default_resolution_policy: dict | None = None


def serialize_model(model: ModelRegistry, *, view: str = "full") -> dict[str, Any]:
    payload = {
        "id": str(model.id),
        "tenant_id": str(model.tenant_id) if model.tenant_id else None,
        "name": model.name,
        "description": model.description,
        "capability_type": getattr(model.capability_type, "value", model.capability_type),
        "status": getattr(model.status, "value", model.status),
        "is_active": bool(model.is_active),
        "is_default": bool(model.is_default),
        "created_at": model.created_at.isoformat() if model.created_at else None,
        "updated_at": model.updated_at.isoformat() if model.updated_at else None,
    }
    if view == "summary":
        return payload
    payload.update(
        {
            "version": model.version,
            "metadata": model.metadata_ or {},
            "default_resolution_policy": model.default_resolution_policy or {},
            "providers": [
                {
                    "id": str(binding.id),
                    "provider": getattr(binding.provider, "value", binding.provider),
                    "provider_model_id": binding.provider_model_id,
                    "priority": binding.priority,
                    "is_enabled": bool(binding.is_enabled),
                    "config": binding.config or {},
                    "credentials_ref": str(binding.credentials_ref) if binding.credentials_ref else None,
                    "pricing_config": binding.pricing_config or {},
                }
                for binding in list(model.providers or [])
            ],
        }
    )
    return payload


def enum_value(value: Any) -> str:
    return str(getattr(value, "value", value)).strip().lower()


def enum_filter(column, value):
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


def model_scope_clause(tenant_id: UUID):
    return or_(ModelRegistry.tenant_id == tenant_id, ModelRegistry.tenant_id.is_(None))


async def apply_default_invariant(
    *,
    db: AsyncSession,
    tenant_id: UUID | None,
    capability_type: ModelCapabilityType,
    selected_model_id: UUID,
) -> None:
    await db.execute(
        update(ModelRegistry)
        .where(
            ModelRegistry.id != selected_model_id,
            ModelRegistry.capability_type == capability_type,
            (ModelRegistry.tenant_id == tenant_id if tenant_id is not None else ModelRegistry.tenant_id.is_(None)),
            ModelRegistry.is_default.is_(True),
        )
        .values(is_default=False)
    )


def validate_default_state(*, is_default: bool, is_active: bool, status: ModelStatus) -> None:
    if is_default and (not is_active or status == ModelStatus.DISABLED):
        raise validation("Default models must remain active and cannot be disabled")


class ModelRegistryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_models(self, *, ctx: ControlPlaneContext, params: ListModelsInput) -> tuple[list[ModelRegistry], int]:
        result = await self.db.execute(
            select(ModelRegistry)
            .where(model_scope_clause(ctx.tenant_id))
            .options(selectinload(ModelRegistry.providers))
            .order_by(ModelRegistry.name.asc())
        )
        scoped_models = result.scalars().all()
        filtered_models = [
            model for model in scoped_models
            if (params.capability_type is None or enum_value(model.capability_type) == enum_value(params.capability_type))
            and (params.status is None or enum_value(model.status) == enum_value(params.status))
            and (params.is_active is None or bool(model.is_active) is params.is_active)
        ]
        models = filtered_models[params.skip: params.skip + params.limit]
        return models, len(filtered_models)

    async def create_model(self, *, ctx: ControlPlaneContext, params: CreateModelInput) -> ModelRegistry:
        validate_default_state(is_default=params.is_default, is_active=params.is_active, status=params.status)
        model = ModelRegistry(
            tenant_id=ctx.tenant_id,
            name=params.name.strip(),
            description=params.description,
            capability_type=params.capability_type,
            status=params.status,
            metadata_=params.metadata or {},
            default_resolution_policy=params.default_resolution_policy or {},
            is_active=params.is_active,
            is_default=False,
        )
        self.db.add(model)
        await self.db.flush()
        if params.is_default:
            await apply_default_invariant(
                db=self.db,
                tenant_id=ctx.tenant_id,
                capability_type=model.capability_type,
                selected_model_id=model.id,
            )
            model.is_default = True
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise conflict("Model registry invariant violation") from exc
        return await self.get_model(ctx=ctx, model_id=model.id)

    async def get_model(self, *, ctx: ControlPlaneContext, model_id: UUID) -> ModelRegistry:
        result = await self.db.execute(
            select(ModelRegistry)
            .where(and_(ModelRegistry.id == model_id, model_scope_clause(ctx.tenant_id)))
            .options(selectinload(ModelRegistry.providers))
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise not_found("Model not found")
        return model

    async def update_model(self, *, ctx: ControlPlaneContext, model_id: UUID, params: UpdateModelInput) -> ModelRegistry:
        result = await self.db.execute(
            select(ModelRegistry)
            .where(and_(ModelRegistry.id == model_id, ModelRegistry.tenant_id == ctx.tenant_id))
            .options(selectinload(ModelRegistry.providers))
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise not_found("Model not found or permission denied")
        if params.name is not None:
            model.name = params.name.strip()
        if params.description is not None:
            model.description = params.description
        if params.status is not None:
            model.status = params.status
        if params.is_active is not None:
            model.is_active = params.is_active
        if params.metadata is not None:
            model.metadata_ = params.metadata
        if params.default_resolution_policy is not None:
            model.default_resolution_policy = params.default_resolution_policy
        validate_default_state(
            is_default=params.is_default if params.is_default is not None else model.is_default,
            is_active=model.is_active,
            status=model.status,
        )
        if params.is_default is True:
            await apply_default_invariant(
                db=self.db,
                tenant_id=ctx.tenant_id,
                capability_type=model.capability_type,
                selected_model_id=model.id,
            )
            model.is_default = True
        elif params.is_default is False:
            model.is_default = False
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise conflict("Model registry invariant violation") from exc
        return await self.get_model(ctx=ctx, model_id=model.id)


def validate_provider_support(*, provider: ModelProviderType, capability_type: ModelCapabilityType) -> None:
    if not is_model_provider_supported(provider=provider, capability=capability_type):
        raise validation(
            f"Provider '{provider.value}' is not supported for capability '{capability_type.value}'"
        )


SUPPORTED_BILLING_MODES = {
    "per_token",
    "per_1k_tokens",
    "flat_per_request",
    "manual",
    "unknown",
}


def coerce_optional_float(value: Any, *, field_name: str) -> float:
    try:
        parsed = float(value)
    except Exception as exc:
        raise validation(f"Invalid numeric value for pricing_config.{field_name}") from exc
    if parsed < 0:
        raise validation(f"pricing_config.{field_name} must be >= 0")
    return parsed


def validate_pricing_config(pricing_config: dict | None) -> dict:
    if pricing_config is None:
        return {}
    if not isinstance(pricing_config, dict):
        raise validation("pricing_config must be an object")
    normalized = dict(pricing_config)
    currency = str(normalized.get("currency") or "USD").strip().upper()
    billing_mode = str(normalized.get("billing_mode") or "unknown").strip().lower()
    if billing_mode not in SUPPORTED_BILLING_MODES:
        raise validation("pricing_config.billing_mode is invalid")
    if billing_mode == "manual":
        raise validation("pricing_config.billing_mode 'manual' is reserved for internal overrides")
    normalized["currency"] = currency
    normalized["billing_mode"] = billing_mode
    rates = normalized.get("rates")
    if rates is not None and not isinstance(rates, dict):
        raise validation("pricing_config.rates must be an object")
    normalized_rates: dict[str, float] = {}
    for key, value in dict(rates or {}).items():
        normalized_rates[str(key)] = coerce_optional_float(value, field_name=f"rates.{key}")
    if normalized_rates:
        normalized["rates"] = normalized_rates
    else:
        normalized.pop("rates", None)
    if "minimum_charge" in normalized and normalized.get("minimum_charge") is not None:
        normalized["minimum_charge"] = coerce_optional_float(normalized.get("minimum_charge"), field_name="minimum_charge")
    if "flat_amount" in normalized and normalized.get("flat_amount") is not None:
        normalized["flat_amount"] = coerce_optional_float(normalized.get("flat_amount"), field_name="flat_amount")
    if billing_mode in {"per_token", "per_1k_tokens"} and not normalized.get("rates"):
        raise validation("pricing_config.rates is required for token pricing")
    if billing_mode == "flat_per_request" and normalized.get("flat_amount") is None:
        raise validation("pricing_config.flat_amount is required for flat pricing")
    if billing_mode != "flat_per_request":
        normalized.pop("flat_amount", None)
    if billing_mode not in {"per_token", "per_1k_tokens"}:
        normalized.pop("rates", None)
    normalized.pop("manual_total_cost", None)
    return normalized


def validate_registry_pricing_policy(*, provider: ModelProviderType, pricing_config: dict | None) -> dict:
    normalized = validate_pricing_config(pricing_config)
    if normalized and not is_tenant_managed_pricing_provider(provider):
        raise validation(f"Pricing is platform-managed for provider '{provider.value}'")
    return normalized
