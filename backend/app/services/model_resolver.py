"""
Model Resolver - Late-bound resolution of logical models to providers.

Implements policy-driven model resolution with fallback, compliance,
and cost tier support. Now uses PostgreSQL.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.registry import ModelRegistry, ModelProviderType
from app.agent.core.interfaces import LLMProvider
from app.agent.components.llm.openai import OpenAILLM
from app.agent.components.llm.gemini import GeminiLLM


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
        model = await self._get_model(model_id)
        if not model:
            raise ModelResolverError(f"Model not found: {model_id}")
        
        # Use override policy or defaults
        policy = policy_override or ModelResolutionPolicy()
        
        # Create provider instance
        try:
            return self._create_provider_instance(model)
        except Exception as e:
            if policy.fallback_enabled:
                # Try to find an alternative model
                fallback = await self._get_fallback_model(model)
                if fallback:
                    return self._create_provider_instance(fallback)
            raise ModelResolverError(f"Provider failed: {e}")
    
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
        
        raise ModelResolverError(f"All models in fallback chain failed: {all_models}")
    
    async def _get_model(self, model_id: str) -> Optional[ModelRegistry]:
        """Fetch model by ID, name, or as UUID."""
        # Try as UUID first
        try:
            model_uuid = UUID(model_id)
            query = select(ModelRegistry).where(
                ModelRegistry.id == model_uuid,
                ModelRegistry.is_active == True,
                # Allow tenant-specific or global (null tenant_id) models
                (ModelRegistry.tenant_id == self.tenant_id) | (ModelRegistry.tenant_id.is_(None))
            )
            result = await self.db.execute(query)
            model = result.scalar_one_or_none()
            if model:
                return model
        except (ValueError, AttributeError):
            pass
        
        # Try by name
        query = select(ModelRegistry).where(
            ModelRegistry.name == model_id,
            ModelRegistry.is_active == True,
            (ModelRegistry.tenant_id == self.tenant_id) | (ModelRegistry.tenant_id.is_(None))
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def _get_fallback_model(self, failed_model: ModelRegistry) -> Optional[ModelRegistry]:
        """Get a fallback model of the same provider type."""
        query = select(ModelRegistry).where(
            ModelRegistry.provider == failed_model.provider,
            ModelRegistry.is_active == True,
            ModelRegistry.id != failed_model.id,
            (ModelRegistry.tenant_id == self.tenant_id) | (ModelRegistry.tenant_id.is_(None))
        ).limit(1)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    def _create_provider_instance(self, model: ModelRegistry) -> LLMProvider:
        """Create an LLMProvider instance from model registry entry."""
        metadata = model.metadata_ or {}
        api_key = metadata.get("api_key")  # In production, should come from secrets
        config = {k: v for k, v in metadata.items() if k != "api_key"}
        
        if model.provider == ModelProviderType.OPENAI:
            return OpenAILLM(
                model=model.name,
                api_key=api_key,
                **config
            )
        elif model.provider == ModelProviderType.GOOGLE:
            return GeminiLLM(
                model=model.name,
                **config
            )
        else:
            raise ModelResolverError(f"Unsupported provider type: {model.provider}")
    
    def clear_cache(self):
        """Clear the provider cache."""
        self._provider_cache.clear()
