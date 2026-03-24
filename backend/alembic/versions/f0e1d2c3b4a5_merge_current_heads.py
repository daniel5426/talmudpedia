"""merge current alembic heads

Revision ID: f0e1d2c3b4a5
Revises: 1f2e3d4c5b6a, 6f8e9d0c1b2a, a1b2c3d4e5f6, d1e2f3a4b5c6, fe2a3b4c5d6e
Create Date: 2026-03-24 19:42:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union


revision: str = "f0e1d2c3b4a5"
down_revision: Union[str, Sequence[str], None] = (
    "1f2e3d4c5b6a",
    "6f8e9d0c1b2a",
    "a1b2c3d4e5f6",
    "d1e2f3a4b5c6",
    "fe2a3b4c5d6e",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
