"""add published app accounts and thread owner

Revision ID: 8b1d2e3f4a5c
Revises: 6c8b7a2d9e4f
Create Date: 2026-03-09 12:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "8b1d2e3f4a5c"
down_revision: Union[str, Sequence[str], None] = "6c8b7a2d9e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ACCOUNT_STATUS_ENUM = postgresql.ENUM(
    "active",
    "blocked",
    name="publishedappaccountstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    _ACCOUNT_STATUS_ENUM.create(bind, checkfirst=True)

    op.create_table(
        "published_app_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("global_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("avatar", sa.String(), nullable=True),
        sa.Column("hashed_password", sa.String(), nullable=True),
        sa.Column("status", _ACCOUNT_STATUS_ENUM, nullable=False, server_default="active"),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["global_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("published_app_id", "email", name="uq_published_app_account_email"),
    )
    op.create_index(op.f("ix_published_app_accounts_published_app_id"), "published_app_accounts", ["published_app_id"], unique=False)
    op.create_index(op.f("ix_published_app_accounts_global_user_id"), "published_app_accounts", ["global_user_id"], unique=False)

    op.alter_column("published_app_sessions", "user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.add_column("published_app_sessions", sa.Column("app_account_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_published_app_sessions_app_account_id"), "published_app_sessions", ["app_account_id"], unique=False)
    op.create_foreign_key(
        "fk_published_app_sessions_app_account_id",
        "published_app_sessions",
        "published_app_accounts",
        ["app_account_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_published_app_sessions_app_account",
        "published_app_sessions",
        ["published_app_id", "app_account_id"],
        unique=False,
    )

    op.alter_column("published_app_external_identities", "user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.add_column("published_app_external_identities", sa.Column("app_account_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(
        op.f("ix_published_app_external_identities_app_account_id"),
        "published_app_external_identities",
        ["app_account_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_published_app_external_identities_app_account_id",
        "published_app_external_identities",
        "published_app_accounts",
        ["app_account_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column("agent_threads", sa.Column("app_account_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_agent_threads_app_account_id"), "agent_threads", ["app_account_id"], unique=False)
    op.create_foreign_key(
        "fk_agent_threads_app_account_id",
        "agent_threads",
        "published_app_accounts",
        ["app_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_agent_threads_app_account_activity",
        "agent_threads",
        ["tenant_id", "app_account_id", "last_activity_at"],
        unique=False,
    )

    op.add_column("agent_runs", sa.Column("published_app_account_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_agent_runs_published_app_account_id"), "agent_runs", ["published_app_account_id"], unique=False)
    op.create_foreign_key(
        "fk_agent_runs_published_app_account_id",
        "agent_runs",
        "published_app_accounts",
        ["published_app_account_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_index("ix_agent_runs_coding_scope_status_created_at", table_name="agent_runs")
    op.create_index(
        "ix_agent_runs_coding_scope_status_created_at",
        "agent_runs",
        ["surface", "published_app_id", "published_app_account_id", "initiator_user_id", "status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_runs_coding_scope_status_created_at", table_name="agent_runs")
    op.create_index(
        "ix_agent_runs_coding_scope_status_created_at",
        "agent_runs",
        ["surface", "published_app_id", "initiator_user_id", "status", "created_at"],
        unique=False,
    )
    op.drop_constraint("fk_agent_runs_published_app_account_id", "agent_runs", type_="foreignkey")
    op.drop_index(op.f("ix_agent_runs_published_app_account_id"), table_name="agent_runs")
    op.drop_column("agent_runs", "published_app_account_id")

    op.drop_index("ix_agent_threads_app_account_activity", table_name="agent_threads")
    op.drop_constraint("fk_agent_threads_app_account_id", "agent_threads", type_="foreignkey")
    op.drop_index(op.f("ix_agent_threads_app_account_id"), table_name="agent_threads")
    op.drop_column("agent_threads", "app_account_id")

    op.drop_constraint("fk_published_app_external_identities_app_account_id", "published_app_external_identities", type_="foreignkey")
    op.drop_index(op.f("ix_published_app_external_identities_app_account_id"), table_name="published_app_external_identities")
    op.drop_column("published_app_external_identities", "app_account_id")
    op.alter_column("published_app_external_identities", "user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)

    op.drop_index("ix_published_app_sessions_app_account", table_name="published_app_sessions")
    op.drop_constraint("fk_published_app_sessions_app_account_id", "published_app_sessions", type_="foreignkey")
    op.drop_index(op.f("ix_published_app_sessions_app_account_id"), table_name="published_app_sessions")
    op.drop_column("published_app_sessions", "app_account_id")
    op.alter_column("published_app_sessions", "user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)

    op.drop_index(op.f("ix_published_app_accounts_global_user_id"), table_name="published_app_accounts")
    op.drop_index(op.f("ix_published_app_accounts_published_app_id"), table_name="published_app_accounts")
    op.drop_table("published_app_accounts")

    _ACCOUNT_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
