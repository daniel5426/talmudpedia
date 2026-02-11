"""add build lifecycle fields to published app revisions

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-02-11 23:59:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


published_app_revision_build_status_enum = postgresql.ENUM(
    "queued",
    "running",
    "succeeded",
    "failed",
    name="publishedapprevisionbuildstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    published_app_revision_build_status_enum.create(bind, checkfirst=True)

    op.add_column(
        "published_app_revisions",
        sa.Column(
            "build_status",
            published_app_revision_build_status_enum,
            nullable=False,
            server_default="queued",
        ),
    )
    op.add_column(
        "published_app_revisions",
        sa.Column("build_seq", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("published_app_revisions", sa.Column("build_error", sa.Text(), nullable=True))
    op.add_column("published_app_revisions", sa.Column("build_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("published_app_revisions", sa.Column("build_finished_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("published_app_revisions", sa.Column("dist_storage_prefix", sa.String(), nullable=True))
    op.add_column(
        "published_app_revisions",
        sa.Column("dist_manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "published_app_revisions",
        sa.Column("template_runtime", sa.String(), nullable=False, server_default="vite_static"),
    )


def downgrade() -> None:
    op.drop_column("published_app_revisions", "template_runtime")
    op.drop_column("published_app_revisions", "dist_manifest")
    op.drop_column("published_app_revisions", "dist_storage_prefix")
    op.drop_column("published_app_revisions", "build_finished_at")
    op.drop_column("published_app_revisions", "build_started_at")
    op.drop_column("published_app_revisions", "build_error")
    op.drop_column("published_app_revisions", "build_seq")
    op.drop_column("published_app_revisions", "build_status")

    bind = op.get_bind()
    published_app_revision_build_status_enum.drop(bind, checkfirst=True)
