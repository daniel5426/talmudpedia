from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ArtifactWorkerExecutionRequest(BaseModel):
    run_id: UUID
    tenant_id: UUID
    artifact_id: UUID | None = None
    revision_id: UUID
    domain: str = "test"
    inputs: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    resource_limits: dict[str, Any] = Field(default_factory=dict)


class ArtifactWorkerExecutionResponse(BaseModel):
    status: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    stdout_excerpt: str | None = None
    stderr_excerpt: str | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int | None = None
    worker_id: str | None = None
    sandbox_session_id: str | None = None
