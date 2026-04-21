from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID

from app.agent.execution.types import ExecutionMode
from app.db.postgres.models.agent_threads import AgentThreadSurface


class RuntimeEventView(str, Enum):
    internal_full = "internal_full"
    public_safe = "public_safe"


@dataclass(frozen=True)
class RuntimeThreadScope:
    organization_id: UUID | None
    project_id: UUID | None = None
    user_id: UUID | None = None
    app_account_id: UUID | None = None
    published_app_id: UUID | None = None
    agent_id: UUID | None = None
    external_user_id: str | None = None
    external_session_id: str | None = None


@dataclass(frozen=True)
class RuntimeSurfaceContext:
    organization_id: UUID
    project_id: UUID | None
    surface: AgentThreadSurface
    event_view: RuntimeEventView
    user_id: UUID | None = None
    request_user_id: str | None = None
    app_account_id: UUID | None = None
    published_app_id: UUID | None = None
    agent_id: UUID | None = None
    external_user_id: str | None = None
    external_session_id: str | None = None
    context_defaults: dict[str, Any] = field(default_factory=dict)

    def thread_scope(self, *, agent_id: UUID | None = None) -> RuntimeThreadScope:
        return RuntimeThreadScope(
            organization_id=self.organization_id,
            project_id=self.project_id,
            user_id=self.user_id,
            app_account_id=self.app_account_id,
            published_app_id=self.published_app_id,
            agent_id=agent_id or self.agent_id,
            external_user_id=self.external_user_id,
            external_session_id=self.external_session_id,
        )


@dataclass(frozen=True)
class RuntimeChatRequest:
    input: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    attachment_ids: list[str] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    client: dict[str, Any] = field(default_factory=dict)
    thread_id: UUID | None = None
    run_id: UUID | None = None

    def resume_payload(self) -> dict[str, Any]:
        payload = dict(self.context or {})
        if self.input and "input" not in payload:
            payload["input"] = self.input
        return payload


@dataclass(frozen=True)
class RuntimeStreamOptions:
    execution_mode: ExecutionMode
    preload_thread_messages: bool = False
    cleanup_transient_thread: bool = False
    stream_v2_enforced: bool = True
    padding_bytes: int = 4096
    include_content_encoding_identity: bool = False
    include_run_id_header: bool = False
    include_thread_header: bool = True
    extra_headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeThreadOptions:
    before_turn_index: int | None = None
    limit: int = 20
    include_subthreads: bool = False
    subthread_depth: int = 1
    subthread_turn_limit: int | None = None
    subthread_child_limit: int = 20


@dataclass(frozen=True)
class RuntimeRunControlContext:
    organization_id: UUID
    project_id: UUID | None = None
    user_id: UUID | None = None
    is_service: bool = False
    is_platform_admin: bool = False
