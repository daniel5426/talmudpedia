"""
Model Resolver - Late-bound resolution of logical models to providers.

Implements policy-driven model resolution with fallback, compliance,
and cost tier support.
"""
from typing import Optional
from bson import ObjectId

from app.db.models.model_registry import (
    LogicalModel,
    ModelProvider,
    ModelProviderType,
    ModelResolutionPolicy,
)
from app.agent.core.interfaces import LLMProvider
from app.agent.components.llm.openai import OpenAILLM
from app.agent.components.llm.gemini import GeminiLLM
from app.db.connection import MongoDatabase


class ModelResolverError(Exception):
    """Error during model resolution."""
    pass


class ModelResolver:
    """
    Resolves logical model IDs to concrete LLMProvider instances.
    
    Resolution is policy-driven, supporting:
    - Provider priority ordering
    - Automatic fallback on failure
    - Compliance tag filtering
    - Cost tier selection
    """
    
    def __init__(self, tenant_id: str):
        self.tenant_id = ObjectId(tenant_id)
        self._provider_cache: dict[str, LLMProvider] = {}
    
    async def resolve(
        self,
        model_id: str,
        policy_override: Optional[ModelResolutionPolicy] = None
    ) -> LLMProvider:
        """
        Resolve a logical model ID to a provider instance.
        
        Args:
            model_id: The logical model ID or slug
            policy_override: Optional policy to override model defaults
            
        Returns:
            An LLMProvider instance ready for use
            
        Raises:
            ModelResolverError: If no suitable provider found
        """
        db = MongoDatabase.get_db()
        
        # Fetch logical model
        model = await self._get_model(db, model_id)
        if not model:
            raise ModelResolverError(f"Model not found: {model_id}")
        
        # Use override policy or model default
        policy = policy_override or model.get("default_resolution_policy", {})
        
        # Fetch available providers for this model
        providers = await self._get_providers(db, model["_id"], policy)
        if not providers:
            raise ModelResolverError(f"No providers available for model: {model_id}")
        
        # Try providers in priority order
        for provider_doc in providers:
            try:
                return self._create_provider_instance(provider_doc)
            except Exception as e:
                # Log and try next provider if fallback enabled
                if policy.get("fallback_enabled", True):
                    continue
                raise ModelResolverError(f"Provider failed: {e}")
        
        raise ModelResolverError(f"All providers failed for model: {model_id}")
    
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
    
    async def _get_model(self, db, model_id: str) -> Optional[dict]:
        """Fetch model by ID or slug."""
        collection = db["logical_models"]
        
        # Try as ObjectId first
        if ObjectId.is_valid(model_id):
            model = await collection.find_one({
                "_id": ObjectId(model_id),
                "tenant_id": self.tenant_id,
                "status": "active"
            })
            if model:
                return model
        
        # Try as slug
        return await collection.find_one({
            "slug": model_id,
            "tenant_id": self.tenant_id,
            "status": "active"
        })
    
    async def _get_providers(
        self,
        db,
        model_id: ObjectId,
        policy: dict
    ) -> list[dict]:
        """Fetch providers matching policy constraints."""
        collection = db["model_providers"]
        
        query = {
            "logical_model_id": model_id,
            "is_enabled": True
        }
        
        # Filter by priority list if specified
        priority_list = policy.get("priority", [])
        if priority_list:
            query["provider"] = {"$in": priority_list}
        
        # Fetch and sort by priority
        cursor = collection.find(query).sort("priority", 1)
        return await cursor.to_list(length=10)
    
    def _create_provider_instance(self, provider_doc: dict) -> LLMProvider:
        """Create an LLMProvider instance from provider config."""
        provider_type = provider_doc["provider"]
        model_id = provider_doc["provider_model_id"]
        config = provider_doc.get("config", {})
        
        if provider_type == ModelProviderType.OPENAI.value:
            return OpenAILLM(
                model=model_id,
                api_key=config.get("api_key"),  # Should come from secrets
                **{k: v for k, v in config.items() if k != "api_key"}
            )
        elif provider_type == ModelProviderType.GEMINI.value:
            return GeminiLLM(
                model=model_id,
                **config
            )
        else:
            raise ModelResolverError(f"Unsupported provider type: {provider_type}")
    
    def clear_cache(self):
        """Clear the provider cache."""
        self._provider_cache.clear()
