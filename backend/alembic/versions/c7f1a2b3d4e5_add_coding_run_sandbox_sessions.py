"""add run-scoped coding sandbox sessions

Revision ID: c7f1a2b3d4e5
Revises: 9b6c5d4e3f21, b1c2d3e4f5a6
Create Date: 2026-02-19 01:25:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c7f1a2b3d4e5"
down_revision: Union[str, Sequence[str], None] = ("9b6c5d4e3f21", "b1c2d3e4f5a6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


published_app_coding_run_sandbox_status_enum = postgresql.ENUM(
    "starting",
    "running",
    "stopped",
    "expired",
    "error",
    name="publishedappcodingrunsandboxstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    published_app_coding_run_sandbox_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "published_app_coding_run_sandbox_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            published_app_coding_run_sandbox_status_enum,
            nullable=False,
            server_default="starting",
        ),
        sa.Column("sandbox_id", sa.String(length=128), nullable=True),
        sa.Column("preview_url", sa.String(), nullable=True),
        sa.Column("workspace_path", sa.String(), nullable=True),
        sa.Column("idle_timeout_seconds", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("run_timeout_seconds", sa.Integer(), nullable=False, server_default="1200"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dependency_hash", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["published_app_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_published_app_coding_run_sandbox_run_id"),
    )
    op.create_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_run_id"),
        "published_app_coding_run_sandbox_sessions",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_tenant_id"),
        "published_app_coding_run_sandbox_sessions",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_published_app_id"),
        "published_app_coding_run_sandbox_sessions",
        ["published_app_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_revision_id"),
        "published_app_coding_run_sandbox_sessions",
        ["revision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_user_id"),
        "published_app_coding_run_sandbox_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_sandbox_id"),
        "published_app_coding_run_sandbox_sessions",
        ["sandbox_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_expires_at"),
        "published_app_coding_run_sandbox_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_published_app_coding_run_sandbox_app_created_at",
        "published_app_coding_run_sandbox_sessions",
        ["published_app_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_published_app_coding_run_sandbox_app_created_at",
        table_name="published_app_coding_run_sandbox_sessions",
    )
    op.drop_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_expires_at"),
        table_name="published_app_coding_run_sandbox_sessions",
    )
    op.drop_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_sandbox_id"),
        table_name="published_app_coding_run_sandbox_sessions",
    )
    op.drop_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_user_id"),
        table_name="published_app_coding_run_sandbox_sessions",
    )
    op.drop_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_revision_id"),
        table_name="published_app_coding_run_sandbox_sessions",
    )
    op.drop_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_published_app_id"),
        table_name="published_app_coding_run_sandbox_sessions",
    )
    op.drop_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_tenant_id"),
        table_name="published_app_coding_run_sandbox_sessions",
    )
    op.drop_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_run_id"),
        table_name="published_app_coding_run_sandbox_sessions",
    )
    op.drop_table("published_app_coding_run_sandbox_sessions")

    bind = op.get_bind()
    published_app_coding_run_sandbox_status_enum.drop(bind, checkfirst=True)
