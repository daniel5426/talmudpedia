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

from app.db.postgres.models.registry import ModelRegistry, ModelProviderType, ModelProviderBinding, ModelCapabilityType
from app.agent.core.interfaces import LLMProvider
from app.agent.components.llm.openai import OpenAILLM
from app.agent.components.llm.gemini import GeminiLLM
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
    - Provider priority ordering
    - Automatic fallback on failure
    - Compliance tag filtering
    - Cost tier selection
    """
    
    def __init__(self, db: AsyncSession, tenant_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self._provider_cache: dict[str, LLMProvider] = {}
    
    async def resolve(
        self,
        model_id: str,
        policy_override: Optional[ModelResolutionPolicy] = None
    ) -> LLMProvider:
        """
        Resolve a logical model ID to a provider instance.
        
        Args:
            model_id: The model ID, name, or slug
            policy_override: Optional policy to override model defaults
            
        Returns:
            An LLMProvider instance ready for use
            
        Raises:
            ModelResolverError: If no suitable provider found
        """
        # Fetch model from registry
        logger.debug(f"Resolving model {model_id} for tenant {self.tenant_id}")
        model = await self._get_model(model_id)
        if not model:
            logger.error(f"Model resolution failed: Model {model_id} not found for tenant {self.tenant_id} (or global)")
            raise ModelResolverError(f"Model not found: {model_id}")
        
        logger.info(f"Resolved logical model: {model.name} ({model.id})")

        # Determine which provider to use
        # 1. Search for active bindings
        active_bindings = [b for b in model.providers if b.is_enabled]
        logger.debug(f"Found {len(active_bindings)} active bindings for model {model.name}")
        
        if active_bindings:
            # Pick highest priority (lowest value)
            binding = min(active_bindings, key=lambda x: x.priority)
            logger.info(f"Selecting binding: {binding.provider} -> {binding.provider_model_id} (priority: {binding.priority})")
            try:
                return self._create_provider_instance_from_binding(binding)
            except Exception as e:
                logger.error(f"Failed to create provider from binding {binding.id}: {e}")
                # If fallback is enabled, we could try other bindings or other models
                pass

        # 2. Policy-driven fallback
        policy = policy_override or ModelResolutionPolicy()
        if policy.fallback_enabled:
            logger.warning(f"No active bindings found for {model.name}. Attempting policy-driven fallback.")
            fallback = await self._get_fallback_model(model)
            if fallback:
                logger.info(f"Falling back to model: {fallback.name} ({fallback.id})")
                return await self.resolve(str(fallback.id))
        
        logger.error(f"Resolution failed: No suitable provider found for model: {model_id}")
        raise ModelResolverError(f"No suitable provider found for model: {model_id}")
    
    async def resolve_with_fallback(
        self,
        model_id: str,
        fallback_model_ids: list[str]
    ) -> LLMProvider:
        """
        Resolve model with explicit fallback chain.
        """
        all_models = [model_id] + fallback_model_ids
        logger.info(f"Resolving model chain: {all_models}")
        
        for mid in all_models:
            try:
                resolved = await self.resolve(mid)
                logger.info(f"Successfully resolved model {mid} in fallback chain")
                return resolved
            except ModelResolverError as e:
                logger.warning(f"Failed to resolve model {mid} in fallback chain: {e}")
                continue
        
        logger.error(f"All models in fallback chain failed: {all_models}")
        raise ModelResolverError(f"All models in fallback chain failed: {all_models}")
    
    async def _get_model(self, model_id: str) -> Optional[ModelRegistry]:
        """Fetch model by ID, name, or as UUID with providers loaded."""
        # Try as UUID first
        try:
            model_uuid = UUID(model_id)
            logger.debug(f"Searching for model by UUID: {model_uuid}")
            query = select(ModelRegistry).where(
                ModelRegistry.id == model_uuid,
                ModelRegistry.is_active == True,
                # Allow tenant-specific or global (null tenant_id) models
                or_(ModelRegistry.tenant_id == self.tenant_id, ModelRegistry.tenant_id.is_(None))
            ).options(selectinload(ModelRegistry.providers))
            result = await self.db.execute(query)
            model = result.scalar_one_or_none()
            if model:
                logger.debug(f"Found model by UUID: {model.name}")
                return model
        except (ValueError, AttributeError):
            pass
        
        # Try by name/slug
        logger.debug(f"Searching for model by name/slug: {model_id}")
        query = select(ModelRegistry).where(
            or_(ModelRegistry.name == model_id, ModelRegistry.slug == model_id),
            ModelRegistry.is_active == True,
            or_(ModelRegistry.tenant_id == self.tenant_id, ModelRegistry.tenant_id.is_(None))
        ).options(selectinload(ModelRegistry.providers))
        result = await self.db.execute(query)
        model = result.scalar_one_or_none()
        if model:
            logger.debug(f"Found model by name/slug: {model.name} (ID: {model.id})")
        else:
            logger.debug(f"Model not found for ID/Name: {model_id}")
        return model
    
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
    
    def _create_provider_instance_from_binding(self, binding: ModelProviderBinding) -> LLMProvider:
        """Create an LLMProvider instance from a provider binding."""
        config = binding.config or {}
        # In production, credentials should be fetched via binding.credentials_ref
        # For now, we fall back to environment variables or binding config
        api_key = config.get("api_key")
        
        if binding.provider == ModelProviderType.OPENAI:
            return OpenAILLM(
                model=binding.provider_model_id,
                api_key=api_key,
                **{k: v for k, v in config.items() if k != "api_key"}
            )
        elif binding.provider == ModelProviderType.GOOGLE or binding.provider == ModelProviderType.GEMINI:
            return GeminiLLM(
                model=binding.provider_model_id,
                **{k: v for k, v in config.items() if k != "api_key"}
            )
        else:
            raise ModelResolverError(f"Unsupported provider type in binding: {binding.provider}")

    def clear_cache(self):
        """Clear the provider cache."""
        self._provider_cache.clear()
    
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
        
        binding = min(active_bindings, key=lambda x: x.priority)
        logger.info(f"Using provider: {binding.provider} -> {binding.provider_model_id}")
        
        return self._create_embedding_provider_from_binding(binding, model)
    
    def _create_embedding_provider_from_binding(
        self,
        binding: ModelProviderBinding,
        model: ModelRegistry
    ) -> EmbeddingProvider:
        """Create an EmbeddingProvider instance from a provider binding."""
        config = binding.config or {}
        api_key = config.get("api_key")
        
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
            return GeminiEmbeddingProvider(
                api_key=api_key,
                model=binding.provider_model_id,
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

