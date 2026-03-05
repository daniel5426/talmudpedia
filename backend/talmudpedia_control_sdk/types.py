from __future__ import annotations

from typing import Any, Dict, Optional, TypedDict


class RequestMetadata(TypedDict, total=False):
    reason: str
    source: str
    trace_id: str
    actor_hint: str


class RequestOptions(TypedDict, total=False):
    idempotency_key: str
    dry_run: bool
    validate_only: bool
    request_metadata: RequestMetadata


class ResponseMeta(TypedDict, total=False):
    request_id: str
    trace_id: str
    idempotency_reused: bool
    warnings: list[str]


class ResponseEnvelope(TypedDict, total=False):
    data: Any
    meta: ResponseMeta
    errors: list[Dict[str, Any]]
