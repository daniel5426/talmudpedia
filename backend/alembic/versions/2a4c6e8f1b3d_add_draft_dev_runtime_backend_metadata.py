"""add draft dev runtime backend metadata

Revision ID: 2a4c6e8f1b3d
Revises: 1c9d7e4f6a2b
Create Date: 2026-03-08 19:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "2a4c6e8f1b3d"
down_revision: Union[str, Sequence[str], None] = "1c9d7e4f6a2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "published_app_draft_dev_sessions",
        sa.Column("runtime_backend", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "published_app_draft_dev_sessions",
        sa.Column(
            "backend_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("published_app_draft_dev_sessions", "backend_metadata")
    op.drop_column("published_app_draft_dev_sessions", "runtime_backend")
