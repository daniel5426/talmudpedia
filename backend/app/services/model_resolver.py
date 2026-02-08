"""
Model Resolver - Late-bound resolution of logical models to providers.

Implements policy-driven model resolution with fallback, compliance,
and cost tier support. Now uses PostgreSQL.
"""
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.postgres.models.registry import (
    ModelRegistry,
    ModelProviderType,
    ModelProviderBinding,
    ModelCapabilityType,
    ProviderConfig,
    IntegrationCredentialCategory
)
from app.services.credentials_service import CredentialsService
from app.agent.core.interfaces import LLMProvider
from app.agent.components.llm.langchain_provider import LangChainProviderAdapter
from app.rag.interfaces.embedding import EmbeddingProvider
from app.rag.providers.embedding.openai import OpenAIEmbeddingProvider
from app.rag.providers.embedding.gemini import GeminiEmbeddingProvider
from app.rag.providers.embedding.huggingface import HuggingFaceEmbeddingProvider


logger = logging.getLogger(__name__)


class ModelResolverError(Exception):
    """Error during model resolution."""
    pass


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


class ModelResolver:
    """
    Resolves logical model IDs to concrete LLMProvider instances.

    Resolution is policy-driven, supporting:
    - strict tenant isolation
    - deterministic binding selection
    - centralized provider configuration
    """

    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        # Cache for ProviderConfigs within this session
        self._config_cache: dict[str, ProviderConfig] = {}

    async def resolve(
        self,
        model_id: str,
        policy_override: Optional[ModelResolutionPolicy] = None
    ) -> LLMProvider:
        """
        Resolve a logical model ID to a provider instance.
        """
        # 1. Fetch model
        logger.debug(f"Resolving model {model_id} for tenant {self.tenant_id}")
        model = await self._get_model(model_id)
        if not model:
            # Check if it was a direct provider model ID (e.g. "gpt-4o") for dev convenience?
            # ideally NO, we want strict logical IDs.
            raise ModelResolverError(f"Model not found: {model_id}")

        logger.info(f"Resolved logical model: {model.name} ({model.id})")

        # 2. Binding Resolution (Deterministic)
        policy_data = model.default_resolution_policy or {}
        policy = policy_override or ModelResolutionPolicy(
            priority=policy_data.get("priority"),
            fallback_enabled=policy_data.get("fallback_enabled", True),
            cost_tier=policy_data.get("cost_tier"),
        )

        binding = await self._resolve_binding(model, policy)
        if not binding:
            # Policy-driven fallback
            if policy.fallback_enabled:
                logger.warning(f"No usable binding for {model.name}. Attempting fallback.")
                fallback = await self._get_fallback_model(model)
                if fallback:
                    logger.info(f"Falling back to model: {fallback.name}")
                    return await self.resolve(str(fallback.id), policy_override)

            raise ModelResolverError(f"No suitable binding/provider found for model: {model.name}")

        # 3. Provider Instantiation
        try:
            return await self._create_provider_instance(binding)
        except Exception as e:
            logger.error(f"Failed to instantiate provider for {model.name}: {e}")
            raise ModelResolverError(f"Provider instantiation failed: {e}")

    async def _resolve_binding(
        self,
        model: ModelRegistry,
        policy: Optional[ModelResolutionPolicy] = None
    ) -> Optional[ModelProviderBinding]:
        """
        Select the best binding for the current tenant.
        Rule: Tenant Binding > Global Binding.
        Rule: If Tenant Binding exists but is disabled -> STOP. (No fallback to global).
        """
        # Separate bindings
        tenant_bindings = []
        global_bindings = []

        for b in model.providers:
            if b.tenant_id == self.tenant_id:
                tenant_bindings.append(b)
            elif b.tenant_id is None:
                global_bindings.append(b)

        # 1. Check Tenant Bindings
        def _sort_key(binding: ModelProviderBinding) -> tuple:
            priority_order = [p.lower() for p in (policy.priority or [])] if policy else []
            provider_key = binding.provider.value if hasattr(binding.provider, "value") else str(binding.provider)
            provider_rank = priority_order.index(provider_key) if provider_key in priority_order else len(priority_order)
            return (provider_rank, binding.priority)

        if tenant_bindings:
            # Sort by policy priority (if provided), then binding priority
            tenant_bindings.sort(key=_sort_key if policy and policy.priority else lambda x: x.priority)
            best = tenant_bindings[0]
            
            if not best.is_enabled:
                logger.warning(f"Tenant binding for {model.name} is explicitly disabled. Aborting resolution.")
                return None
            
            logger.info(f"Selected TENANT binding: {best.provider} -> {best.provider_model_id}")
            return best

        # 2. Check Global Bindings
        if global_bindings:
            global_bindings.sort(key=_sort_key if policy and policy.priority else lambda x: x.priority)
            best = global_bindings[0]

            if not best.is_enabled:
                logger.warning(f"System binding for {model.name} is disabled.")
                return None
                
            logger.info(f"Selected GLOBAL binding: {best.provider} -> {best.provider_model_id}")
            return best

        return None

    async def _create_provider_instance(self, binding: ModelProviderBinding) -> LLMProvider:
        """
        Create provider with merged config (ProviderConfig + Binding.config).
        """
        # 1. Resolve credentials (IntegrationCredential -> ProviderConfig -> Binding.config)
        credentials_payload, api_key, provider_variant = await self._resolve_provider_credentials(
            binding,
            IntegrationCredentialCategory.LLM_PROVIDER
        )

        # 2. Merge configs
        final_config = dict(credentials_payload or {})

        # Overlay: Binding config (runtime params like temp, max_tokens)
        # We explicitly exclude auth keys from binding config to prevent leakage/override confusion
        binding_params = binding.config or {}

        if not api_key:
            api_key = binding_params.get("api_key")

        if not api_key and binding.provider != ModelProviderType.LOCAL:
            raise ModelResolverError(f"Missing API Key for provider {binding.provider}")

        # Remove keys from final kwargs
        final_config.pop("api_key", None)

        # Add runtime params
        for k, v in binding_params.items():
            if k not in ["api_key", "provider_variant"]:
                final_config[k] = v

        # 3. Instantiate
        if binding.provider == ModelProviderType.OPENAI:
            return LangChainProviderAdapter(
                provider=binding.provider,
                model=binding.provider_model_id,
                api_key=api_key,
                **final_config,
            )
        elif binding.provider in (ModelProviderType.GOOGLE, ModelProviderType.GEMINI):
            return LangChainProviderAdapter(
                provider=binding.provider,
                model=binding.provider_model_id,
                api_key=api_key,
                **final_config,
            )
        # ... add others ...
        else:
             # Fallback generic or error
             raise ModelResolverError(f"Provider {binding.provider} not factory-supported yet.")

    async def _get_provider_config(self, provider: ModelProviderType, variant: Optional[str] = None) -> Optional[ProviderConfig]:
        """
        Find best ProviderConfig: Tenant > Global.
        Matches provider + variant.
        """
        cache_key = f"{provider}:{variant}"
        if cache_key in self._config_cache:
            return self._config_cache[cache_key]
            
        # 1. Try Tenant
        stmt = select(ProviderConfig).where(
            ProviderConfig.tenant_id == self.tenant_id,
            ProviderConfig.provider == provider,
            ProviderConfig.provider_variant == variant,
            ProviderConfig.is_enabled == True
        )
        res = await self.db.execute(stmt)
        config = res.scalar_one_or_none()
        
        if config:
            self._config_cache[cache_key] = config
            return config
            
        # 2. Try Global
        stmt = select(ProviderConfig).where(
            ProviderConfig.tenant_id == None,
            ProviderConfig.provider == provider,
            ProviderConfig.provider_variant == variant,
            ProviderConfig.is_enabled == True
        )
        res = await self.db.execute(stmt)
        config = res.scalar_one_or_none()
        
        if config:
            self._config_cache[cache_key] = config
            return config
            
        return None

    async def _resolve_provider_credentials(
        self,
        binding: ModelProviderBinding,
        category: IntegrationCredentialCategory,
    ) -> tuple[dict, Optional[str], Optional[str]]:
        """
        Resolve credentials for a provider binding.

        Priority:
        1) IntegrationCredential by credentials_ref
        2) IntegrationCredential by (provider, variant)
        3) ProviderConfig (legacy)
        4) Binding.config.api_key (legacy)
        """
        provider_variant = (binding.config or {}).get("provider_variant")
        credentials_service = CredentialsService(self.db, self.tenant_id)

        credential = None
        if binding.credentials_ref:
            credential = await credentials_service.get_by_id(binding.credentials_ref)
        if not credential:
            credential = await credentials_service.get_by_provider(
                category=category,
                provider_key=binding.provider.value,
                provider_variant=provider_variant,
            )

        if credential and not credential.is_enabled:
            raise ModelResolverError(
                f"Credentials disabled for provider {binding.provider} (ref={credential.id})"
            )

        credentials_payload: dict = credential.credentials if credential else {}
        api_key = credentials_payload.get("api_key") if credentials_payload else None

        if not credentials_payload:
            provider_config = await self._get_provider_config(binding.provider, provider_variant)
            if provider_config:
                credentials_payload = provider_config.credentials or {}
                api_key = credentials_payload.get("api_key")

        if not api_key:
            api_key = (binding.config or {}).get("api_key")

        return credentials_payload, api_key, provider_variant

    # ... (Rest of resolver methods like resolve_with_fallback, etc. need corresponding updates or can reuse basics)

    async def resolve_with_fallback(
        self,
        model_id: str,
        fallback_model_ids: list[str]
    ) -> LLMProvider:
        """
        Resolve model with explicit fallback chain.
        """
        all_models = [model_id] + fallback_model_ids
        for mid in all_models:
            try:
                return await self.resolve(mid)
            except ModelResolverError:
                continue
        raise ModelResolverError(f"All models failed: {all_models}")

    async def _get_model(self, model_id: str) -> Optional[ModelRegistry]:
        """Fetch model by ID/Slug with bindings."""
        # Try UUID
        try:
            mid = UUID(model_id)
            clause = ModelRegistry.id == mid
        except ValueError:
            clause = or_(ModelRegistry.slug == model_id, ModelRegistry.name == model_id)
            
        # Common query
        stmt = select(ModelRegistry).where(
            clause,
            ModelRegistry.is_active == True,
            or_(ModelRegistry.tenant_id == self.tenant_id, ModelRegistry.tenant_id == None)
        ).options(selectinload(ModelRegistry.providers))
        
        res = await self.db.execute(stmt)
        return res.scalar_one_or_none()

    async def _get_fallback_model(self, failed_model: ModelRegistry) -> Optional[ModelRegistry]:
        """Get a fallback model of the same capability type."""
        query = select(ModelRegistry).where(
            ModelRegistry.capability_type == failed_model.capability_type,
            ModelRegistry.is_active == True,
            ModelRegistry.id != failed_model.id,
            or_(ModelRegistry.tenant_id == self.tenant_id, ModelRegistry.tenant_id.is_(None))
        ).limit(1)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    def clear_cache(self):
        """Clear the provider cache."""
        self._config_cache.clear()
    
    # ─────────────────────────────────────────────────────────────────────────
    # Embedding Model Resolution
    # ─────────────────────────────────────────────────────────────────────────
    
    async def resolve_embedding(
        self,
        model_id: str,
        required_capability: ModelCapabilityType = ModelCapabilityType.EMBEDDING
    ) -> EmbeddingProvider:
        """
        Resolve a logical model ID to an EmbeddingProvider instance.
        
        Args:
            model_id: The model ID, name, or slug
            required_capability: Expected capability type (for validation)
            
        Returns:
            An EmbeddingProvider instance ready for use
            
        Raises:
            ModelResolverError: If model not found, wrong capability, or no provider
        """
        logger.debug(f"Resolving embedding model {model_id} for tenant {self.tenant_id}")
        model = await self._get_model(model_id)
        
        if not model:
            raise ModelResolverError(f"Model not found: {model_id}")
        
        # Validate capability type
        if model.capability_type != required_capability:
            raise ModelResolverError(
                f"Model '{model.name}' has capability '{model.capability_type.value}', "
                f"expected '{required_capability.value}'"
            )
        
        # Check model status
        from app.db.postgres.models.registry import ModelStatus
        if model.status == ModelStatus.DEPRECATED:
            logger.warning(f"Model '{model.name}' is deprecated")
        elif model.status == ModelStatus.DISABLED:
            raise ModelResolverError(f"Model '{model.name}' is disabled")
        
        logger.info(f"Resolved embedding model: {model.name} ({model.id})")
        
        # Find active binding
        active_bindings = [b for b in model.providers if b.is_enabled]
        if not active_bindings:
            raise ModelResolverError(f"No active provider bindings for model: {model.name}")
        
        policy_data = model.default_resolution_policy or {}
        priority_order = [p.lower() for p in policy_data.get("priority", [])]
        if priority_order:
            def _sort_key(binding: ModelProviderBinding) -> tuple:
                provider_key = binding.provider.value if hasattr(binding.provider, "value") else str(binding.provider)
                provider_rank = priority_order.index(provider_key) if provider_key in priority_order else len(priority_order)
                return (provider_rank, binding.priority)
            active_bindings.sort(key=_sort_key)
            binding = active_bindings[0]
        else:
            binding = min(active_bindings, key=lambda x: x.priority)
        logger.info(f"Using provider: {binding.provider} -> {binding.provider_model_id}")

        credentials_payload, api_key, _ = await self._resolve_provider_credentials(
            binding,
            IntegrationCredentialCategory.LLM_PROVIDER,
        )

        merged_config = dict(binding.config or {})
        return self._create_embedding_provider_from_binding(
            binding,
            model,
            config=merged_config,
            credentials_payload=credentials_payload,
            api_key_override=api_key,
        )
    
    def _create_embedding_provider_from_binding(
        self,
        binding: ModelProviderBinding,
        model: ModelRegistry,
        config: Optional[dict] = None,
        credentials_payload: Optional[dict] = None,
        api_key_override: Optional[str] = None,
    ) -> EmbeddingProvider:
        """Create an EmbeddingProvider instance from a provider binding."""
        config = config or binding.config or {}
        credentials_payload = credentials_payload or {}
        api_key = api_key_override or config.get("api_key") or credentials_payload.get("api_key")
        
        # Get dimension from model metadata
        metadata = model.metadata_ or {}
        dimension = metadata.get("dimension")
        
        if binding.provider == ModelProviderType.OPENAI:
            return OpenAIEmbeddingProvider(
                api_key=api_key,
                model=binding.provider_model_id,
                dimensions=dimension,
            )
        elif binding.provider in (ModelProviderType.GOOGLE, ModelProviderType.GEMINI):
            task_type = config.get("task_type") or credentials_payload.get("task_type")
            return GeminiEmbeddingProvider(
                api_key=api_key,
                model=binding.provider_model_id,
                task_type=task_type or "QUESTION_ANSWERING",
            )
        elif binding.provider == ModelProviderType.HUGGINGFACE:
            return HuggingFaceEmbeddingProvider(
                model=binding.provider_model_id,
            )
        else:
            raise ModelResolverError(
                f"Unsupported embedding provider: {binding.provider}"
            )
    
    async def get_model_dimension(self, model_id: str) -> int:
        """
        Get the embedding dimension for a model.
        Used by pipeline compiler for validation.
        """
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
