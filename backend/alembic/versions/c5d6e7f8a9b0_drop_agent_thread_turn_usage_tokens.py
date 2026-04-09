"""drop agent thread turn usage tokens

Revision ID: c5d6e7f8a9b0
Revises: b2c3d4e5f6a7
Create Date: 2026-03-27 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("agent_thread_turns")}
    if "usage_tokens" in columns:
        op.drop_column("agent_thread_turns", "usage_tokens")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("agent_thread_turns")}
    if "usage_tokens" not in columns:
        op.add_column(
            "agent_thread_turns",
            sa.Column("usage_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )
