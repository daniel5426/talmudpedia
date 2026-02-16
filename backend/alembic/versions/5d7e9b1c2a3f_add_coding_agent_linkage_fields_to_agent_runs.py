"""add coding-agent linkage fields to agent_runs

Revision ID: 5d7e9b1c2a3f
Revises: f1a2b3c4d5e7
Create Date: 2026-02-16 10:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "5d7e9b1c2a3f"
down_revision: Union[str, None] = "f1a2b3c4d5e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("surface", sa.String(), nullable=True))
    op.add_column("agent_runs", sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("agent_runs", sa.Column("base_revision_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("agent_runs", sa.Column("result_revision_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("agent_runs", sa.Column("checkpoint_revision_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.create_foreign_key(
        "fk_agent_runs_published_app_id",
        "agent_runs",
        "published_apps",
        ["published_app_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_agent_runs_base_revision_id",
        "agent_runs",
        "published_app_revisions",
        ["base_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_agent_runs_result_revision_id",
        "agent_runs",
        "published_app_revisions",
        ["result_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_agent_runs_checkpoint_revision_id",
        "agent_runs",
        "published_app_revisions",
        ["checkpoint_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(op.f("ix_agent_runs_surface"), "agent_runs", ["surface"], unique=False)
    op.create_index(op.f("ix_agent_runs_published_app_id"), "agent_runs", ["published_app_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_base_revision_id"), "agent_runs", ["base_revision_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_result_revision_id"), "agent_runs", ["result_revision_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_checkpoint_revision_id"), "agent_runs", ["checkpoint_revision_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_runs_checkpoint_revision_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_result_revision_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_base_revision_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_published_app_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_surface"), table_name="agent_runs")

    op.drop_constraint("fk_agent_runs_checkpoint_revision_id", "agent_runs", type_="foreignkey")
    op.drop_constraint("fk_agent_runs_result_revision_id", "agent_runs", type_="foreignkey")
    op.drop_constraint("fk_agent_runs_base_revision_id", "agent_runs", type_="foreignkey")
    op.drop_constraint("fk_agent_runs_published_app_id", "agent_runs", type_="foreignkey")

    op.drop_column("agent_runs", "checkpoint_revision_id")
    op.drop_column("agent_runs", "result_revision_id")
    op.drop_column("agent_runs", "base_revision_id")
    op.drop_column("agent_runs", "published_app_id")
    op.drop_column("agent_runs", "surface")
