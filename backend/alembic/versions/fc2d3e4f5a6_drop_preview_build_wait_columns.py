"""drop preview build wait columns

Revision ID: fc2d3e4f5a6
Revises: fb1c2d3e4f5a
Create Date: 2026-03-16 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "fc2d3e4f5a6"
down_revision = "fb1c2d3e4f5a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("published_app_builder_conversation_turns") as batch_op:
        batch_op.drop_column("awaiting_preview_build")
        batch_op.drop_column("min_preview_build_seq")


def downgrade() -> None:
    with op.batch_alter_table("published_app_builder_conversation_turns") as batch_op:
        batch_op.add_column(sa.Column("min_preview_build_seq", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("awaiting_preview_build", sa.Boolean(), nullable=False, server_default=sa.false()))
