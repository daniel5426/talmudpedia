"""drop artifact source_code legacy column

Revision ID: f2b3c4d5e6f7
Revises: f1c2d3e4b5a6
Create Date: 2026-03-11 12:15:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f1c2d3e4b5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        return {col["name"] for col in inspector.get_columns(table_name)}
    except Exception:
        return set()


def upgrade() -> None:
    revision_columns = _column_names("artifact_revisions")
    if "source_code" in revision_columns:
        op.drop_column("artifact_revisions", "source_code")
    if "entry_module_path" in revision_columns:
        op.alter_column(
            "artifact_revisions",
            "entry_module_path",
            existing_type=sa.String(),
            server_default="main.py",
        )
        op.alter_column(
            "artifact_revisions",
            "entry_module_path",
            existing_type=sa.String(),
            server_default=None,
        )


def downgrade() -> None:
    revision_columns = _column_names("artifact_revisions")
    if "source_code" not in revision_columns:
        op.add_column("artifact_revisions", sa.Column("source_code", sa.Text(), nullable=True))
    if "entry_module_path" in revision_columns:
        op.alter_column(
            "artifact_revisions",
            "entry_module_path",
            existing_type=sa.String(),
            server_default="handler.py",
        )
        op.alter_column(
            "artifact_revisions",
            "entry_module_path",
            existing_type=sa.String(),
            server_default=None,
        )
