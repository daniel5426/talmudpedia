"""add execution engine audit fields to agent_runs

Revision ID: 9b6c5d4e3f21
Revises: 8e4f2a1b9c0d
Create Date: 2026-02-18 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9b6c5d4e3f21"
down_revision: Union[str, None] = "8e4f2a1b9c0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("execution_engine", sa.String(), nullable=False, server_default=sa.text("'native'")),
    )
    op.add_column("agent_runs", sa.Column("engine_run_ref", sa.String(), nullable=True))
    op.create_index(op.f("ix_agent_runs_execution_engine"), "agent_runs", ["execution_engine"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_runs_execution_engine"), table_name="agent_runs")
    op.drop_column("agent_runs", "engine_run_ref")
    op.drop_column("agent_runs", "execution_engine")
