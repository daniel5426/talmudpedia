"""add prompt library

Revision ID: a1b2c3d4e5f6
Revises: fc2d3e4f5a6
Create Date: 2026-03-19 13:20:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "fc2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


prompt_scope_enum = postgresql.ENUM("tenant", "global", name="promptscope", create_type=False)
prompt_status_enum = postgresql.ENUM("active", "archived", name="promptstatus", create_type=False)
prompt_ownership_enum = postgresql.ENUM("manual", "system", name="promptownership", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        prompt_scope_enum.create(bind, checkfirst=True)
        prompt_status_enum.create(bind, checkfirst=True)
        prompt_ownership_enum.create(bind, checkfirst=True)

    op.create_table(
        "prompt_library",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("scope", prompt_scope_enum if bind.dialect.name == "postgresql" else sa.String(length=32), nullable=False),
        sa.Column("status", prompt_status_enum if bind.dialect.name == "postgresql" else sa.String(length=32), nullable=False),
        sa.Column("ownership", prompt_ownership_enum if bind.dialect.name == "postgresql" else sa.String(length=32), nullable=False),
        sa.Column("managed_by", sa.String(), nullable=True),
        sa.Column("allowed_surfaces", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb") if bind.dialect.name == "postgresql" else "[]"),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb") if bind.dialect.name == "postgresql" else "[]"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_prompt_library_name"), "prompt_library", ["name"], unique=False)
    op.create_index(op.f("ix_prompt_library_ownership"), "prompt_library", ["ownership"], unique=False)
    op.create_index(op.f("ix_prompt_library_scope"), "prompt_library", ["scope"], unique=False)
    op.create_index(op.f("ix_prompt_library_status"), "prompt_library", ["status"], unique=False)
    op.create_index(op.f("ix_prompt_library_tenant_id"), "prompt_library", ["tenant_id"], unique=False)
    op.create_index("ix_prompt_library_tenant_name", "prompt_library", ["tenant_id", "name"], unique=False)

    op.create_table(
        "prompt_library_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("allowed_surfaces", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb") if bind.dialect.name == "postgresql" else "[]"),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb") if bind.dialect.name == "postgresql" else "[]"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompt_library.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_prompt_library_versions_prompt_id"), "prompt_library_versions", ["prompt_id"], unique=False)
    op.create_index(
        "uq_prompt_library_versions_prompt_version",
        "prompt_library_versions",
        ["prompt_id", "version"],
        unique=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index("uq_prompt_library_versions_prompt_version", table_name="prompt_library_versions")
    op.drop_index(op.f("ix_prompt_library_versions_prompt_id"), table_name="prompt_library_versions")
    op.drop_table("prompt_library_versions")

    op.drop_index("ix_prompt_library_tenant_name", table_name="prompt_library")
    op.drop_index(op.f("ix_prompt_library_tenant_id"), table_name="prompt_library")
    op.drop_index(op.f("ix_prompt_library_status"), table_name="prompt_library")
    op.drop_index(op.f("ix_prompt_library_scope"), table_name="prompt_library")
    op.drop_index(op.f("ix_prompt_library_ownership"), table_name="prompt_library")
    op.drop_index(op.f("ix_prompt_library_name"), table_name="prompt_library")
    op.drop_table("prompt_library")

    if bind.dialect.name == "postgresql":
        prompt_ownership_enum.drop(bind, checkfirst=True)
        prompt_status_enum.drop(bind, checkfirst=True)
        prompt_scope_enum.drop(bind, checkfirst=True)
