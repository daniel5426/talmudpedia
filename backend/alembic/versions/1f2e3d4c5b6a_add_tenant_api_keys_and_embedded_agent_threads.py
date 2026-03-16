"""add tenant api keys and embedded agent threads

Revision ID: 1f2e3d4c5b6a
Revises: fc2d3e4f5a6
Create Date: 2026-03-16 14:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "1f2e3d4c5b6a"
down_revision: Union[str, Sequence[str], None] = "fc2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TENANT_API_KEY_STATUS_ENUM = postgresql.ENUM(
    "active",
    "revoked",
    name="tenantapikeystatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    _TENANT_API_KEY_STATUS_ENUM.create(bind, checkfirst=True)

    op.create_table(
        "tenant_api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("key_prefix", sa.String(), nullable=False),
        sa.Column("secret_hash", sa.String(), nullable=False),
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("status", _TENANT_API_KEY_STATUS_ENUM, nullable=False, server_default="active"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_prefix", name="uq_tenant_api_keys_key_prefix"),
    )
    op.create_index(op.f("ix_tenant_api_keys_tenant_id"), "tenant_api_keys", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_tenant_api_keys_key_prefix"), "tenant_api_keys", ["key_prefix"], unique=False)
    op.create_index(op.f("ix_tenant_api_keys_created_by"), "tenant_api_keys", ["created_by"], unique=False)

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE agentthreadsurface ADD VALUE IF NOT EXISTS 'embedded_runtime'")

    op.add_column("agent_threads", sa.Column("tenant_api_key_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("agent_threads", sa.Column("external_user_id", sa.String(length=255), nullable=True))
    op.add_column("agent_threads", sa.Column("external_session_id", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_agent_threads_tenant_api_key_id"), "agent_threads", ["tenant_api_key_id"], unique=False)
    op.create_index(op.f("ix_agent_threads_external_user_id"), "agent_threads", ["external_user_id"], unique=False)
    op.create_index(op.f("ix_agent_threads_external_session_id"), "agent_threads", ["external_session_id"], unique=False)
    op.create_foreign_key(
        "fk_agent_threads_tenant_api_key_id",
        "agent_threads",
        "tenant_api_keys",
        ["tenant_api_key_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_agent_threads_embed_activity",
        "agent_threads",
        ["tenant_id", "agent_id", "external_user_id", "last_activity_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_threads_embed_activity", table_name="agent_threads")
    op.drop_constraint("fk_agent_threads_tenant_api_key_id", "agent_threads", type_="foreignkey")
    op.drop_index(op.f("ix_agent_threads_external_session_id"), table_name="agent_threads")
    op.drop_index(op.f("ix_agent_threads_external_user_id"), table_name="agent_threads")
    op.drop_index(op.f("ix_agent_threads_tenant_api_key_id"), table_name="agent_threads")
    op.drop_column("agent_threads", "external_session_id")
    op.drop_column("agent_threads", "external_user_id")
    op.drop_column("agent_threads", "tenant_api_key_id")

    op.drop_index(op.f("ix_tenant_api_keys_created_by"), table_name="tenant_api_keys")
    op.drop_index(op.f("ix_tenant_api_keys_key_prefix"), table_name="tenant_api_keys")
    op.drop_index(op.f("ix_tenant_api_keys_tenant_id"), table_name="tenant_api_keys")
    op.drop_table("tenant_api_keys")

    _TENANT_API_KEY_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
    return None
