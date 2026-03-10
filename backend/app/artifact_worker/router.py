from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.session import get_db

from .executor import ArtifactWorkerExecutor
from .schemas import ArtifactWorkerExecutionRequest, ArtifactWorkerExecutionResponse


router = APIRouter(prefix="/internal/artifact-worker", tags=["internal-artifact-worker"])


def _require_internal_token(authorization: str | None = Header(None)) -> None:
    expected = str(os.getenv("ARTIFACT_WORKER_INTERNAL_TOKEN") or "").strip()
    if not expected:
        return
    raw = str(authorization or "")
    token = raw.replace("Bearer ", "", 1).strip() if raw.lower().startswith("bearer ") else raw.strip()
    if token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal worker token")


@router.post("/runs/execute", response_model=ArtifactWorkerExecutionResponse)
async def execute_artifact_run(
    request: ArtifactWorkerExecutionRequest,
    _: None = Depends(_require_internal_token),
    db: AsyncSession = Depends(get_db),
):
    executor = ArtifactWorkerExecutor()
    return await executor.execute(db, request)


@router.post("/runs/{sandbox_session_id}/cancel")
async def cancel_artifact_run(
    sandbox_session_id: str,
    _: None = Depends(_require_internal_token),
):
    executor = ArtifactWorkerExecutor()
    try:
        executor.cancel(sandbox_session_id)
    except ProcessLookupError:
        raise HTTPException(status_code=404, detail="Sandbox session not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "cancelled", "sandbox_session_id": sandbox_session_id}
