"""add draft dev sessions and async publish jobs for published apps

Revision ID: f1a2b3c4d5e7
Revises: e3f4a5b6c7d8
Create Date: 2026-02-14 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e7"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


published_app_draft_dev_session_status_enum = postgresql.ENUM(
    "starting",
    "running",
    "stopped",
    "expired",
    "error",
    name="publishedappdraftdevsessionstatus",
    create_type=False,
)

published_app_publish_job_status_enum = postgresql.ENUM(
    "queued",
    "running",
    "succeeded",
    "failed",
    name="publishedapppublishjobstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    published_app_draft_dev_session_status_enum.create(bind, checkfirst=True)
    published_app_publish_job_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "published_app_draft_dev_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            published_app_draft_dev_session_status_enum,
            nullable=False,
            server_default="starting",
        ),
        sa.Column("sandbox_id", sa.String(length=128), nullable=True),
        sa.Column("preview_url", sa.String(), nullable=True),
        sa.Column("idle_timeout_seconds", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dependency_hash", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["published_app_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("published_app_id", "user_id", name="uq_published_app_draft_dev_session_scope"),
    )
    op.create_index(
        op.f("ix_published_app_draft_dev_sessions_published_app_id"),
        "published_app_draft_dev_sessions",
        ["published_app_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_draft_dev_sessions_user_id"),
        "published_app_draft_dev_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_draft_dev_sessions_revision_id"),
        "published_app_draft_dev_sessions",
        ["revision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_draft_dev_sessions_expires_at"),
        "published_app_draft_dev_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_published_app_draft_dev_sessions_scope",
        "published_app_draft_dev_sessions",
        ["published_app_id", "user_id"],
        unique=False,
    )

    op.create_table(
        "published_app_publish_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("saved_draft_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            published_app_publish_job_status_enum,
            nullable=False,
            server_default="queued",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("diagnostics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_revision_id"], ["published_app_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["saved_draft_revision_id"], ["published_app_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["published_revision_id"], ["published_app_revisions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_published_app_publish_jobs_published_app_id"),
        "published_app_publish_jobs",
        ["published_app_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_publish_jobs_tenant_id"),
        "published_app_publish_jobs",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_publish_jobs_requested_by"),
        "published_app_publish_jobs",
        ["requested_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_publish_jobs_source_revision_id"),
        "published_app_publish_jobs",
        ["source_revision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_publish_jobs_saved_draft_revision_id"),
        "published_app_publish_jobs",
        ["saved_draft_revision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_publish_jobs_published_revision_id"),
        "published_app_publish_jobs",
        ["published_revision_id"],
        unique=False,
    )
    op.create_index(
        "ix_published_app_publish_jobs_app_created_at",
        "published_app_publish_jobs",
        ["published_app_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_published_app_publish_jobs_app_created_at", table_name="published_app_publish_jobs")
    op.drop_index(op.f("ix_published_app_publish_jobs_published_revision_id"), table_name="published_app_publish_jobs")
    op.drop_index(op.f("ix_published_app_publish_jobs_saved_draft_revision_id"), table_name="published_app_publish_jobs")
    op.drop_index(op.f("ix_published_app_publish_jobs_source_revision_id"), table_name="published_app_publish_jobs")
    op.drop_index(op.f("ix_published_app_publish_jobs_requested_by"), table_name="published_app_publish_jobs")
    op.drop_index(op.f("ix_published_app_publish_jobs_tenant_id"), table_name="published_app_publish_jobs")
    op.drop_index(op.f("ix_published_app_publish_jobs_published_app_id"), table_name="published_app_publish_jobs")
    op.drop_table("published_app_publish_jobs")

    op.drop_index("ix_published_app_draft_dev_sessions_scope", table_name="published_app_draft_dev_sessions")
    op.drop_index(op.f("ix_published_app_draft_dev_sessions_expires_at"), table_name="published_app_draft_dev_sessions")
    op.drop_index(op.f("ix_published_app_draft_dev_sessions_revision_id"), table_name="published_app_draft_dev_sessions")
    op.drop_index(op.f("ix_published_app_draft_dev_sessions_user_id"), table_name="published_app_draft_dev_sessions")
    op.drop_index(op.f("ix_published_app_draft_dev_sessions_published_app_id"), table_name="published_app_draft_dev_sessions")
    op.drop_table("published_app_draft_dev_sessions")

    bind = op.get_bind()
    published_app_publish_job_status_enum.drop(bind, checkfirst=True)
    published_app_draft_dev_session_status_enum.drop(bind, checkfirst=True)
