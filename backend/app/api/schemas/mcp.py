from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class McpServerCreateRequest(BaseModel):
    name: str
    description: str | None = None
    server_url: str
    auth_mode: str = "none"
    static_bearer_token: str | None = None
    static_headers: dict[str, str] | None = None
    auth_config: dict[str, Any] = Field(default_factory=dict)
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    is_active: bool = True


class McpServerUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    server_url: str | None = None
    auth_mode: str | None = None
    static_bearer_token: str | None = None
    static_headers: dict[str, str] | None = None
    auth_config: dict[str, Any] | None = None
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    is_active: bool | None = None


class McpServerResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    server_url: str
    transport: str
    auth_mode: str
    is_active: bool
    auth_config: dict[str, Any]
    auth_metadata: dict[str, Any]
    capability_snapshot: dict[str, Any]
    oauth_client_id: str | None
    oauth_client_registration: dict[str, Any]
    tool_snapshot_version: int
    sync_status: str
    sync_error: str | None
    last_tested_at: datetime | None
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime
    has_static_bearer_token: bool
    has_static_headers: bool
    has_oauth_client_secret: bool


class McpDiscoveredToolResponse(BaseModel):
    id: UUID
    server_id: UUID
    snapshot_version: int
    name: str
    title: str | None
    description: str | None
    input_schema: dict[str, Any]
    annotations: dict[str, Any]
    tool_metadata: dict[str, Any]
    created_at: datetime


class McpAccountConnectionResponse(BaseModel):
    server_id: UUID
    user_id: UUID
    status: str
    scopes: list[Any]
    account_metadata: dict[str, Any]
    last_error: str | None
    access_token_expires_at: datetime | None
    refresh_token_expires_at: datetime | None
    last_refreshed_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


class McpAgentMountCreateRequest(BaseModel):
    server_id: UUID
    approval_policy: str = "ask"


class McpAgentMountUpdateRequest(BaseModel):
    approval_policy: str | None = None
    is_active: bool | None = None
    apply_latest_snapshot: bool = False


class McpAgentMountResponse(BaseModel):
    id: UUID
    agent_id: UUID
    server_id: UUID
    applied_snapshot_version: int
    approval_policy: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class McpAuthStartResponse(BaseModel):
    authorization_url: str
