"""add agent threads and thread turns

Revision ID: 7a1f3b4c5d6e
Revises: 3f8a1c2d9b7e
Create Date: 2026-03-02 18:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "7a1f3b4c5d6e"
down_revision: Union[str, Sequence[str], None] = "3f8a1c2d9b7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


agent_thread_status = postgresql.ENUM(
    "active",
    "archived",
    name="agentthreadstatus",
    create_type=False,
)
agent_thread_surface = postgresql.ENUM(
    "internal",
    "published_host_runtime",
    "preview_runtime",
    name="agentthreadsurface",
    create_type=False,
)
agent_thread_turn_status = postgresql.ENUM(
    "running",
    "completed",
    "failed",
    "cancelled",
    "paused",
    name="agentthreadturnstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    agent_thread_status.create(bind, checkfirst=True)
    agent_thread_surface.create(bind, checkfirst=True)
    agent_thread_turn_status.create(bind, checkfirst=True)

    op.create_table(
        "agent_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("surface", agent_thread_surface, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status", agent_thread_status, nullable=False),
        sa.Column("last_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["last_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_threads_tenant_id"), "agent_threads", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_agent_threads_user_id"), "agent_threads", ["user_id"], unique=False)
    op.create_index(op.f("ix_agent_threads_agent_id"), "agent_threads", ["agent_id"], unique=False)
    op.create_index(op.f("ix_agent_threads_published_app_id"), "agent_threads", ["published_app_id"], unique=False)
    op.create_index(op.f("ix_agent_threads_surface"), "agent_threads", ["surface"], unique=False)
    op.create_index(op.f("ix_agent_threads_status"), "agent_threads", ["status"], unique=False)
    op.create_index(op.f("ix_agent_threads_last_run_id"), "agent_threads", ["last_run_id"], unique=False)
    op.create_index(op.f("ix_agent_threads_last_activity_at"), "agent_threads", ["last_activity_at"], unique=False)
    op.create_index(
        "ix_agent_threads_scope_activity",
        "agent_threads",
        ["tenant_id", "user_id", "last_activity_at"],
        unique=False,
    )

    op.add_column("agent_runs", sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_agent_runs_thread_id"), "agent_runs", ["thread_id"], unique=False)
    op.create_foreign_key(
        "fk_agent_runs_thread_id_agent_threads",
        "agent_runs",
        "agent_threads",
        ["thread_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_agent_runs_thread_created_at", "agent_runs", ["thread_id", "created_at"], unique=False)

    op.create_table(
        "agent_thread_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("user_input_text", sa.Text(), nullable=True),
        sa.Column("assistant_output_text", sa.Text(), nullable=True),
        sa.Column("status", agent_thread_turn_status, nullable=False),
        sa.Column("usage_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["thread_id"], ["agent_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index(op.f("ix_agent_thread_turns_thread_id"), "agent_thread_turns", ["thread_id"], unique=False)
    op.create_index(op.f("ix_agent_thread_turns_run_id"), "agent_thread_turns", ["run_id"], unique=True)
    op.create_index(op.f("ix_agent_thread_turns_status"), "agent_thread_turns", ["status"], unique=False)
    op.create_index("ix_agent_thread_turns_thread_turn_index", "agent_thread_turns", ["thread_id", "turn_index"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_thread_turns_thread_turn_index", table_name="agent_thread_turns")
    op.drop_index(op.f("ix_agent_thread_turns_status"), table_name="agent_thread_turns")
    op.drop_index(op.f("ix_agent_thread_turns_run_id"), table_name="agent_thread_turns")
    op.drop_index(op.f("ix_agent_thread_turns_thread_id"), table_name="agent_thread_turns")
    op.drop_table("agent_thread_turns")

    op.drop_index("ix_agent_runs_thread_created_at", table_name="agent_runs")
    op.drop_constraint("fk_agent_runs_thread_id_agent_threads", "agent_runs", type_="foreignkey")
    op.drop_index(op.f("ix_agent_runs_thread_id"), table_name="agent_runs")
    op.drop_column("agent_runs", "thread_id")

    op.drop_index("ix_agent_threads_scope_activity", table_name="agent_threads")
    op.drop_index(op.f("ix_agent_threads_last_activity_at"), table_name="agent_threads")
    op.drop_index(op.f("ix_agent_threads_last_run_id"), table_name="agent_threads")
    op.drop_index(op.f("ix_agent_threads_status"), table_name="agent_threads")
    op.drop_index(op.f("ix_agent_threads_surface"), table_name="agent_threads")
    op.drop_index(op.f("ix_agent_threads_published_app_id"), table_name="agent_threads")
    op.drop_index(op.f("ix_agent_threads_agent_id"), table_name="agent_threads")
    op.drop_index(op.f("ix_agent_threads_user_id"), table_name="agent_threads")
    op.drop_index(op.f("ix_agent_threads_tenant_id"), table_name="agent_threads")
    op.drop_table("agent_threads")

    bind = op.get_bind()
    agent_thread_turn_status.drop(bind, checkfirst=True)
    agent_thread_surface.drop(bind, checkfirst=True)
    agent_thread_status.drop(bind, checkfirst=True)
