"""add published app chat opencode session fields

Revision ID: ff9a2b3c4d5e
Revises: ff1e2d3c4b5a
Create Date: 2026-04-16 07:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ff9a2b3c4d5e"
down_revision = "ff1e2d3c4b5a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "published_app_coding_chat_sessions",
        sa.Column("opencode_session_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "published_app_coding_chat_sessions",
        sa.Column("opencode_sandbox_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "published_app_coding_chat_sessions",
        sa.Column("opencode_workspace_path", sa.Text(), nullable=True),
    )
    op.add_column(
        "published_app_coding_chat_sessions",
        sa.Column("opencode_session_opened_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "published_app_coding_chat_sessions",
        sa.Column("opencode_session_closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_published_app_coding_chat_sessions_opencode_session_id",
        "published_app_coding_chat_sessions",
        ["opencode_session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_published_app_coding_chat_sessions_opencode_session_id",
        table_name="published_app_coding_chat_sessions",
    )
    op.drop_column("published_app_coding_chat_sessions", "opencode_session_closed_at")
    op.drop_column("published_app_coding_chat_sessions", "opencode_session_opened_at")
    op.drop_column("published_app_coding_chat_sessions", "opencode_workspace_path")
    op.drop_column("published_app_coding_chat_sessions", "opencode_sandbox_id")
    op.drop_column("published_app_coding_chat_sessions", "opencode_session_id")
