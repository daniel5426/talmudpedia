"""add published app coding chat history tables

Revision ID: d4e9f1a2b3c4
Revises: c7f1a2b3d4e5
Create Date: 2026-02-19 11:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d4e9f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "c7f1a2b3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


published_app_coding_chat_message_role_enum = postgresql.ENUM(
    "user",
    "assistant",
    name="publishedappcodingchatmessagerole",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    published_app_coding_chat_message_role_enum.create(bind, checkfirst=True)

    op.create_table(
        "published_app_coding_chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="New Chat"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_published_app_coding_chat_sessions_published_app_id"),
        "published_app_coding_chat_sessions",
        ["published_app_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_chat_sessions_user_id"),
        "published_app_coding_chat_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_chat_sessions_last_message_at"),
        "published_app_coding_chat_sessions",
        ["last_message_at"],
        unique=False,
    )
    op.create_index(
        "ix_published_app_coding_chat_sessions_scope_last_message",
        "published_app_coding_chat_sessions",
        ["published_app_id", "user_id", sa.text("last_message_at DESC")],
        unique=False,
    )

    op.create_table(
        "published_app_coding_chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            published_app_coding_chat_message_role_enum,
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["published_app_coding_chat_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "role", name="uq_published_app_coding_chat_messages_run_role"),
    )
    op.create_index(
        op.f("ix_published_app_coding_chat_messages_session_id"),
        "published_app_coding_chat_messages",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_chat_messages_run_id"),
        "published_app_coding_chat_messages",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_published_app_coding_chat_messages_session_created_at",
        "published_app_coding_chat_messages",
        ["session_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_published_app_coding_chat_messages_session_created_at",
        table_name="published_app_coding_chat_messages",
    )
    op.drop_index(
        op.f("ix_published_app_coding_chat_messages_run_id"),
        table_name="published_app_coding_chat_messages",
    )
    op.drop_index(
        op.f("ix_published_app_coding_chat_messages_session_id"),
        table_name="published_app_coding_chat_messages",
    )
    op.drop_table("published_app_coding_chat_messages")

    op.drop_index(
        "ix_published_app_coding_chat_sessions_scope_last_message",
        table_name="published_app_coding_chat_sessions",
    )
    op.drop_index(
        op.f("ix_published_app_coding_chat_sessions_last_message_at"),
        table_name="published_app_coding_chat_sessions",
    )
    op.drop_index(
        op.f("ix_published_app_coding_chat_sessions_user_id"),
        table_name="published_app_coding_chat_sessions",
    )
    op.drop_index(
        op.f("ix_published_app_coding_chat_sessions_published_app_id"),
        table_name="published_app_coding_chat_sessions",
    )
    op.drop_table("published_app_coding_chat_sessions")

    bind = op.get_bind()
    published_app_coding_chat_message_role_enum.drop(bind, checkfirst=True)
