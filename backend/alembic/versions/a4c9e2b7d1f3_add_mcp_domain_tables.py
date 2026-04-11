"""add mcp domain tables

Revision ID: a4c9e2b7d1f3
Revises: 6f4a7b2c9d1e, c5d6e7f8a9b0
Create Date: 2026-04-12 14:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "a4c9e2b7d1f3"
down_revision: Union[str, Sequence[str], None] = ("6f4a7b2c9d1e", "c5d6e7f8a9b0")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names() -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    try:
        return set(inspector.get_table_names())
    except Exception:
        return set()


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    try:
        return {idx["name"] for idx in inspector.get_indexes(table_name)}
    except Exception:
        return set()


def upgrade() -> None:
    tables = _table_names()

    if "mcp_servers" not in tables:
        op.create_table(
            "mcp_servers",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("server_url", sa.Text(), nullable=False),
            sa.Column("transport", sa.String(), nullable=False, server_default="streamable_http"),
            sa.Column("auth_mode", sa.String(), nullable=False, server_default="none"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("static_bearer_token_encrypted", sa.Text(), nullable=True),
            sa.Column("static_headers_encrypted", sa.Text(), nullable=True),
            sa.Column("auth_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("auth_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("capability_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("oauth_client_id", sa.Text(), nullable=True),
            sa.Column("oauth_client_secret_encrypted", sa.Text(), nullable=True),
            sa.Column(
                "oauth_client_registration",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column("oauth_client_secret_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("tool_snapshot_version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sync_status", sa.String(), nullable=False, server_default="never_synced"),
            sa.Column("sync_error", sa.Text(), nullable=True),
            sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "name", name="uq_mcp_servers_tenant_name"),
        )
        op.create_index("ix_mcp_servers_tenant_id", "mcp_servers", ["tenant_id"], unique=False)
        op.create_index("ix_mcp_servers_created_by", "mcp_servers", ["created_by"], unique=False)
        op.create_index("ix_mcp_servers_auth_mode", "mcp_servers", ["auth_mode"], unique=False)
        op.create_index("ix_mcp_servers_sync_status", "mcp_servers", ["sync_status"], unique=False)
        op.create_index("ix_mcp_servers_tenant_active", "mcp_servers", ["tenant_id", "is_active"], unique=False)

    if "mcp_discovered_tools" not in tables:
        op.create_table(
            "mcp_discovered_tools",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("server_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("snapshot_version", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("input_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("annotations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("tool_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "server_id",
                "snapshot_version",
                "name",
                name="uq_mcp_discovered_tools_server_snapshot_name",
            ),
        )
        op.create_index("ix_mcp_discovered_tools_tenant_id", "mcp_discovered_tools", ["tenant_id"], unique=False)
        op.create_index("ix_mcp_discovered_tools_server_id", "mcp_discovered_tools", ["server_id"], unique=False)
        op.create_index(
            "ix_mcp_discovered_tools_snapshot_version",
            "mcp_discovered_tools",
            ["snapshot_version"],
            unique=False,
        )
        op.create_index(
            "ix_mcp_discovered_tools_server_snapshot",
            "mcp_discovered_tools",
            ["server_id", "snapshot_version"],
            unique=False,
        )

    if "mcp_agent_mounts" not in tables:
        op.create_table(
            "mcp_agent_mounts",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("server_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("applied_snapshot_version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("approval_policy", sa.String(), nullable=False, server_default="ask"),
            sa.Column("tool_filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("agent_id", "server_id", name="uq_mcp_agent_mounts_agent_server"),
        )
        op.create_index("ix_mcp_agent_mounts_tenant_id", "mcp_agent_mounts", ["tenant_id"], unique=False)
        op.create_index("ix_mcp_agent_mounts_agent_id", "mcp_agent_mounts", ["agent_id"], unique=False)
        op.create_index("ix_mcp_agent_mounts_server_id", "mcp_agent_mounts", ["server_id"], unique=False)
        op.create_index("ix_mcp_agent_mounts_created_by", "mcp_agent_mounts", ["created_by"], unique=False)
        op.create_index("ix_mcp_agent_mounts_agent_active", "mcp_agent_mounts", ["agent_id", "is_active"], unique=False)

    if "mcp_user_account_connections" not in tables:
        op.create_table(
            "mcp_user_account_connections",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("server_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("token_payload_encrypted", sa.Text(), nullable=True),
            sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("account_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("server_id", "user_id", name="uq_mcp_user_account_connections_server_user"),
        )
        op.create_index(
            "ix_mcp_user_account_connections_tenant_id",
            "mcp_user_account_connections",
            ["tenant_id"],
            unique=False,
        )
        op.create_index(
            "ix_mcp_user_account_connections_server_id",
            "mcp_user_account_connections",
            ["server_id"],
            unique=False,
        )
        op.create_index(
            "ix_mcp_user_account_connections_user_id",
            "mcp_user_account_connections",
            ["user_id"],
            unique=False,
        )
        op.create_index(
            "ix_mcp_user_account_connections_status",
            "mcp_user_account_connections",
            ["status"],
            unique=False,
        )
        op.create_index(
            "ix_mcp_user_account_connections_user_status",
            "mcp_user_account_connections",
            ["user_id", "status"],
            unique=False,
        )

    if "mcp_oauth_states" not in tables:
        op.create_table(
            "mcp_oauth_states",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("server_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("state", sa.String(), nullable=False),
            sa.Column("code_verifier", sa.Text(), nullable=False),
            sa.Column("redirect_uri", sa.Text(), nullable=False),
            sa.Column("client_id", sa.Text(), nullable=False),
            sa.Column("requested_scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("auth_server_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("token_method", sa.String(), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("state"),
        )
        op.create_index("ix_mcp_oauth_states_tenant_id", "mcp_oauth_states", ["tenant_id"], unique=False)
        op.create_index("ix_mcp_oauth_states_server_id", "mcp_oauth_states", ["server_id"], unique=False)
        op.create_index("ix_mcp_oauth_states_user_id", "mcp_oauth_states", ["user_id"], unique=False)
        op.create_index("ix_mcp_oauth_states_state", "mcp_oauth_states", ["state"], unique=False)
        op.create_index("ix_mcp_oauth_states_server_user", "mcp_oauth_states", ["server_id", "user_id"], unique=False)
        op.create_index("ix_mcp_oauth_states_expires_at", "mcp_oauth_states", ["expires_at"], unique=False)


def downgrade() -> None:
    tables = _table_names()

    if "mcp_oauth_states" in tables:
        for index_name in _index_names("mcp_oauth_states"):
            op.drop_index(index_name, table_name="mcp_oauth_states")
        op.drop_table("mcp_oauth_states")

    if "mcp_user_account_connections" in tables:
        for index_name in _index_names("mcp_user_account_connections"):
            op.drop_index(index_name, table_name="mcp_user_account_connections")
        op.drop_table("mcp_user_account_connections")

    if "mcp_agent_mounts" in tables:
        for index_name in _index_names("mcp_agent_mounts"):
            op.drop_index(index_name, table_name="mcp_agent_mounts")
        op.drop_table("mcp_agent_mounts")

    if "mcp_discovered_tools" in tables:
        for index_name in _index_names("mcp_discovered_tools"):
            op.drop_index(index_name, table_name="mcp_discovered_tools")
        op.drop_table("mcp_discovered_tools")

    if "mcp_servers" in tables:
        for index_name in _index_names("mcp_servers"):
            op.drop_index(index_name, table_name="mcp_servers")
        op.drop_table("mcp_servers")
