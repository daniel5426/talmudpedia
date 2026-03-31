from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.session import get_db
from app.services.speech_to_text_service import SpeechToTextService


router = APIRouter()


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        audio_content = await file.read()
        result, _execution = await SpeechToTextService(db, None).transcribe_bytes(
            audio_content,
            mime_type=file.content_type,
            filename=file.filename,
        )
        return {"text": result.text}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
