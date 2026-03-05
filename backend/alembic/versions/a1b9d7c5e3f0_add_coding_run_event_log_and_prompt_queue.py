"""add coding run event log and prompt queue

Revision ID: a1b9d7c5e3f0
Revises: f3d5c7b9a1e2
Create Date: 2026-02-23 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "a1b9d7c5e3f0"
down_revision = "f3d5c7b9a1e2"
branch_labels = None
depends_on = None


queue_status_enum = postgresql.ENUM(
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    name="publishedappcodingpromptqueuestatus",
    create_type=False,
)


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("runner_owner_id", sa.String(length=128), nullable=True))
    op.add_column("agent_runs", sa.Column("runner_lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_runs", sa.Column("runner_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "agent_runs",
        sa.Column("is_cancelling", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index(op.f("ix_agent_runs_runner_owner_id"), "agent_runs", ["runner_owner_id"], unique=False)
    op.create_index(
        op.f("ix_agent_runs_runner_lease_expires_at"),
        "agent_runs",
        ["runner_lease_expires_at"],
        unique=False,
    )
    op.create_index(op.f("ix_agent_runs_is_cancelling"), "agent_runs", ["is_cancelling"], unique=False)

    op.create_table(
        "published_app_coding_run_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=128), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("diagnostics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "seq", name="uq_published_app_coding_run_events_run_seq"),
    )
    op.create_index(
        "ix_published_app_coding_run_events_run_seq",
        "published_app_coding_run_events",
        ["run_id", "seq"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_run_events_run_id"),
        "published_app_coding_run_events",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_run_events_created_at"),
        "published_app_coding_run_events",
        ["created_at"],
        unique=False,
    )

    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE publishedappcodingpromptqueuestatus AS ENUM (
                'queued',
                'running',
                'completed',
                'failed',
                'cancelled'
            );
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.create_table(
        "published_app_coding_prompt_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chat_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", queue_status_enum, nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_session_id"], ["published_app_coding_chat_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "chat_session_id",
            "position",
            name="uq_published_app_coding_prompt_queue_session_position",
        ),
    )
    op.create_index(
        "ix_published_app_coding_prompt_queue_session_position",
        "published_app_coding_prompt_queue",
        ["chat_session_id", "position"],
        unique=False,
    )
    op.create_index(
        "ix_published_app_coding_prompt_queue_session_status",
        "published_app_coding_prompt_queue",
        ["chat_session_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_prompt_queue_published_app_id"),
        "published_app_coding_prompt_queue",
        ["published_app_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_prompt_queue_user_id"),
        "published_app_coding_prompt_queue",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_prompt_queue_chat_session_id"),
        "published_app_coding_prompt_queue",
        ["chat_session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_prompt_queue_created_at"),
        "published_app_coding_prompt_queue",
        ["created_at"],
        unique=False,
    )



def downgrade() -> None:
    op.drop_index(op.f("ix_published_app_coding_prompt_queue_created_at"), table_name="published_app_coding_prompt_queue")
    op.drop_index(op.f("ix_published_app_coding_prompt_queue_chat_session_id"), table_name="published_app_coding_prompt_queue")
    op.drop_index(op.f("ix_published_app_coding_prompt_queue_user_id"), table_name="published_app_coding_prompt_queue")
    op.drop_index(op.f("ix_published_app_coding_prompt_queue_published_app_id"), table_name="published_app_coding_prompt_queue")
    op.drop_index("ix_published_app_coding_prompt_queue_session_status", table_name="published_app_coding_prompt_queue")
    op.drop_index("ix_published_app_coding_prompt_queue_session_position", table_name="published_app_coding_prompt_queue")
    op.drop_table("published_app_coding_prompt_queue")
    queue_status_enum.drop(op.get_bind(), checkfirst=True)

    op.drop_index(op.f("ix_published_app_coding_run_events_created_at"), table_name="published_app_coding_run_events")
    op.drop_index(op.f("ix_published_app_coding_run_events_run_id"), table_name="published_app_coding_run_events")
    op.drop_index("ix_published_app_coding_run_events_run_seq", table_name="published_app_coding_run_events")
    op.drop_table("published_app_coding_run_events")

    op.drop_index(op.f("ix_agent_runs_is_cancelling"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_runner_lease_expires_at"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_runner_owner_id"), table_name="agent_runs")
    op.drop_column("agent_runs", "is_cancelling")
    op.drop_column("agent_runs", "runner_heartbeat_at")
    op.drop_column("agent_runs", "runner_lease_expires_at")
    op.drop_column("agent_runs", "runner_owner_id")
