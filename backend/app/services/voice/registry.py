from typing import Dict, Type, Optional
from .base import BaseVoiceSession

class VoiceProviderRegistry:
    """Registry for voice session providers."""
    
    _providers: Dict[str, Type[BaseVoiceSession]] = {}

    @classmethod
    def register(cls, name: str, provider_class: Type[BaseVoiceSession]):
        cls._providers[name] = provider_class

    @classmethod
    def get_provider(cls, name: str) -> Optional[Type[BaseVoiceSession]]:
        return cls._providers.get(name)

# Helper to automatically discover/register providers if needed or manually register them
def get_voice_session(provider_name: str, **kwargs) -> BaseVoiceSession:
    provider_class = VoiceProviderRegistry.get_provider(provider_name)
    if not provider_class:
        raise ValueError(f"Voice provider '{provider_name}' not found.")
    return provider_class(**kwargs)
