"""add artifact revision dependency declarations

Revision ID: d6f7a8b9c0d1
Revises: c4b2f6a9d1e0
Create Date: 2026-03-10 18:30:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "c4b2f6a9d1e0"
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
    if "python_dependencies" not in _column_names("artifact_revisions"):
        op.add_column(
            "artifact_revisions",
            sa.Column(
                "python_dependencies",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )
        op.alter_column("artifact_revisions", "python_dependencies", server_default=None)


def downgrade() -> None:
    if "python_dependencies" in _column_names("artifact_revisions"):
        op.drop_column("artifact_revisions", "python_dependencies")
