"""add org unit system key

Revision ID: d9e8f7a6b5c4
Revises: e0f1a2b3c4d5
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d9e8f7a6b5c4"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("org_units", sa.Column("system_key", sa.String(), nullable=True))
    op.create_index("ix_org_units_system_key", "org_units", ["system_key"], unique=False)
    op.execute(
        """
        UPDATE org_units
        SET system_key = 'root'
        WHERE system_key IS NULL
          AND type = 'org'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_org_units_system_key", table_name="org_units")
    op.drop_column("org_units", "system_key")
