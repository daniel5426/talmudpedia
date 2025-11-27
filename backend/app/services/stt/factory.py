import os
from .base import STTProvider
from .google import GoogleChirpProvider

# Module-level singleton
_provider_instance: STTProvider | None = None

def get_stt_provider() -> STTProvider:
    """
    Returns the configured STT provider instance.
    Currently defaults to GoogleChirpProvider.
    """
    global _provider_instance
    
    if _provider_instance is None:
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is not set.")
        
        _provider_instance = GoogleChirpProvider(project_id=project_id)
    
    return _provider_instance
