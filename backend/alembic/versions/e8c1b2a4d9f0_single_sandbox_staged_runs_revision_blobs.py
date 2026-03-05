"""single_sandbox_staged_runs_revision_blobs

Revision ID: e8c1b2a4d9f0
Revises: d4e9f1a2b3c4
Create Date: 2026-02-21 17:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError


# revision identifiers, used by Alembic.
revision = "e8c1b2a4d9f0"
down_revision = "d4e9f1a2b3c4"
branch_labels = None
depends_on = None


def _is_lock_or_statement_timeout(exc: DBAPIError) -> bool:
    original = getattr(exc, "orig", None)
    sqlstate = str(getattr(original, "sqlstate", "") or "").strip()
    message = str(original or exc).lower()
    return sqlstate in {"55P03", "57014"} or "lock timeout" in message or "statement timeout" in message


def _drop_legacy_coding_run_sandbox_objects_best_effort() -> None:
    bind = op.get_bind()
    # Avoid long migration stalls while waiting on old-table locks.
    bind.execute(sa.text("SET LOCAL lock_timeout = '2s'"))
    bind.execute(sa.text("SET LOCAL statement_timeout = '15s'"))

    table_dropped = False
    try:
        # Use a savepoint so lock/statement timeout does not abort the outer migration transaction.
        with bind.begin_nested():
            bind.execute(sa.text("DROP TABLE IF EXISTS published_app_coding_run_sandbox_sessions"))
        table_dropped = True
    except DBAPIError as exc:
        if not _is_lock_or_statement_timeout(exc):
            raise
        print(
            "[alembic] Skipping DROP TABLE published_app_coding_run_sandbox_sessions "
            "due to lock/statement timeout; retry cleanup later."
        )

    if not table_dropped:
        return

    try:
        # Same savepoint protection for enum drop.
        with bind.begin_nested():
            bind.execute(sa.text("DROP TYPE IF EXISTS published_app_coding_run_sandbox_status"))
    except DBAPIError as exc:
        if not _is_lock_or_statement_timeout(exc):
            raise
        print(
            "[alembic] Skipping DROP TYPE published_app_coding_run_sandbox_status "
            "due to lock/statement timeout; retry cleanup later."
        )


def upgrade() -> None:
    op.add_column(
        "published_app_revisions",
        sa.Column(
            "manifest_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.create_table(
        "published_app_revision_blobs",
        sa.Column("blob_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(), nullable=True),
        sa.Column("inline_content", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("blob_hash"),
    )

    op.add_column(
        "published_app_draft_dev_sessions",
        sa.Column("active_coding_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "published_app_draft_dev_sessions",
        sa.Column("active_coding_run_locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "published_app_draft_dev_sessions",
        sa.Column("active_coding_run_client_message_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        op.f("ix_published_app_draft_dev_sessions_active_coding_run_id"),
        "published_app_draft_dev_sessions",
        ["active_coding_run_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_published_app_draft_dev_sessions_active_coding_run_id",
        "published_app_draft_dev_sessions",
        "agent_runs",
        ["active_coding_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Hard cutover reset for legacy inline-file revisions.
    op.execute(
        """
        UPDATE published_apps
        SET current_draft_revision_id = NULL,
            current_published_revision_id = NULL
        """
    )
    op.execute("DELETE FROM published_app_revisions")

    # Remove legacy coding-run sandbox state path (best effort if old table is lock-contended).
    _drop_legacy_coding_run_sandbox_objects_best_effort()


def downgrade() -> None:
    published_app_coding_run_sandbox_status_enum = postgresql.ENUM(
        "starting",
        "running",
        "stopped",
        "expired",
        "error",
        name="published_app_coding_run_sandbox_status",
    )
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
        sa.Column("status", published_app_coding_run_sandbox_status_enum, nullable=False),
        sa.Column("sandbox_id", sa.String(length=128), nullable=True),
        sa.Column("preview_url", sa.String(), nullable=True),
        sa.Column("workspace_path", sa.String(), nullable=True),
        sa.Column("idle_timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("180")),
        sa.Column("run_timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("1200")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dependency_hash", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["published_app_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_published_app_coding_run_sandbox_run_id"),
    )
    op.create_index(
        "ix_published_app_coding_run_sandbox_app_created_at",
        "published_app_coding_run_sandbox_sessions",
        ["published_app_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_expires_at"),
        "published_app_coding_run_sandbox_sessions",
        ["expires_at"],
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
        op.f("ix_published_app_coding_run_sandbox_sessions_run_id"),
        "published_app_coding_run_sandbox_sessions",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_sandbox_id"),
        "published_app_coding_run_sandbox_sessions",
        ["sandbox_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_tenant_id"),
        "published_app_coding_run_sandbox_sessions",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_coding_run_sandbox_sessions_user_id"),
        "published_app_coding_run_sandbox_sessions",
        ["user_id"],
        unique=False,
    )

    op.drop_constraint(
        "fk_published_app_draft_dev_sessions_active_coding_run_id",
        "published_app_draft_dev_sessions",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_published_app_draft_dev_sessions_active_coding_run_id"),
        table_name="published_app_draft_dev_sessions",
    )
    op.drop_column("published_app_draft_dev_sessions", "active_coding_run_client_message_id")
    op.drop_column("published_app_draft_dev_sessions", "active_coding_run_locked_at")
    op.drop_column("published_app_draft_dev_sessions", "active_coding_run_id")

    op.drop_table("published_app_revision_blobs")
    op.drop_column("published_app_revisions", "manifest_json")
