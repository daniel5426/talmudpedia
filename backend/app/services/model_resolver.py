"""
Model Resolver - Late-bound resolution of logical models to capability runtimes.

Implements policy-driven model resolution with deterministic binding selection,
credential merging, and capability-specific runtime instantiation.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.postgres.models.registry import (
    IntegrationCredentialCategory,
    ModelCapabilityType,
    ModelProviderBinding,
    ModelProviderType,
    ModelRegistry,
    ModelStatus,
)
from app.services.credentials_service import CredentialsService
from app.services.model_accounting import binding_pricing_snapshot
from app.services.model_runtime import (
    ModelRuntimeAdapterRegistry,
    ResolvedModelBindingReceipt as _ResolvedModelBindingReceipt,
    ResolvedModelRuntimeExecution,
    SpeechToTextRuntime,
    register_default_model_runtime_adapters,
)
from app.services.resource_policy_service import ResourcePolicySnapshot


logger = logging.getLogger(__name__)


class ModelResolverError(Exception):
    """Error during model resolution."""


class ModelResolutionPolicy:
    """Policy for model resolution."""

    def __init__(
        self,
        priority: Optional[list] = None,
        fallback_enabled: bool = True,
        cost_tier: Optional[str] = None,
    ):
        self.priority = priority or []
        self.fallback_enabled = fallback_enabled
        self.cost_tier = cost_tier


ResolvedModelExecution = ResolvedModelRuntimeExecution[Any]
ResolvedModelBindingReceipt = _ResolvedModelBindingReceipt


@dataclass
class _ResolvedBindingContext:
    model: ModelRegistry
    binding: ModelProviderBinding
    policy: ModelResolutionPolicy


class ModelResolver:
    """
    Resolves logical model IDs to concrete capability runtime instances.

    Resolution is policy-driven, supporting:
    - strict tenant/global scope precedence
    - deterministic binding selection
    - centralized provider configuration
    """

    def __init__(self, db: AsyncSession, tenant_id: UUID | None):
        self.db = db
        self.tenant_id = tenant_id
        register_default_model_runtime_adapters()

    async def resolve(
        self,
        model_id: str,
        policy_override: Optional[ModelResolutionPolicy] = None,
        policy_snapshot: ResourcePolicySnapshot | None = None,
    ) -> Any:
        execution = await self.resolve_for_execution(
            model_id,
            policy_override,
            policy_snapshot=policy_snapshot,
        )
        return execution.provider_instance

    async def resolve_for_execution(
        self,
        model_id: str,
        policy_override: Optional[ModelResolutionPolicy] = None,
        policy_snapshot: ResourcePolicySnapshot | None = None,
    ) -> ResolvedModelExecution:
        return await self.resolve_chat_execution(
            model_id,
            policy_override=policy_override,
            policy_snapshot=policy_snapshot,
        )

    async def resolve_receipt(
        self,
        model_id: str,
        policy_override: Optional[ModelResolutionPolicy] = None,
        policy_snapshot: ResourcePolicySnapshot | None = None,
        required_capability: ModelCapabilityType = ModelCapabilityType.CHAT,
    ) -> ResolvedModelBindingReceipt:
        binding_ctx = await self._resolve_binding_context(
            model_id=model_id,
            required_capability=required_capability,
            policy_override=policy_override,
            policy_snapshot=policy_snapshot,
            allow_default=False,
        )
        merged_config, credentials_payload = await self._build_runtime_config(binding_ctx.binding)
        return ResolvedModelBindingReceipt(
            logical_model=binding_ctx.model,
            binding=binding_ctx.binding,
            binding_scope="tenant" if binding_ctx.binding.tenant_id is not None else "global",
            merged_config=merged_config,
            credentials_payload=credentials_payload,
            pricing_snapshot=binding_pricing_snapshot(binding_ctx.binding),
            capability_flags=self._capability_flags(binding_ctx.binding),
            capability_type=required_capability,
        )

    async def resolve_chat_execution(
        self,
        model_id: str,
        policy_override: Optional[ModelResolutionPolicy] = None,
        policy_snapshot: ResourcePolicySnapshot | None = None,
        required_capability: ModelCapabilityType = ModelCapabilityType.CHAT,
    ) -> ResolvedModelExecution:
        return await self._resolve_capability_execution(
            model_id=model_id,
            required_capability=required_capability,
            policy_override=policy_override,
            policy_snapshot=policy_snapshot,
            allow_default=False,
        )

    async def resolve_embedding_execution(
        self,
        model_id: str,
        policy_override: Optional[ModelResolutionPolicy] = None,
        policy_snapshot: ResourcePolicySnapshot | None = None,
        required_capability: ModelCapabilityType = ModelCapabilityType.EMBEDDING,
    ) -> ResolvedModelExecution:
        return await self._resolve_capability_execution(
            model_id=model_id,
            required_capability=required_capability,
            policy_override=policy_override,
            policy_snapshot=policy_snapshot,
            allow_default=False,
        )

    async def resolve_embedding(
        self,
        model_id: str,
        required_capability: ModelCapabilityType = ModelCapabilityType.EMBEDDING,
        policy_snapshot: ResourcePolicySnapshot | None = None,
    ) -> Any:
        execution = await self.resolve_embedding_execution(
            model_id,
            required_capability=required_capability,
            policy_snapshot=policy_snapshot,
        )
        return execution.provider_instance

    async def resolve_speech_to_text_execution(
        self,
        model_id: str | None = None,
        policy_override: Optional[ModelResolutionPolicy] = None,
        policy_snapshot: ResourcePolicySnapshot | None = None,
    ) -> ResolvedModelRuntimeExecution[SpeechToTextRuntime]:
        execution = await self._resolve_capability_execution(
            model_id=model_id,
            required_capability=ModelCapabilityType.SPEECH_TO_TEXT,
            policy_override=policy_override,
            policy_snapshot=policy_snapshot,
            allow_default=True,
        )
        return execution

    async def resolve_speech_to_text(
        self,
        model_id: str | None = None,
        policy_snapshot: ResourcePolicySnapshot | None = None,
    ) -> SpeechToTextRuntime:
        execution = await self.resolve_speech_to_text_execution(
            model_id=model_id,
            policy_snapshot=policy_snapshot,
        )
        return execution.provider_instance

    async def resolve_with_fallback(
        self,
        model_id: str,
        fallback_model_ids: list[str],
        policy_snapshot: ResourcePolicySnapshot | None = None,
    ) -> Any:
        all_models = [model_id] + fallback_model_ids
        for mid in all_models:
            try:
                return await self.resolve(mid, policy_snapshot=policy_snapshot)
            except ModelResolverError:
                continue
        raise ModelResolverError(f"All models failed: {all_models}")

    async def get_model_dimension(self, model_id: str) -> int:
        model = await self._get_model(model_id)
        if not model:
            raise ModelResolverError(f"Model not found: {model_id}")
        metadata = model.metadata_ or {}
        dimension = metadata.get("dimension")
        if dimension is None:
            raise ModelResolverError(
                f"Model '{model.name}' does not have dimension configured in metadata"
            )
        return dimension

    def clear_cache(self) -> None:
        return

    async def _resolve_capability_execution(
        self,
        *,
        model_id: str | None,
        required_capability: ModelCapabilityType,
        policy_override: Optional[ModelResolutionPolicy],
        policy_snapshot: ResourcePolicySnapshot | None,
        allow_default: bool,
    ) -> ResolvedModelExecution:
        binding_ctx = await self._resolve_binding_context(
            model_id=model_id,
            required_capability=required_capability,
            policy_override=policy_override,
            policy_snapshot=policy_snapshot,
            allow_default=allow_default,
        )
        merged_config, credentials_payload = await self._build_runtime_config(binding_ctx.binding)
        runtime_instance = await self._instantiate_runtime(
            capability=required_capability,
            binding=binding_ctx.binding,
            model=binding_ctx.model,
            merged_config=merged_config,
            credentials_payload=credentials_payload,
        )
        return ResolvedModelExecution(
            logical_model=binding_ctx.model,
            binding=binding_ctx.binding,
            runtime_instance=runtime_instance,
            binding_scope="tenant" if binding_ctx.binding.tenant_id is not None else "global",
            merged_config=merged_config,
            credentials_payload=credentials_payload,
            pricing_snapshot=binding_pricing_snapshot(binding_ctx.binding),
            capability_flags=self._capability_flags(binding_ctx.binding),
            capability_type=required_capability,
        )

    async def _resolve_binding_context(
        self,
        *,
        model_id: str | None,
        required_capability: ModelCapabilityType,
        policy_override: Optional[ModelResolutionPolicy],
        policy_snapshot: ResourcePolicySnapshot | None,
        allow_default: bool,
    ) -> _ResolvedBindingContext:
        logger.debug(
            "Resolving model capability %s for tenant %s model_id=%s",
            required_capability.value,
            self.tenant_id,
            model_id,
        )
        model = await self._resolve_model_record(
            model_id=model_id,
            required_capability=required_capability,
            policy_snapshot=policy_snapshot,
            allow_default=allow_default,
        )
        if not model:
            raise ModelResolverError(
                "Model not found" if model_id else f"No default model found for capability '{required_capability.value}'"
            )

        if model.capability_type != required_capability:
            raise ModelResolverError(
                f"Model '{model.name}' has capability '{model.capability_type.value}', "
                f"expected '{required_capability.value}'"
            )
        if model.status == ModelStatus.DISABLED:
            raise ModelResolverError(f"Model '{model.name}' is disabled")
        if model.status == ModelStatus.DEPRECATED:
            logger.warning("Model '%s' is deprecated", model.name)

        policy_data = model.default_resolution_policy or {}
        policy = policy_override or ModelResolutionPolicy(
            priority=policy_data.get("priority"),
            fallback_enabled=policy_data.get("fallback_enabled", True),
            cost_tier=policy_data.get("cost_tier"),
        )

        binding = await self._resolve_binding(model, policy)
        if not binding and policy.fallback_enabled:
            fallback = await self._get_fallback_model(model)
            if fallback is not None:
                logger.info("Falling back to model: %s", fallback.name)
                return await self._resolve_binding_context(
                    model_id=str(fallback.id),
                    required_capability=required_capability,
                    policy_override=policy_override,
                    policy_snapshot=policy_snapshot,
                    allow_default=False,
                )
        if not binding:
            raise ModelResolverError(f"No suitable binding/provider found for model: {model.name}")
        return _ResolvedBindingContext(model=model, binding=binding, policy=policy)

    async def _resolve_model_record(
        self,
        *,
        model_id: str | None,
        required_capability: ModelCapabilityType,
        policy_snapshot: ResourcePolicySnapshot | None,
        allow_default: bool,
    ) -> ModelRegistry | None:
        if model_id:
            if policy_snapshot is not None and not policy_snapshot.can_use("model", model_id):
                raise ModelResolverError(f"Model access denied: {model_id}")
            return await self._get_model(model_id)
        if not allow_default:
            raise ModelResolverError("Model id is required")
        return await self._get_default_model(required_capability, policy_snapshot=policy_snapshot)

    async def _resolve_binding(
        self,
        model: ModelRegistry,
        policy: Optional[ModelResolutionPolicy] = None,
    ) -> Optional[ModelProviderBinding]:
        tenant_bindings: list[ModelProviderBinding] = []
        global_bindings: list[ModelProviderBinding] = []

        for binding in model.providers:
            if not binding.is_enabled:
                continue
            if self.tenant_id is not None and binding.tenant_id == self.tenant_id:
                tenant_bindings.append(binding)
            elif binding.tenant_id is None:
                global_bindings.append(binding)

        def _sort_key(binding: ModelProviderBinding) -> tuple[int, int]:
            priority_order = [p.lower() for p in (policy.priority or [])] if policy else []
            provider_key = binding.provider.value if hasattr(binding.provider, "value") else str(binding.provider)
            provider_rank = priority_order.index(provider_key) if provider_key in priority_order else len(priority_order)
            return (provider_rank, binding.priority)

        if tenant_bindings:
            tenant_bindings.sort(key=_sort_key if policy and policy.priority else lambda item: item.priority)
            return tenant_bindings[0]
        if global_bindings:
            global_bindings.sort(key=_sort_key if policy and policy.priority else lambda item: item.priority)
            return global_bindings[0]
        return None

    async def _build_runtime_config(
        self,
        binding: ModelProviderBinding,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        credentials_payload, _, _provider_variant = await self._resolve_provider_credentials(
            binding,
            self._credential_category_for_binding(binding),
        )
        merged_config = dict(credentials_payload or {})
        for key, value in dict(binding.config or {}).items():
            if key == "api_key":
                continue
            merged_config[key] = value
        return merged_config, dict(credentials_payload or {})

    async def _instantiate_runtime(
        self,
        *,
        capability: ModelCapabilityType,
        binding: ModelProviderBinding,
        model: ModelRegistry,
        merged_config: dict[str, Any],
        credentials_payload: dict[str, Any],
    ) -> Any:
        factory = ModelRuntimeAdapterRegistry.get(capability=capability, provider=binding.provider)
        if factory is None:
            raise ModelResolverError(
                f"Provider {binding.provider.value} is not runtime-supported for capability {capability.value}"
            )
        try:
            return await factory(
                binding=binding,
                model=model,
                merged_config=merged_config,
                credentials_payload=credentials_payload,
            )
        except Exception as exc:
            logger.error(
                "Failed to instantiate runtime for model %s (%s/%s): %s",
                model.name,
                capability.value,
                binding.provider.value,
                exc,
            )
            raise ModelResolverError(f"Provider instantiation failed: {exc}") from exc

    async def _resolve_provider_credentials(
        self,
        binding: ModelProviderBinding,
        category: IntegrationCredentialCategory,
    ) -> tuple[dict[str, Any], Optional[str], Optional[str]]:
        provider_variant = (binding.config or {}).get("provider_variant")
        credentials_service = CredentialsService(self.db, self.tenant_id)
        credentials_payload = await credentials_service.resolve_backend_config(
            base_config={},
            credentials_ref=binding.credentials_ref,
            category=category,
            provider_key=getattr(binding.provider, "value", str(binding.provider)),
            provider_variant=provider_variant,
        )
        api_key = credentials_payload.get("api_key") if credentials_payload else None
        return dict(credentials_payload or {}), api_key, provider_variant

    async def _get_model(self, model_id: str) -> Optional[ModelRegistry]:
        try:
            mid = UUID(str(model_id))
        except Exception:
            return None
        scope_clause = (
            or_(ModelRegistry.tenant_id == self.tenant_id, ModelRegistry.tenant_id.is_(None))
            if self.tenant_id is not None
            else ModelRegistry.tenant_id.is_(None)
        )
        stmt = (
            select(ModelRegistry)
            .where(
                ModelRegistry.id == mid,
                ModelRegistry.is_active == True,
                scope_clause,
            )
            .options(selectinload(ModelRegistry.providers))
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _get_default_model(
        self,
        capability: ModelCapabilityType,
        *,
        policy_snapshot: ResourcePolicySnapshot | None,
    ) -> Optional[ModelRegistry]:
        candidates: list[ModelRegistry] = []
        base_stmt = (
            select(ModelRegistry)
            .where(
                ModelRegistry.capability_type == capability,
                ModelRegistry.is_active == True,
            )
            .options(selectinload(ModelRegistry.providers))
        )
        if self.tenant_id is not None:
            tenant_default_stmt = base_stmt.where(
                ModelRegistry.tenant_id == self.tenant_id,
                ModelRegistry.is_default == True,
            )
            global_default_stmt = base_stmt.where(
                ModelRegistry.tenant_id.is_(None),
                ModelRegistry.is_default == True,
            )
            tenant_fallback_stmt = base_stmt.where(ModelRegistry.tenant_id == self.tenant_id)
            global_fallback_stmt = base_stmt.where(ModelRegistry.tenant_id.is_(None))
            ordered_stmts = [tenant_default_stmt, global_default_stmt, tenant_fallback_stmt, global_fallback_stmt]
        else:
            ordered_stmts = [
                base_stmt.where(ModelRegistry.tenant_id.is_(None), ModelRegistry.is_default == True),
                base_stmt.where(ModelRegistry.tenant_id.is_(None)),
            ]

        for stmt in ordered_stmts:
            result = await self.db.execute(stmt)
            candidates = list(result.scalars().all())
            for model in candidates:
                if policy_snapshot is not None and not policy_snapshot.can_use("model", str(model.id)):
                    continue
                return model
        return None

    async def _get_fallback_model(self, failed_model: ModelRegistry) -> Optional[ModelRegistry]:
        scope_clause = (
            or_(ModelRegistry.tenant_id == self.tenant_id, ModelRegistry.tenant_id.is_(None))
            if self.tenant_id is not None
            else ModelRegistry.tenant_id.is_(None)
        )
        query = (
            select(ModelRegistry)
            .where(
                ModelRegistry.capability_type == failed_model.capability_type,
                ModelRegistry.is_active == True,
                ModelRegistry.id != failed_model.id,
                scope_clause,
            )
            .options(selectinload(ModelRegistry.providers))
            .limit(1)
        )
        return (await self.db.execute(query)).scalar_one_or_none()

    @staticmethod
    def _credential_category_for_binding(binding: ModelProviderBinding) -> IntegrationCredentialCategory:
        del binding
        return IntegrationCredentialCategory.LLM_PROVIDER

    @staticmethod
    def _capability_flags(binding: ModelProviderBinding) -> dict[str, bool]:
        binding_config = dict(binding.config or {})
        provider_value = getattr(binding.provider, "value", str(binding.provider))
        supports_usage_reporting = provider_value in {"openai", "anthropic", "google", "gemini", "xai"}
        return {
            "supports_usage_reporting": supports_usage_reporting,
            "supports_stream_usage": bool(binding_config.get("supports_stream_usage", False)),
            "supports_final_usage_reporting": bool(
                binding_config.get("supports_final_usage_reporting", supports_usage_reporting)
            ),
            "supports_provider_cost_reporting": bool(
                binding_config.get("supports_provider_cost_reporting", False)
            ),
            "supports_separate_input_output_tokens": bool(
                binding_config.get("supports_separate_input_output_tokens", supports_usage_reporting)
            ),
        }
