"""shared stage batch finalization and lock pointer removal

Revision ID: f9b4e1c2d3a6
Revises: c2f7a9d8e1b4
Create Date: 2026-02-24 18:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f9b4e1c2d3a6"
down_revision: Union[str, Sequence[str], None] = "c2f7a9d8e1b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _drop_fk_for_column(inspector: sa.Inspector, table_name: str, column_name: str) -> None:
    for fk in inspector.get_foreign_keys(table_name):
        constrained_columns = list(fk.get("constrained_columns") or [])
        if constrained_columns == [column_name]:
            fk_name = fk.get("name")
            if fk_name:
                op.drop_constraint(fk_name, table_name, type_="foreignkey")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "agent_runs" in inspector.get_table_names():
        if not _table_has_column(inspector, "agent_runs", "has_workspace_writes"):
            op.add_column(
                "agent_runs",
                sa.Column("has_workspace_writes", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        if not _table_has_column(inspector, "agent_runs", "batch_finalized_at"):
            op.add_column("agent_runs", sa.Column("batch_finalized_at", sa.DateTime(timezone=True), nullable=True))
        if not _table_has_column(inspector, "agent_runs", "batch_owner"):
            op.add_column(
                "agent_runs",
                sa.Column("batch_owner", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )

        inspector = sa.inspect(bind)
        if not _index_exists(inspector, "agent_runs", "ix_agent_runs_coding_scope_status_created_at"):
            op.create_index(
                "ix_agent_runs_coding_scope_status_created_at",
                "agent_runs",
                ["surface", "published_app_id", "initiator_user_id", "status", "created_at"],
                unique=False,
            )

        bind.execute(
            sa.text(
                """
                UPDATE agent_runs
                SET batch_finalized_at = NOW(),
                    batch_owner = FALSE
                WHERE surface = 'published_app_coding_agent'
                  AND status IN ('completed', 'failed', 'cancelled', 'paused')
                  AND batch_finalized_at IS NULL
                """
            )
        )

    if "published_app_draft_dev_sessions" in inspector.get_table_names():
        if _table_has_column(inspector, "published_app_draft_dev_sessions", "active_coding_run_id"):
            _drop_fk_for_column(inspector, "published_app_draft_dev_sessions", "active_coding_run_id")
            inspector = sa.inspect(bind)
            if _index_exists(inspector, "published_app_draft_dev_sessions", "ix_published_app_draft_dev_sessions_active_coding_run_id"):
                op.drop_index(
                    "ix_published_app_draft_dev_sessions_active_coding_run_id",
                    table_name="published_app_draft_dev_sessions",
                )
            op.drop_column("published_app_draft_dev_sessions", "active_coding_run_id")

        inspector = sa.inspect(bind)
        if _table_has_column(inspector, "published_app_draft_dev_sessions", "active_coding_run_locked_at"):
            op.drop_column("published_app_draft_dev_sessions", "active_coding_run_locked_at")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "published_app_draft_dev_sessions" in inspector.get_table_names():
        if not _table_has_column(inspector, "published_app_draft_dev_sessions", "active_coding_run_id"):
            op.add_column(
                "published_app_draft_dev_sessions",
                sa.Column("active_coding_run_id", postgresql.UUID(as_uuid=True), nullable=True),
            )
        inspector = sa.inspect(bind)
        if not _index_exists(inspector, "published_app_draft_dev_sessions", "ix_published_app_draft_dev_sessions_active_coding_run_id"):
            op.create_index(
                "ix_published_app_draft_dev_sessions_active_coding_run_id",
                "published_app_draft_dev_sessions",
                ["active_coding_run_id"],
                unique=False,
            )
        inspector = sa.inspect(bind)
        has_fk = any(
            list(fk.get("constrained_columns") or []) == ["active_coding_run_id"]
            for fk in inspector.get_foreign_keys("published_app_draft_dev_sessions")
        )
        if not has_fk:
            op.create_foreign_key(
                "fk_published_app_draft_dev_sessions_active_coding_run_id",
                "published_app_draft_dev_sessions",
                "agent_runs",
                ["active_coding_run_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if not _table_has_column(inspector, "published_app_draft_dev_sessions", "active_coding_run_locked_at"):
            op.add_column(
                "published_app_draft_dev_sessions",
                sa.Column("active_coding_run_locked_at", sa.DateTime(timezone=True), nullable=True),
            )

    inspector = sa.inspect(bind)
    if "agent_runs" in inspector.get_table_names():
        if _index_exists(inspector, "agent_runs", "ix_agent_runs_coding_scope_status_created_at"):
            op.drop_index("ix_agent_runs_coding_scope_status_created_at", table_name="agent_runs")

        if _table_has_column(inspector, "agent_runs", "batch_owner"):
            op.drop_column("agent_runs", "batch_owner")
        if _table_has_column(inspector, "agent_runs", "batch_finalized_at"):
            op.drop_column("agent_runs", "batch_finalized_at")
        if _table_has_column(inspector, "agent_runs", "has_workspace_writes"):
            op.drop_column("agent_runs", "has_workspace_writes")
