from abc import ABC, abstractmethod

class STTProvider(ABC):
    """Abstract base class for Speech-to-Text providers."""

    @abstractmethod
    async def transcribe(self, audio_content: bytes) -> str:
        """
        Transcribes the given audio content.

        Args:
            audio_content: The audio data in bytes.

        Returns:
            The transcribed text as a string.
        """
        pass
