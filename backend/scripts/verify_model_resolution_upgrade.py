
import asyncio
import uuid
from unittest.mock import AsyncMock, Mock, MagicMock

# Define simple mocks for our data models
class MockModel:
    def __init__(self, id, name, tenant_id=None, providers=None, capability_type="chat"):
        self.id = id
        self.name = name
        self.tenant_id = tenant_id
        self.providers = providers or []
        self.capability_type = capability_type
        self.status = "active"
        self.metadata_ = {}

class MockBinding:
    def __init__(self, provider, provider_model_id, tenant_id=None, priority=0, is_enabled=True, config=None):
        self.id = uuid.uuid4()
        self.provider = provider
        self.provider_model_id = provider_model_id
        self.tenant_id = tenant_id
        self.priority = priority
        self.is_enabled = is_enabled
        self.config = config or {}

class MockProviderConfig:
    def __init__(self, provider, tenant_id=None, provider_variant=None, credentials=None, is_enabled=True):
        self.id = uuid.uuid4()
        self.provider = provider
        self.tenant_id = tenant_id
        self.provider_variant = provider_variant
        self.credentials = credentials or {}
        self.is_enabled = is_enabled

# Mock the Resolver dependencies
async def test_resolution():
    print("Starting Verification...")
    
    # 1. Setup Data
    tenant_id = uuid.uuid4()
    
    # Global Model with Global Binding
    global_binding = MockBinding("openai", "gpt-4o", tenant_id=None, priority=0)
    model = MockModel(uuid.uuid4(), "GPT-4o", providers=[global_binding])
    
    # Mock DB Session
    mock_db = AsyncMock()
    
    # Import Resolver (we need the actual class code, but we will patch DB calls)
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from app.services.model_resolver import ModelResolver, ModelResolverError
    
    resolver = ModelResolver(mock_db, tenant_id)
    
    # --- Test Case 1: Standard Global Resolution ---
    print("\nTest 1: Global Binding Resolution")
    resolver._get_model = AsyncMock(return_value=model)
    resolver._get_provider_config = AsyncMock(return_value=MockProviderConfig("openai", credentials={"api_key": "global-key"}))
    resolver._create_provider_instance = AsyncMock(return_value="Success")
    
    res = await resolver.resolve("GPT-4o")
    assert res == "Success"
    print("✅ System Binding used.")

    # --- Test Case 2: Tenant Override ---
    print("\nTest 2: Tenant Binding Override")
    tenant_binding = MockBinding("openai", "gpt-4o-tenant", tenant_id=tenant_id, priority=0)
    model.providers.append(tenant_binding) # Now has both
    
    # Reset mocks
    resolver._get_model = AsyncMock(return_value=model)
    
    # We need to spy on _resolve_binding or check which binding was passed to _create_provider_instance
    resolver._create_provider_instance = AsyncMock(return_value="Success")
    
    await resolver.resolve("GPT-4o")
    
    # detailed check
    # The resolver should have picked the tenant binding
    # We can inspect the binding passed to _create_provider_instance
    call_args = resolver._create_provider_instance.call_args
    binding_used = call_args[0][0]
    assert binding_used.provider_model_id == "gpt-4o-tenant"
    print("✅ Tenant Binding prioritized over Global.")

    # --- Test Case 3: Tenant Disabled -> No Fallback ---
    print("\nTest 3: Tenant Disabled (Strict Guardrail)")
    tenant_binding.is_enabled = False
    # Global binding is still enabled
    
    # Mock fallback to return None for now to trigger the error we want
    resolver._get_fallback_model = AsyncMock(return_value=None)
    
    try:
        await resolver.resolve("GPT-4o")
        print("❌ FAILED: Should have raised error but succeeded.")
    except ModelResolverError:
         print("✅ Correctly rejected disabled tenant binding without falling back to global.")

    # --- Test Case 4: Config Merge ---
    print("\nTest 4: Config Merge (ProviderConfig + Binding)")
    tenant_binding.is_enabled = True
    
    # Binding has model params
    tenant_binding.config = {"temperature": 0.7, "provider_variant": "azure"}
    
    # ProviderConfig has creds
    provider_config = MockProviderConfig("openai", tenant_id, "azure", {"api_key": "azure-key", "base_url": "https://azure.com"})
    
    resolver._get_model = AsyncMock(return_value=model)
    resolver._get_provider_config = AsyncMock(return_value=provider_config)
    
    # Mock instantiation
    from app.agent.components.llm.openai import OpenAILLM
    resolver._create_provider_instance = ModelResolver._create_provider_instance.__get__(resolver, ModelResolver) 
    
    # Mock OpenAILLM to avoid pydantic validation errors or network calls
    # (No code needed here, we are calling _create_provider_instance directly below)
        
    # We can't easily mock OpenAILLM init without patching, so let's just inspect the logic of _create_provider_instance manually in the test
    # by calling it directly
    
    provider_instance = await resolver._create_provider_instance(tenant_binding)
    
    print(f"Captured API Key: {provider_instance.client.api_key}")
    print(f"Captured Base URL: {provider_instance.client.base_url}")
    print(f"Captured Temperature (Default Kwargs): {provider_instance.default_kwargs['temperature']}")
    
    assert provider_instance.client.api_key == "azure-key"
    assert str(provider_instance.client.base_url) == "https://azure.com"
    assert provider_instance.default_kwargs['temperature'] == 0.7
    print("✅ Config merged correctly.")

if __name__ == "__main__":
    asyncio.run(test_resolution())
