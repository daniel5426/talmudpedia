"""add shared published app draft workspaces

Revision ID: 6c8b7a2d9e4f
Revises: 4f2e8c1a9d7b
Create Date: 2026-03-08 23:55:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "6c8b7a2d9e4f"
down_revision: Union[str, Sequence[str], None] = "4f2e8c1a9d7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_WORKSPACE_STATUS_ENUM = "publishedappdraftworkspacestatus"


def _is_postgresql() -> bool:
    bind = op.get_bind()
    return str(getattr(bind.dialect, "name", "") or "").lower() == "postgresql"


def upgrade() -> None:
    workspace_status_type = postgresql.ENUM(
        "starting",
        "syncing",
        "serving",
        "degraded",
        "stopping",
        "stopped",
        "error",
        name=_WORKSPACE_STATUS_ENUM,
        create_type=False,
    )
    if _is_postgresql():
        workspace_status_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "published_app_draft_workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            workspace_status_type,
            nullable=False,
            server_default="stopped",
        ),
        sa.Column("sprite_name", sa.String(length=128), nullable=False),
        sa.Column("sandbox_id", sa.String(length=128), nullable=True),
        sa.Column("runtime_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("runtime_backend", sa.String(length=32), nullable=True),
        sa.Column(
            "backend_metadata",
            postgresql.JSONB(astext_type=sa.Text()) if _is_postgresql() else sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb") if _is_postgresql() else None,
        ),
        sa.Column("preview_url", sa.String(), nullable=True),
        sa.Column("live_workspace_path", sa.String(length=512), nullable=True),
        sa.Column("stage_workspace_path", sa.String(length=512), nullable=True),
        sa.Column("publish_workspace_path", sa.String(length=512), nullable=True),
        sa.Column("preview_service_name", sa.String(length=128), nullable=True),
        sa.Column("opencode_service_name", sa.String(length=128), nullable=True),
        sa.Column("dependency_hash", sa.String(length=64), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detached_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["published_app_revisions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("published_app_id", name="uq_published_app_draft_workspace_app"),
    )
    op.create_index(
        op.f("ix_published_app_draft_workspaces_published_app_id"),
        "published_app_draft_workspaces",
        ["published_app_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_draft_workspaces_revision_id"),
        "published_app_draft_workspaces",
        ["revision_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_draft_workspaces_sprite_name"),
        "published_app_draft_workspaces",
        ["sprite_name"],
        unique=True,
    )
    op.create_index(
        op.f("ix_published_app_draft_workspaces_sandbox_id"),
        "published_app_draft_workspaces",
        ["sandbox_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_draft_workspaces_last_activity_at"),
        "published_app_draft_workspaces",
        ["last_activity_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_draft_workspaces_detached_at"),
        "published_app_draft_workspaces",
        ["detached_at"],
        unique=False,
    )

    op.add_column(
        "published_app_draft_dev_sessions",
        sa.Column("draft_workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_published_app_draft_dev_sessions_draft_workspace_id"),
        "published_app_draft_dev_sessions",
        ["draft_workspace_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_published_app_draft_dev_sessions_draft_workspace_id",
        "published_app_draft_dev_sessions",
        "published_app_draft_workspaces",
        ["draft_workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_published_app_draft_dev_sessions_draft_workspace_id",
        "published_app_draft_dev_sessions",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_published_app_draft_dev_sessions_draft_workspace_id"),
        table_name="published_app_draft_dev_sessions",
    )
    op.drop_column("published_app_draft_dev_sessions", "draft_workspace_id")

    op.drop_index(op.f("ix_published_app_draft_workspaces_detached_at"), table_name="published_app_draft_workspaces")
    op.drop_index(op.f("ix_published_app_draft_workspaces_last_activity_at"), table_name="published_app_draft_workspaces")
    op.drop_index(op.f("ix_published_app_draft_workspaces_sandbox_id"), table_name="published_app_draft_workspaces")
    op.drop_index(op.f("ix_published_app_draft_workspaces_sprite_name"), table_name="published_app_draft_workspaces")
    op.drop_index(op.f("ix_published_app_draft_workspaces_revision_id"), table_name="published_app_draft_workspaces")
    op.drop_index(op.f("ix_published_app_draft_workspaces_published_app_id"), table_name="published_app_draft_workspaces")
    op.drop_table("published_app_draft_workspaces")

    if _is_postgresql():
        op.execute(f"DROP TYPE IF EXISTS {_WORKSPACE_STATUS_ENUM}")
