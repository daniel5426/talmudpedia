from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.services.stt.base import STTProvider
from app.services.stt.factory import get_stt_provider

router = APIRouter()

@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    stt_provider: STTProvider = Depends(get_stt_provider)
):
    """
    Transcribes an uploaded audio file using the configured STT provider.
    """
    try:
        audio_content = await file.read()
        transcript = await stt_provider.transcribe(audio_content)
        return {"text": transcript}
    except Exception as e:
        print(f"Transcription error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
