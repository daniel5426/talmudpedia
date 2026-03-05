"""add_scope_to_custom_operators

Revision ID: 6a1d4e9b2c7f
Revises: d9f3a7b1c2e4
Create Date: 2026-03-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6a1d4e9b2c7f"
down_revision: Union[str, None] = "d9f3a7b1c2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _has_column("custom_operators", "scope"):
        op.add_column(
            "custom_operators",
            sa.Column("scope", sa.String(), nullable=False, server_default=sa.text("'rag'")),
        )

    op.execute("UPDATE custom_operators SET scope = 'rag' WHERE scope IS NULL")
    op.alter_column("custom_operators", "scope", server_default=None)


def downgrade() -> None:
    if _has_column("custom_operators", "scope"):
        op.drop_column("custom_operators", "scope")
