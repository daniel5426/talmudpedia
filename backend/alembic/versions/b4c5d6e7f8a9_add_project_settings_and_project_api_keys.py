"""add project settings and project api keys

Revision ID: b4c5d6e7f8a9
Revises: 6c4d5e7f8a9b, a7c3e5d9b1f2, a8f3c1d2e4b5, ff9a2b3c4d5e
Create Date: 2026-04-19 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = ("6c4d5e7f8a9b", "a7c3e5d9b1f2", "a8f3c1d2e4b5", "ff9a2b3c4d5e")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PROJECT_API_KEY_STATUS_ENUM = postgresql.ENUM(
    "active",
    "revoked",
    name="projectapikeystatus",
    create_type=False,
)


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _table_exists(inspector, "projects") and not _column_exists(inspector, "projects", "settings"):
        op.add_column(
            "projects",
            sa.Column(
                "settings",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )

    _PROJECT_API_KEY_STATUS_ENUM.create(bind, checkfirst=True)

    inspector = inspect(bind)
    if not _table_exists(inspector, "project_api_keys"):
        op.create_table(
            "project_api_keys",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("key_prefix", sa.String(), nullable=False),
            sa.Column("secret_hash", sa.String(), nullable=False),
            sa.Column(
                "scopes",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("status", _PROJECT_API_KEY_STATUS_ENUM, nullable=False, server_default="active"),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("key_prefix", name="uq_project_api_keys_key_prefix"),
        )

    inspector = inspect(bind)
    if not _index_exists(inspector, "project_api_keys", op.f("ix_project_api_keys_project_id")):
        op.create_index(op.f("ix_project_api_keys_project_id"), "project_api_keys", ["project_id"], unique=False)
    if not _index_exists(inspector, "project_api_keys", op.f("ix_project_api_keys_tenant_id")):
        op.create_index(op.f("ix_project_api_keys_tenant_id"), "project_api_keys", ["tenant_id"], unique=False)
    if not _index_exists(inspector, "project_api_keys", op.f("ix_project_api_keys_key_prefix")):
        op.create_index(op.f("ix_project_api_keys_key_prefix"), "project_api_keys", ["key_prefix"], unique=False)
    if not _index_exists(inspector, "project_api_keys", op.f("ix_project_api_keys_created_by")):
        op.create_index(op.f("ix_project_api_keys_created_by"), "project_api_keys", ["created_by"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_project_api_keys_created_by"), table_name="project_api_keys")
    op.drop_index(op.f("ix_project_api_keys_key_prefix"), table_name="project_api_keys")
    op.drop_index(op.f("ix_project_api_keys_tenant_id"), table_name="project_api_keys")
    op.drop_index(op.f("ix_project_api_keys_project_id"), table_name="project_api_keys")
    op.drop_table("project_api_keys")
    _PROJECT_API_KEY_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
    op.drop_column("projects", "settings")
