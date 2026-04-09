"""add generic agent execution worker fields

Revision ID: 6f4a7b2c9d1e
Revises: d1f4a8c9e2b7
Create Date: 2026-04-09 19:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6f4a7b2c9d1e"
down_revision = "d1f4a8c9e2b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("execution_owner_kind", sa.String(), nullable=True))
    op.add_column("agent_runs", sa.Column("execution_owner_id", sa.String(), nullable=True))
    op.add_column("agent_runs", sa.Column("execution_lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_runs", sa.Column("execution_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_runs", sa.Column("dispatch_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("agent_runs", sa.Column("last_dispatched_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_agent_runs_execution_owner_kind"), "agent_runs", ["execution_owner_kind"], unique=False)
    op.create_index(op.f("ix_agent_runs_execution_owner_id"), "agent_runs", ["execution_owner_id"], unique=False)
    op.create_index(
        op.f("ix_agent_runs_execution_lease_expires_at"),
        "agent_runs",
        ["execution_lease_expires_at"],
        unique=False,
    )
    op.execute("UPDATE agent_runs SET dispatch_count = 0 WHERE dispatch_count IS NULL")
    op.alter_column("agent_runs", "dispatch_count", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_runs_execution_lease_expires_at"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_execution_owner_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_execution_owner_kind"), table_name="agent_runs")
    op.drop_column("agent_runs", "last_dispatched_at")
    op.drop_column("agent_runs", "dispatch_count")
    op.drop_column("agent_runs", "execution_heartbeat_at")
    op.drop_column("agent_runs", "execution_lease_expires_at")
    op.drop_column("agent_runs", "execution_owner_id")
    op.drop_column("agent_runs", "execution_owner_kind")
