"""add builder checkpoint metadata and result revision linkage

Revision ID: a7c1d9e4b6f2
Revises: c9d8e7f6a5b4
Create Date: 2026-02-14 22:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a7c1d9e4b6f2"
down_revision: Union[str, None] = "c9d8e7f6a5b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


builder_checkpoint_type_enum = postgresql.ENUM(
    "auto_run",
    "undo",
    "file_revert",
    name="buildercheckpointtype",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    builder_checkpoint_type_enum.create(bind, checkfirst=True)

    op.add_column(
        "published_app_builder_conversation_turns",
        sa.Column("result_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "published_app_builder_conversation_turns",
        sa.Column(
            "tool_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "published_app_builder_conversation_turns",
        sa.Column(
            "checkpoint_type",
            builder_checkpoint_type_enum,
            nullable=False,
            server_default="auto_run",
        ),
    )
    op.add_column(
        "published_app_builder_conversation_turns",
        sa.Column("checkpoint_label", sa.String(), nullable=True),
    )

    op.create_foreign_key(
        "fk_builder_turn_result_revision",
        "published_app_builder_conversation_turns",
        "published_app_revisions",
        ["result_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_published_app_builder_conversation_turns_result_revision_id"),
        "published_app_builder_conversation_turns",
        ["result_revision_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_published_app_builder_conversation_turns_result_revision_id"),
        table_name="published_app_builder_conversation_turns",
    )
    op.drop_constraint(
        "fk_builder_turn_result_revision",
        "published_app_builder_conversation_turns",
        type_="foreignkey",
    )
    op.drop_column("published_app_builder_conversation_turns", "checkpoint_label")
    op.drop_column("published_app_builder_conversation_turns", "checkpoint_type")
    op.drop_column("published_app_builder_conversation_turns", "tool_summary")
    op.drop_column("published_app_builder_conversation_turns", "result_revision_id")

    bind = op.get_bind()
    builder_checkpoint_type_enum.drop(bind, checkfirst=True)
