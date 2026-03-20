"""add xai model provider type

Revision ID: fd1a2b3c4d5e
Revises: fb9a1c2d3e4f
Create Date: 2026-03-20 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "fd1a2b3c4d5e"
down_revision: Union[str, Sequence[str], None] = "fb9a1c2d3e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    bind.execute(text("ALTER TYPE modelprovidertype ADD VALUE IF NOT EXISTS 'XAI'"))


def downgrade() -> None:
    # PostgreSQL enum value removal is intentionally omitted.
    return
