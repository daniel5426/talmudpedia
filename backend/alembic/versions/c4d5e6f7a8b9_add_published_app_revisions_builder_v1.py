"""add published app revisions for apps builder v1

Revision ID: c4d5e6f7a8b9
Revises: b2f4c6d8e9a1
Create Date: 2026-02-11 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "b2f4c6d8e9a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


published_app_revision_kind_enum = postgresql.ENUM(
    "draft",
    "published",
    name="publishedapprevisionkind",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    published_app_revision_kind_enum.create(bind, checkfirst=True)

    op.add_column(
        "published_apps",
        sa.Column("template_key", sa.String(), nullable=False, server_default="chat-classic"),
    )
    op.add_column("published_apps", sa.Column("current_draft_revision_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("published_apps", sa.Column("current_published_revision_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.create_index(op.f("ix_published_apps_current_draft_revision_id"), "published_apps", ["current_draft_revision_id"], unique=False)
    op.create_index(op.f("ix_published_apps_current_published_revision_id"), "published_apps", ["current_published_revision_id"], unique=False)

    op.create_table(
        "published_app_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", published_app_revision_kind_enum, nullable=False, server_default="draft"),
        sa.Column("template_key", sa.String(), nullable=False, server_default="chat-classic"),
        sa.Column("entry_file", sa.String(), nullable=False, server_default="src/main.tsx"),
        sa.Column("files", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("compiled_bundle", sa.Text(), nullable=True),
        sa.Column("bundle_hash", sa.String(), nullable=True),
        sa.Column("source_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_revision_id"], ["published_app_revisions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(op.f("ix_published_app_revisions_published_app_id"), "published_app_revisions", ["published_app_id"], unique=False)
    op.create_index(op.f("ix_published_app_revisions_bundle_hash"), "published_app_revisions", ["bundle_hash"], unique=False)
    op.create_index(op.f("ix_published_app_revisions_source_revision_id"), "published_app_revisions", ["source_revision_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_published_app_revisions_source_revision_id"), table_name="published_app_revisions")
    op.drop_index(op.f("ix_published_app_revisions_bundle_hash"), table_name="published_app_revisions")
    op.drop_index(op.f("ix_published_app_revisions_published_app_id"), table_name="published_app_revisions")
    op.drop_table("published_app_revisions")

    op.drop_index(op.f("ix_published_apps_current_published_revision_id"), table_name="published_apps")
    op.drop_index(op.f("ix_published_apps_current_draft_revision_id"), table_name="published_apps")
    op.drop_column("published_apps", "current_published_revision_id")
    op.drop_column("published_apps", "current_draft_revision_id")
    op.drop_column("published_apps", "template_key")

    bind = op.get_bind()
    published_app_revision_kind_enum.drop(bind, checkfirst=True)
