import os
import json
from google.cloud import speech_v2
from google.cloud.speech_v2.types import cloud_speech
from google.oauth2 import service_account
from .base import STTProvider

class GoogleChirpProvider(STTProvider):
    """
    STT Provider using Google Cloud Speech-to-Text V2 (Chirp).
    """

    def __init__(self, project_id: str, location: str = "us"):
        self.project_id = project_id
        self.location = location
        
        credentials_value = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        
        if credentials_value:
            # Check if it's a file path or JSON content
            if credentials_value.strip().startswith('{'):
                # It's JSON content, parse it
                credentials_info = json.loads(credentials_value)
                credentials = service_account.Credentials.from_service_account_info(credentials_info)
            else:
                # It's a file path
                credentials = service_account.Credentials.from_service_account_file(credentials_value)
            
            # Use regional endpoint for chirp_3 support
            client_options = {"api_endpoint": f"{self.location}-speech.googleapis.com"}
            self.client = speech_v2.SpeechClient(credentials=credentials, client_options=client_options)
        else:
            # Fall back to default credentials with regional endpoint
            client_options = {"api_endpoint": f"{self.location}-speech.googleapis.com"}
            self.client = speech_v2.SpeechClient(client_options=client_options)

    async def transcribe(self, audio_content: bytes) -> str:
        """
        Transcribes audio using Google Cloud Speech-to-Text V2.
        """
        import asyncio
        
        # Build the configuration object
        config = cloud_speech.RecognitionConfig(
            auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
            language_codes=["en-US", "he-IL"],  # Support English and Hebrew
            model="chirp_3",
        )

        request = cloud_speech.RecognizeRequest(
            recognizer=f"projects/{self.project_id}/locations/{self.location}/recognizers/_",
            config=config,
            content=audio_content,
        )

        # Run the synchronous API call in a thread pool
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.client.recognize, request)

        transcription = ""
        for result in response.results:
            if result.alternatives:
                transcription += result.alternatives[0].transcript + " "

        return transcription.strip()
