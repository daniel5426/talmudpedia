"""add project scope to artifact coding runtime

Revision ID: 2b3c4d5e6f7a
Revises: 0f1e2d3c4b6a
Create Date: 2026-04-22 20:45:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "2b3c4d5e6f7a"
down_revision: Union[str, None] = "0f1e2d3c4b6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_project_fk(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True))
        batch_op.create_foreign_key(
            f"fk_{table_name}_project_id_projects",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index(f"ix_{table_name}_project_id", ["project_id"], unique=False)


def _drop_project_fk(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_index(f"ix_{table_name}_project_id")
        batch_op.drop_constraint(f"fk_{table_name}_project_id_projects", type_="foreignkey")
        batch_op.drop_column("project_id")


def upgrade() -> None:
    for table_name in (
        "artifact_coding_sessions",
        "artifact_coding_shared_drafts",
        "artifact_coding_run_snapshots",
    ):
        _add_project_fk(table_name)

    op.drop_index("ix_artifact_coding_sessions_scope_activity", table_name="artifact_coding_sessions")
    op.create_index(
        "ix_artifact_coding_sessions_scope_activity",
        "artifact_coding_sessions",
        ["organization_id", "project_id", "artifact_id", "draft_key", "last_message_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_artifact_coding_sessions_scope_activity", table_name="artifact_coding_sessions")
    op.create_index(
        "ix_artifact_coding_sessions_scope_activity",
        "artifact_coding_sessions",
        ["organization_id", "artifact_id", "draft_key", "last_message_at"],
        unique=False,
    )

    for table_name in reversed(
        (
            "artifact_coding_sessions",
            "artifact_coding_shared_drafts",
            "artifact_coding_run_snapshots",
        )
    ):
        _drop_project_fk(table_name)
