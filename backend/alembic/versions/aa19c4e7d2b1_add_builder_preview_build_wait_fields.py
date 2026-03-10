"""add builder preview build wait fields

Revision ID: aa19c4e7d2b1
Revises: fad169b1b128
Create Date: 2026-03-10 10:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "aa19c4e7d2b1"
down_revision = "fad169b1b128"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "published_app_builder_conversation_turns",
        sa.Column("awaiting_preview_build", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "published_app_builder_conversation_turns",
        sa.Column("min_preview_build_seq", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column(
        "published_app_builder_conversation_turns",
        "awaiting_preview_build",
        server_default=None,
    )
    op.alter_column(
        "published_app_builder_conversation_turns",
        "min_preview_build_seq",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("published_app_builder_conversation_turns", "min_preview_build_seq")
    op.drop_column("published_app_builder_conversation_turns", "awaiting_preview_build")
