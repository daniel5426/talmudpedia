from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from uuid import UUID
from fastapi import WebSocket

class BaseVoiceSession(ABC):
    """
    Abstract base class for all speech-to-speech voice providers.
    """
    
    def __init__(self, chat_id: Optional[str] = None, tenant_id: Optional[UUID] = None, user_id: Optional[UUID] = None):
        self.chat_id = chat_id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.frontend_ws: Optional[WebSocket] = None

    @abstractmethod
    async def connect(self, frontend_ws: WebSocket):
        """Establish connection to the provider."""
        pass

    @abstractmethod
    async def send_audio(self, audio_chunk_base64: str):
        """Send audio to the provider."""
        pass

    @abstractmethod
    async def send_user_text(self, text: str, turn_complete: bool = True):
        """Send user text to the provider."""
        pass

    @abstractmethod
    async def receive_loop(self, frontend_ws: WebSocket):
        """Loop for receiving data from provider and sending to frontend."""
        pass

    @abstractmethod
    async def close(self):
        """Close connections and cleanup."""
        pass
