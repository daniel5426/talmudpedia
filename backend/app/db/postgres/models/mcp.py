from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text

from ..base import Base


class McpAuthMode(str, enum.Enum):
    NONE = "none"
    STATIC_BEARER = "static_bearer"
    STATIC_HEADERS = "static_headers"
    OAUTH_USER_ACCOUNT = "oauth_user_account"


class McpSyncStatus(str, enum.Enum):
    NEVER_SYNCED = "never_synced"
    READY = "ready"
    AUTH_REQUIRED = "auth_required"
    ERROR = "error"


class McpAccountConnectionStatus(str, enum.Enum):
    PENDING = "pending"
    ACTIVE = "active"
    STALE = "stale"
    REVOKED = "revoked"
    ERROR = "error"


class McpApprovalPolicy(str, enum.Enum):
    ASK = "ask"
    ALWAYS_ALLOW = "always_allow"


class McpServer(Base):
    __tablename__ = "mcp_servers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    server_url = Column(Text, nullable=False)
    transport = Column(String, nullable=False, default="streamable_http", server_default=text("'streamable_http'"))
    auth_mode = Column(String, nullable=False, default=McpAuthMode.NONE.value, server_default=text("'none'"), index=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    static_bearer_token_encrypted = Column(Text, nullable=True)
    static_headers_encrypted = Column(Text, nullable=True)

    auth_config = Column(JSONB, nullable=False, default=dict)
    auth_metadata = Column(JSONB, nullable=False, default=dict)
    capability_snapshot = Column(JSONB, nullable=False, default=dict)

    oauth_client_id = Column(Text, nullable=True)
    oauth_client_secret_encrypted = Column(Text, nullable=True)
    oauth_client_registration = Column(JSONB, nullable=False, default=dict)
    oauth_client_secret_expires_at = Column(DateTime(timezone=True), nullable=True)

    tool_snapshot_version = Column(Integer, nullable=False, default=0, server_default=text("0"))
    sync_status = Column(
        String,
        nullable=False,
        default=McpSyncStatus.NEVER_SYNCED.value,
        server_default=text("'never_synced'"),
        index=True,
    )
    sync_error = Column(Text, nullable=True)
    last_tested_at = Column(DateTime(timezone=True), nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant")
    creator = relationship("User")
    discovered_tools = relationship("McpDiscoveredTool", back_populates="server", cascade="all, delete-orphan")
    agent_mounts = relationship("McpAgentMount", back_populates="server", cascade="all, delete-orphan")
    account_connections = relationship("McpUserAccountConnection", back_populates="server", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_mcp_servers_tenant_name"),
        Index("ix_mcp_servers_tenant_active", "tenant_id", "is_active"),
    )


class McpDiscoveredTool(Base):
    __tablename__ = "mcp_discovered_tools"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    server_id = Column(UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False, index=True)

    snapshot_version = Column(Integer, nullable=False, index=True)
    name = Column(String, nullable=False)
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    input_schema = Column(JSONB, nullable=False, default=dict)
    annotations = Column(JSONB, nullable=False, default=dict)
    tool_metadata = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tenant = relationship("Tenant")
    server = relationship("McpServer", back_populates="discovered_tools")

    __table_args__ = (
        UniqueConstraint(
            "server_id",
            "snapshot_version",
            "name",
            name="uq_mcp_discovered_tools_server_snapshot_name",
        ),
        Index(
            "ix_mcp_discovered_tools_server_snapshot",
            "server_id",
            "snapshot_version",
        ),
    )


class McpAgentMount(Base):
    __tablename__ = "mcp_agent_mounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    server_id = Column(UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    applied_snapshot_version = Column(Integer, nullable=False, default=0, server_default=text("0"))
    approval_policy = Column(
        String,
        nullable=False,
        default=McpApprovalPolicy.ASK.value,
        server_default=text("'ask'"),
    )
    tool_filters = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant")
    agent = relationship("Agent")
    server = relationship("McpServer", back_populates="agent_mounts")
    creator = relationship("User")

    __table_args__ = (
        UniqueConstraint("agent_id", "server_id", name="uq_mcp_agent_mounts_agent_server"),
        Index("ix_mcp_agent_mounts_agent_active", "agent_id", "is_active"),
    )


class McpUserAccountConnection(Base):
    __tablename__ = "mcp_user_account_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    server_id = Column(UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(
        String,
        nullable=False,
        default=McpAccountConnectionStatus.PENDING.value,
        server_default=text("'pending'"),
        index=True,
    )
    token_payload_encrypted = Column(Text, nullable=True)
    scopes = Column(JSONB, nullable=False, default=list)
    account_metadata = Column(JSONB, nullable=False, default=dict)
    last_error = Column(Text, nullable=True)
    access_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    refresh_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    last_refreshed_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tenant = relationship("Tenant")
    server = relationship("McpServer", back_populates="account_connections")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("server_id", "user_id", name="uq_mcp_user_account_connections_server_user"),
        Index("ix_mcp_user_account_connections_user_status", "user_id", "status"),
    )


class McpOauthState(Base):
    __tablename__ = "mcp_oauth_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    server_id = Column(UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    state = Column(String, nullable=False, unique=True, index=True)
    code_verifier = Column(Text, nullable=False)
    redirect_uri = Column(Text, nullable=False)
    client_id = Column(Text, nullable=False)
    requested_scopes = Column(JSONB, nullable=False, default=list)
    auth_server_metadata = Column(JSONB, nullable=False, default=dict)
    token_method = Column(String, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tenant = relationship("Tenant")
    server = relationship("McpServer")
    user = relationship("User")

    __table_args__ = (
        Index("ix_mcp_oauth_states_server_user", "server_id", "user_id"),
        Index("ix_mcp_oauth_states_expires_at", "expires_at"),
    )
