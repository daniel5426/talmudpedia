"""add_paused_runstatus

Revision ID: a13fc6223d86
Revises: c3a8d1e2f4a6
Create Date: 2026-02-04 20:16:16.418608

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a13fc6223d86'
down_revision: Union[str, None] = 'c3a8d1e2f4a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the paused status for agent runs if it does not exist.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE runstatus ADD VALUE IF NOT EXISTS 'paused'")


def downgrade() -> None:
    # Enum value removal is not supported in Postgres without a type rebuild.
    # Intentionally left as a no-op.
    return None
