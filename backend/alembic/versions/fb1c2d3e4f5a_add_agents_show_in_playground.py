"""add agents show_in_playground flag

Revision ID: fb1c2d3e4f5a
Revises: d3f4a5b6c7e8
Create Date: 2026-03-16 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision: str = "fb1c2d3e4f5a"
down_revision: Union[str, Sequence[str], None] = "d3f4a5b6c7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_name = "agents"
    if not _column_exists(inspector, table_name, "show_in_playground"):
        op.add_column(
            table_name,
            sa.Column("show_in_playground", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
        bind.execute(text("UPDATE agents SET show_in_playground = true WHERE show_in_playground IS NULL"))
        bind.execute(
            text(
                """
                UPDATE agents
                SET show_in_playground = false
                WHERE slug = 'artifact-coding-agent'
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_name = "agents"
    if _column_exists(inspector, table_name, "show_in_playground"):
        op.drop_column(table_name, "show_in_playground")
