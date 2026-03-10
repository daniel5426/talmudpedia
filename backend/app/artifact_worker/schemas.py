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
    inputs: Any = None
    config: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    bundle_hash: str | None = None
    bundle_storage_key: str | None = None
    dependency_hash: str | None = None
    dependency_manifest: list[str] = Field(default_factory=list)
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
    bundle_cache_hit: bool | None = None
    bundle_payload_source: str | None = None
    dependency_cache_hit: bool | None = None
    sandbox_backend: str | None = None
    sandbox_metadata: dict[str, Any] = Field(default_factory=dict)
