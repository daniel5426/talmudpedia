"""rename artifact owner enum to organization

Revision ID: 3c4d5e6f7a8b
Revises: 2b3c4d5e6f7a
Create Date: 2026-04-22 21:35:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3c4d5e6f7a8b"
down_revision: Union[str, None] = "2b3c4d5e6f7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enum_value_exists(bind, enum_name: str, enum_value: str) -> bool:
    row = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_type t
            JOIN pg_enum e ON e.enumtypid = t.oid
            WHERE t.typname = :enum_name AND e.enumlabel = :enum_value
            LIMIT 1
            """
        ),
        {"enum_name": enum_name, "enum_value": enum_value},
    ).first()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()
    if _enum_value_exists(bind, "artifactownertype", "tenant") and not _enum_value_exists(bind, "artifactownertype", "organization"):
        bind.execute(sa.text("ALTER TYPE artifactownertype RENAME VALUE 'tenant' TO 'organization'"))


def downgrade() -> None:
    bind = op.get_bind()
    if _enum_value_exists(bind, "artifactownertype", "organization") and not _enum_value_exists(bind, "artifactownertype", "tenant"):
        bind.execute(sa.text("ALTER TYPE artifactownertype RENAME VALUE 'organization' TO 'tenant'"))
