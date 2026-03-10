from __future__ import annotations

import os

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.artifact_worker.executor import ArtifactWorkerExecutor
from app.artifact_worker.schemas import ArtifactWorkerExecutionRequest, ArtifactWorkerExecutionResponse


class DifySandboxWorkerClient:
    def __init__(self, db: AsyncSession | None = None):
        self._db = db

    def _mode(self) -> str:
        explicit = str(os.getenv("ARTIFACT_WORKER_CLIENT_MODE") or "").strip().lower()
        if explicit in {"direct", "http"}:
            return explicit
        if os.getenv("ARTIFACT_WORKER_BASE_URL"):
            return "http"
        return "direct"

    async def execute(self, request: ArtifactWorkerExecutionRequest) -> ArtifactWorkerExecutionResponse:
        if self._mode() == "http":
            return await self._execute_http(request)
        if self._db is None:
            raise RuntimeError("Direct artifact worker client requires a database session")
        executor = ArtifactWorkerExecutor()
        return await executor.execute(self._db, request)

    async def cancel(self, sandbox_session_id: str) -> None:
        if self._mode() == "http":
            await self._cancel_http(sandbox_session_id)
            return
        executor = ArtifactWorkerExecutor()
        executor.cancel(sandbox_session_id)

    async def _execute_http(self, request: ArtifactWorkerExecutionRequest) -> ArtifactWorkerExecutionResponse:
        base_url = str(os.getenv("ARTIFACT_WORKER_BASE_URL") or "").strip().rstrip("/")
        if not base_url:
            raise RuntimeError("ARTIFACT_WORKER_BASE_URL is required for HTTP artifact worker mode")
        timeout_seconds = float(os.getenv("ARTIFACT_WORKER_HTTP_TIMEOUT_SECONDS") or "60")
        headers = {}
        token = str(os.getenv("ARTIFACT_WORKER_INTERNAL_TOKEN") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                f"{base_url}/internal/artifact-worker/runs/execute",
                json=request.model_dump(mode="json"),
                headers=headers,
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.strip() or exc.__class__.__name__
            raise RuntimeError(f"Artifact worker request failed ({response.status_code}): {detail}") from exc
        return ArtifactWorkerExecutionResponse.model_validate(response.json())

    async def _cancel_http(self, sandbox_session_id: str) -> None:
        base_url = str(os.getenv("ARTIFACT_WORKER_BASE_URL") or "").strip().rstrip("/")
        if not base_url:
            raise RuntimeError("ARTIFACT_WORKER_BASE_URL is required for HTTP artifact worker mode")
        timeout_seconds = float(os.getenv("ARTIFACT_WORKER_HTTP_TIMEOUT_SECONDS") or "15")
        headers = {}
        token = str(os.getenv("ARTIFACT_WORKER_INTERNAL_TOKEN") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                f"{base_url}/internal/artifact-worker/runs/{sandbox_session_id}/cancel",
                headers=headers,
            )
        response.raise_for_status()
