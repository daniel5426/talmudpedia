"""add thread lineage fields

Revision ID: d1f4a8c9e2b7
Revises: a9c8e7f6d5b4
Create Date: 2026-04-05 15:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d1f4a8c9e2b7"
down_revision: Union[str, Sequence[str], None] = "a9c8e7f6d5b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_threads", sa.Column("root_thread_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("agent_threads", sa.Column("parent_thread_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("agent_threads", sa.Column("parent_thread_turn_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("agent_threads", sa.Column("spawned_by_run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("agent_threads", sa.Column("lineage_depth", sa.Integer(), nullable=False, server_default="0"))

    op.create_foreign_key(
        "fk_agent_threads_root_thread_id",
        "agent_threads",
        "agent_threads",
        ["root_thread_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_agent_threads_parent_thread_id",
        "agent_threads",
        "agent_threads",
        ["parent_thread_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_agent_threads_parent_thread_turn_id",
        "agent_threads",
        "agent_thread_turns",
        ["parent_thread_turn_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_agent_threads_spawned_by_run_id",
        "agent_threads",
        "agent_runs",
        ["spawned_by_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(op.f("ix_agent_threads_root_thread_id"), "agent_threads", ["root_thread_id"], unique=False)
    op.create_index(op.f("ix_agent_threads_parent_thread_id"), "agent_threads", ["parent_thread_id"], unique=False)
    op.create_index(op.f("ix_agent_threads_spawned_by_run_id"), "agent_threads", ["spawned_by_run_id"], unique=False)

    bind = op.get_bind()
    bind.execute(sa.text("UPDATE agent_threads SET root_thread_id = id WHERE root_thread_id IS NULL"))
    bind.execute(sa.text("UPDATE agent_threads SET lineage_depth = 0 WHERE lineage_depth IS NULL"))

    op.alter_column("agent_threads", "root_thread_id", nullable=False)
    op.alter_column("agent_threads", "lineage_depth", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_threads_spawned_by_run_id"), table_name="agent_threads")
    op.drop_index(op.f("ix_agent_threads_parent_thread_id"), table_name="agent_threads")
    op.drop_index(op.f("ix_agent_threads_root_thread_id"), table_name="agent_threads")

    op.drop_constraint("fk_agent_threads_spawned_by_run_id", "agent_threads", type_="foreignkey")
    op.drop_constraint("fk_agent_threads_parent_thread_turn_id", "agent_threads", type_="foreignkey")
    op.drop_constraint("fk_agent_threads_parent_thread_id", "agent_threads", type_="foreignkey")
    op.drop_constraint("fk_agent_threads_root_thread_id", "agent_threads", type_="foreignkey")

    op.drop_column("agent_threads", "lineage_depth")
    op.drop_column("agent_threads", "spawned_by_run_id")
    op.drop_column("agent_threads", "parent_thread_turn_id")
    op.drop_column("agent_threads", "parent_thread_id")
    op.drop_column("agent_threads", "root_thread_id")
