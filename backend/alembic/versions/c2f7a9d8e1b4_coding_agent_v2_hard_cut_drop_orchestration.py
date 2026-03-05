"""coding-agent v2 hard cut drop orchestration artifacts

Revision ID: c2f7a9d8e1b4
Revises: 11e6a7c4b9d2, a1b9d7c5e3f0
Create Date: 2026-02-23 22:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c2f7a9d8e1b4"
down_revision: Union[str, Sequence[str], None] = ("11e6a7c4b9d2", "a1b9d7c5e3f0")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    bind.execute(
        sa.text(
            """
            UPDATE agent_runs
            SET status = 'failed',
                completed_at = NOW(),
                error_message = :msg
            WHERE surface = 'published_app_coding_agent'
              AND status IN ('queued', 'running')
            """
        ),
        {"msg": "Hard cut to coding-agent v2"},
    )
    if "agent_runs" in inspector.get_table_names():
        bind.execute(sa.text("ALTER TABLE agent_runs ALTER COLUMN execution_engine SET DEFAULT 'opencode'"))
        bind.execute(
            sa.text(
                """
                UPDATE agent_runs
                SET execution_engine = 'opencode'
                WHERE surface = 'published_app_coding_agent'
                """
            )
        )

    if "published_app_draft_dev_sessions" in inspector.get_table_names():
        bind.execute(
            sa.text(
                """
                UPDATE published_app_draft_dev_sessions
                SET active_coding_run_id = NULL,
                    active_coding_run_locked_at = NULL
                WHERE active_coding_run_id IS NOT NULL
                """
            )
        )

    if "published_app_coding_run_events" in inspector.get_table_names():
        op.drop_table("published_app_coding_run_events")

    if "agent_runs" in inspector.get_table_names():
        if _index_exists(inspector, "agent_runs", "ix_agent_runs_runner_owner_id"):
            op.drop_index("ix_agent_runs_runner_owner_id", table_name="agent_runs")
        if _index_exists(inspector, "agent_runs", "ix_agent_runs_runner_lease_expires_at"):
            op.drop_index("ix_agent_runs_runner_lease_expires_at", table_name="agent_runs")
        if _index_exists(inspector, "agent_runs", "ix_agent_runs_is_cancelling"):
            op.drop_index("ix_agent_runs_is_cancelling", table_name="agent_runs")

        if _table_has_column(inspector, "agent_runs", "is_cancelling"):
            op.drop_column("agent_runs", "is_cancelling")
        if _table_has_column(inspector, "agent_runs", "runner_heartbeat_at"):
            op.drop_column("agent_runs", "runner_heartbeat_at")
        if _table_has_column(inspector, "agent_runs", "runner_lease_expires_at"):
            op.drop_column("agent_runs", "runner_lease_expires_at")
        if _table_has_column(inspector, "agent_runs", "runner_owner_id"):
            op.drop_column("agent_runs", "runner_owner_id")

    if "published_app_draft_dev_sessions" in inspector.get_table_names() and _table_has_column(
        inspector,
        "published_app_draft_dev_sessions",
        "active_coding_run_client_message_id",
    ):
        op.drop_column("published_app_draft_dev_sessions", "active_coding_run_client_message_id")

    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_published_app_coding_prompt_queue_session_status_position
            ON published_app_coding_prompt_queue (chat_session_id, status, position)
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "agent_runs" in inspector.get_table_names():
        bind.execute(sa.text("ALTER TABLE agent_runs ALTER COLUMN execution_engine SET DEFAULT 'native'"))

    if "agent_runs" in inspector.get_table_names():
        if not _table_has_column(inspector, "agent_runs", "runner_owner_id"):
            op.add_column("agent_runs", sa.Column("runner_owner_id", sa.String(length=128), nullable=True))
        if not _table_has_column(inspector, "agent_runs", "runner_lease_expires_at"):
            op.add_column("agent_runs", sa.Column("runner_lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        if not _table_has_column(inspector, "agent_runs", "runner_heartbeat_at"):
            op.add_column("agent_runs", sa.Column("runner_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
        if not _table_has_column(inspector, "agent_runs", "is_cancelling"):
            op.add_column(
                "agent_runs",
                sa.Column("is_cancelling", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )

        inspector = sa.inspect(bind)
        if not _index_exists(inspector, "agent_runs", "ix_agent_runs_runner_owner_id"):
            op.create_index("ix_agent_runs_runner_owner_id", "agent_runs", ["runner_owner_id"], unique=False)
        if not _index_exists(inspector, "agent_runs", "ix_agent_runs_runner_lease_expires_at"):
            op.create_index(
                "ix_agent_runs_runner_lease_expires_at",
                "agent_runs",
                ["runner_lease_expires_at"],
                unique=False,
            )
        if not _index_exists(inspector, "agent_runs", "ix_agent_runs_is_cancelling"):
            op.create_index("ix_agent_runs_is_cancelling", "agent_runs", ["is_cancelling"], unique=False)

    if "published_app_draft_dev_sessions" in inspector.get_table_names() and not _table_has_column(
        inspector,
        "published_app_draft_dev_sessions",
        "active_coding_run_client_message_id",
    ):
        op.add_column(
            "published_app_draft_dev_sessions",
            sa.Column("active_coding_run_client_message_id", sa.String(length=128), nullable=True),
        )

    if "published_app_coding_run_events" not in inspector.get_table_names():
        op.create_table(
            "published_app_coding_run_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("event", sa.String(length=128), nullable=False),
            sa.Column("stage", sa.String(length=64), nullable=False),
            sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("diagnostics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
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
            "ix_published_app_coding_run_events_run_id",
            "published_app_coding_run_events",
            ["run_id"],
            unique=False,
        )
        op.create_index(
            "ix_published_app_coding_run_events_created_at",
            "published_app_coding_run_events",
            ["created_at"],
            unique=False,
        )

    op.execute(sa.text("DROP INDEX IF EXISTS ix_published_app_coding_prompt_queue_session_status_position"))
