"""add draft dev runtime generation and explicit states

Revision ID: 4f2e8c1a9d7b
Revises: 2a4c6e8f1b3d
Create Date: 2026-03-08 23:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4f2e8c1a9d7b"
down_revision: Union[str, Sequence[str], None] = "2a4c6e8f1b3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_STATUS_ENUM_NAME = "publishedappdraftdevsessionstatus"
_NEW_STATUS_VALUES = ("building", "serving", "degraded", "stopping")


def _is_postgresql() -> bool:
    bind = op.get_bind()
    return str(getattr(bind.dialect, "name", "") or "").lower() == "postgresql"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _is_postgresql():
        for value in _NEW_STATUS_VALUES:
            op.execute(f"ALTER TYPE {_STATUS_ENUM_NAME} ADD VALUE IF NOT EXISTS '{value}'")

    existing_columns = {column["name"] for column in inspector.get_columns("published_app_draft_dev_sessions")}
    if "runtime_generation" not in existing_columns:
        op.add_column(
            "published_app_draft_dev_sessions",
            sa.Column("runtime_generation", sa.Integer(), nullable=False, server_default="0"),
        )
        op.execute("UPDATE published_app_draft_dev_sessions SET runtime_generation = 0 WHERE runtime_generation IS NULL")
        op.alter_column("published_app_draft_dev_sessions", "runtime_generation", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("published_app_draft_dev_sessions")}
    if "runtime_generation" in existing_columns:
        op.drop_column("published_app_draft_dev_sessions", "runtime_generation")
