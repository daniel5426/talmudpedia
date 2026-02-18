"""add run-level model pinning fields to agent_runs

Revision ID: 8e4f2a1b9c0d
Revises: 5d7e9b1c2a3f
Create Date: 2026-02-17 22:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "8e4f2a1b9c0d"
down_revision: Union[str, None] = "5d7e9b1c2a3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("requested_model_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("agent_runs", sa.Column("resolved_model_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.create_foreign_key(
        "fk_agent_runs_requested_model_id",
        "agent_runs",
        "model_registry",
        ["requested_model_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_agent_runs_resolved_model_id",
        "agent_runs",
        "model_registry",
        ["resolved_model_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(op.f("ix_agent_runs_requested_model_id"), "agent_runs", ["requested_model_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_resolved_model_id"), "agent_runs", ["resolved_model_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_runs_resolved_model_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_requested_model_id"), table_name="agent_runs")
    op.drop_constraint("fk_agent_runs_resolved_model_id", "agent_runs", type_="foreignkey")
    op.drop_constraint("fk_agent_runs_requested_model_id", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "resolved_model_id")
    op.drop_column("agent_runs", "requested_model_id")
