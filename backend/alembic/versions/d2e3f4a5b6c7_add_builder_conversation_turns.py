"""add builder conversation turns for replay and audit

Revision ID: d2e3f4a5b6c7
Revises: c4d5e6f7a8b9
Create Date: 2026-02-11 23:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


builder_conversation_turn_status_enum = postgresql.ENUM(
    "succeeded",
    "failed",
    name="builderconversationturnstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    builder_conversation_turn_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "published_app_builder_conversation_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("status", builder_conversation_turn_status_enum, nullable=False, server_default="succeeded"),
        sa.Column("user_prompt", sa.Text(), nullable=False),
        sa.Column("assistant_summary", sa.Text(), nullable=True),
        sa.Column("assistant_rationale", sa.Text(), nullable=True),
        sa.Column("assistant_assumptions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("patch_operations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("tool_trace", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("diagnostics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("failure_code", sa.String(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["published_app_revisions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_published_app_builder_conversation_turns_published_app_id"),
        "published_app_builder_conversation_turns",
        ["published_app_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_builder_conversation_turns_revision_id"),
        "published_app_builder_conversation_turns",
        ["revision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_builder_conversation_turns_request_id"),
        "published_app_builder_conversation_turns",
        ["request_id"],
        unique=False,
    )
    op.create_index(
        "ix_builder_conversation_app_created_at",
        "published_app_builder_conversation_turns",
        ["published_app_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_builder_conversation_app_created_at", table_name="published_app_builder_conversation_turns")
    op.drop_index(
        op.f("ix_published_app_builder_conversation_turns_request_id"),
        table_name="published_app_builder_conversation_turns",
    )
    op.drop_index(
        op.f("ix_published_app_builder_conversation_turns_revision_id"),
        table_name="published_app_builder_conversation_turns",
    )
    op.drop_index(
        op.f("ix_published_app_builder_conversation_turns_published_app_id"),
        table_name="published_app_builder_conversation_turns",
    )
    op.drop_table("published_app_builder_conversation_turns")

    bind = op.get_bind()
    builder_conversation_turn_status_enum.drop(bind, checkfirst=True)
