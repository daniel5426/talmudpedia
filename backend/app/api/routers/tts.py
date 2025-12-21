import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openai import AsyncOpenAI


class TTSRequest(BaseModel):
    text: str


router = APIRouter()


@router.post("/speak")
async def synthesize_speech(payload: TTSRequest):
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    model = os.getenv("LIVEKIT_TTS_MODEL") or "gpt-4o-mini-tts"
    voice = os.getenv("LIVEKIT_TTS_VOICE") or "ash"
    instructions = os.getenv("LIVEKIT_TTS_INSTRUCTIONS")

    client = AsyncOpenAI()

    async def audio_stream():
        try:
            kwargs = {
                "model": model,
                "voice": voice,
                "input": text,
                "response_format": "mp3",
            }
            if instructions:
                kwargs["instructions"] = instructions

            async with client.audio.speech.with_streaming_response.create(**kwargs) as resp:
                async for chunk in resp.iter_bytes():
                    yield chunk
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return StreamingResponse(audio_stream(), media_type="audio/mpeg")
