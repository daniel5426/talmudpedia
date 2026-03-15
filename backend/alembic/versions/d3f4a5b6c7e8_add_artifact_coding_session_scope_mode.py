"""add artifact coding session scope mode

Revision ID: d3f4a5b6c7e8
Revises: c1d2e3f4a5b6
Create Date: 2026-03-16 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "d3f4a5b6c7e8"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_name = "artifact_coding_sessions"
    if not _column_exists(inspector, table_name, "scope_mode"):
        op.add_column(
            table_name,
            sa.Column("scope_mode", sa.String(length=32), nullable=False, server_default="locked"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_name = "artifact_coding_sessions"
    if _column_exists(inspector, table_name, "scope_mode"):
        op.drop_column(table_name, "scope_mode")
