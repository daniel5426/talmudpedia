"""add workspace build cache

Revision ID: 0a1b2c3d4e5f
Revises: fc2d3e4f5a6
Create Date: 2026-03-16 20:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0a1b2c3d4e5f"
down_revision = "fc2d3e4f5a6"
branch_labels = None
depends_on = None


workspace_build_status_enum = sa.Enum(
    "queued",
    "building",
    "ready",
    "failed",
    name="publishedappworkspacebuildstatus",
)

workspace_build_status_column_enum = postgresql.ENUM(
    "queued",
    "building",
    "ready",
    "failed",
    name="publishedappworkspacebuildstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    workspace_build_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "published_app_workspace_builds",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", workspace_build_status_column_enum, nullable=False),
        sa.Column("entry_file", sa.String(), nullable=False),
        sa.Column("source_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dependency_hash", sa.String(length=64), nullable=True),
        sa.Column("source_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("origin_kind", sa.String(length=32), nullable=False),
        sa.Column("origin_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("build_error", sa.Text(), nullable=True),
        sa.Column("build_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("build_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dist_storage_prefix", sa.String(), nullable=True),
        sa.Column("dist_manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("template_runtime", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["origin_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_revision_id"], ["published_app_revisions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "published_app_id",
            "workspace_fingerprint",
            name="uq_published_app_workspace_builds_app_fingerprint",
        ),
    )
    op.create_index(
        "ix_published_app_workspace_builds_app_updated_at_desc",
        "published_app_workspace_builds",
        ["published_app_id", sa.text("updated_at DESC")],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_workspace_builds_published_app_id"),
        "published_app_workspace_builds",
        ["published_app_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_workspace_builds_source_revision_id"),
        "published_app_workspace_builds",
        ["source_revision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_workspace_builds_origin_kind"),
        "published_app_workspace_builds",
        ["origin_kind"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_workspace_builds_origin_run_id"),
        "published_app_workspace_builds",
        ["origin_run_id"],
        unique=False,
    )

    with op.batch_alter_table("published_app_revisions") as batch_op:
        batch_op.add_column(sa.Column("workspace_build_id", postgresql.UUID(as_uuid=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_published_app_revisions_workspace_build_id",
            "published_app_workspace_builds",
            ["workspace_build_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(batch_op.f("ix_published_app_revisions_workspace_build_id"), ["workspace_build_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("published_app_revisions") as batch_op:
        batch_op.drop_index(batch_op.f("ix_published_app_revisions_workspace_build_id"))
        batch_op.drop_constraint("fk_published_app_revisions_workspace_build_id", type_="foreignkey")
        batch_op.drop_column("workspace_build_id")

    op.drop_index(op.f("ix_published_app_workspace_builds_origin_run_id"), table_name="published_app_workspace_builds")
    op.drop_index(op.f("ix_published_app_workspace_builds_origin_kind"), table_name="published_app_workspace_builds")
    op.drop_index(op.f("ix_published_app_workspace_builds_source_revision_id"), table_name="published_app_workspace_builds")
    op.drop_index(op.f("ix_published_app_workspace_builds_published_app_id"), table_name="published_app_workspace_builds")
    op.drop_index("ix_published_app_workspace_builds_app_updated_at_desc", table_name="published_app_workspace_builds")
    op.drop_table("published_app_workspace_builds")

    bind = op.get_bind()
    workspace_build_status_enum.drop(bind, checkfirst=True)
