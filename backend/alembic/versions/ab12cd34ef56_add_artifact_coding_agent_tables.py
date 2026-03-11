"""add artifact coding agent tables

Revision ID: ab12cd34ef56
Revises: f4c6d8e1b2a3
Create Date: 2026-03-11 16:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "ab12cd34ef56"
down_revision: Union[str, Sequence[str], None] = "f4c6d8e1b2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE agentthreadsurface ADD VALUE IF NOT EXISTS 'artifact_admin'")

    op.create_table(
        "artifact_coding_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("draft_key", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="New Chat"),
        sa.Column("working_draft_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_test_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("active_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("linked_artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["active_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["agent_thread_id"], ["agent_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["last_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["last_test_run_id"], ["artifact_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_artifact_id"], ["artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_artifact_coding_sessions_tenant_id"), "artifact_coding_sessions", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_artifact_coding_sessions_artifact_id"), "artifact_coding_sessions", ["artifact_id"], unique=False)
    op.create_index(op.f("ix_artifact_coding_sessions_agent_thread_id"), "artifact_coding_sessions", ["agent_thread_id"], unique=False)
    op.create_index(op.f("ix_artifact_coding_sessions_draft_key"), "artifact_coding_sessions", ["draft_key"], unique=False)
    op.create_index(op.f("ix_artifact_coding_sessions_last_test_run_id"), "artifact_coding_sessions", ["last_test_run_id"], unique=False)
    op.create_index(op.f("ix_artifact_coding_sessions_active_run_id"), "artifact_coding_sessions", ["active_run_id"], unique=False)
    op.create_index(op.f("ix_artifact_coding_sessions_last_run_id"), "artifact_coding_sessions", ["last_run_id"], unique=False)
    op.create_index(op.f("ix_artifact_coding_sessions_linked_artifact_id"), "artifact_coding_sessions", ["linked_artifact_id"], unique=False)
    op.create_index(op.f("ix_artifact_coding_sessions_last_message_at"), "artifact_coding_sessions", ["last_message_at"], unique=False)
    op.create_index(
        "ix_artifact_coding_sessions_scope_activity",
        "artifact_coding_sessions",
        ["tenant_id", "artifact_id", "draft_key", "last_message_at"],
        unique=False,
    )

    op.create_table(
        "artifact_coding_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["artifact_coding_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_artifact_coding_messages_session_id"), "artifact_coding_messages", ["session_id"], unique=False)
    op.create_index(op.f("ix_artifact_coding_messages_run_id"), "artifact_coding_messages", ["run_id"], unique=False)
    op.create_index(
        "ix_artifact_coding_messages_session_created_at",
        "artifact_coding_messages",
        ["session_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_artifact_coding_messages_run_role",
        "artifact_coding_messages",
        ["run_id", "role"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_artifact_coding_messages_run_role", table_name="artifact_coding_messages")
    op.drop_index("ix_artifact_coding_messages_session_created_at", table_name="artifact_coding_messages")
    op.drop_index(op.f("ix_artifact_coding_messages_run_id"), table_name="artifact_coding_messages")
    op.drop_index(op.f("ix_artifact_coding_messages_session_id"), table_name="artifact_coding_messages")
    op.drop_table("artifact_coding_messages")

    op.drop_index("ix_artifact_coding_sessions_scope_activity", table_name="artifact_coding_sessions")
    op.drop_index(op.f("ix_artifact_coding_sessions_last_message_at"), table_name="artifact_coding_sessions")
    op.drop_index(op.f("ix_artifact_coding_sessions_linked_artifact_id"), table_name="artifact_coding_sessions")
    op.drop_index(op.f("ix_artifact_coding_sessions_last_run_id"), table_name="artifact_coding_sessions")
    op.drop_index(op.f("ix_artifact_coding_sessions_active_run_id"), table_name="artifact_coding_sessions")
    op.drop_index(op.f("ix_artifact_coding_sessions_last_test_run_id"), table_name="artifact_coding_sessions")
    op.drop_index(op.f("ix_artifact_coding_sessions_draft_key"), table_name="artifact_coding_sessions")
    op.drop_index(op.f("ix_artifact_coding_sessions_agent_thread_id"), table_name="artifact_coding_sessions")
    op.drop_index(op.f("ix_artifact_coding_sessions_artifact_id"), table_name="artifact_coding_sessions")
    op.drop_index(op.f("ix_artifact_coding_sessions_tenant_id"), table_name="artifact_coding_sessions")
    op.drop_table("artifact_coding_sessions")
