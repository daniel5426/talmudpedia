"""add cloudflare artifact runtime

Revision ID: f1c2d3e4b5a6
Revises: e7c1d2a3b4c5
Create Date: 2026-03-11 10:30:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f1c2d3e4b5a6"
down_revision: Union[str, Sequence[str], None] = "e7c1d2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        return {col["name"] for col in inspector.get_columns(table_name)}
    except Exception:
        return set()


def _table_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        return set(inspector.get_table_names())
    except Exception:
        return set()


def _pg_type_exists(type_name: str) -> bool:
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_type
            WHERE typname = :type_name
            LIMIT 1
            """
        ),
        {"type_name": type_name},
    ).first()
    return row is not None


def upgrade() -> None:
    revision_columns = _column_names("artifact_revisions")
    if "source_files" not in revision_columns:
        op.add_column(
            "artifact_revisions",
            sa.Column("source_files", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        )
    if "entry_module_path" not in revision_columns:
        op.add_column(
            "artifact_revisions",
            sa.Column("entry_module_path", sa.String(), nullable=False, server_default="handler.py"),
        )
    if "build_hash" not in revision_columns:
        op.add_column(
            "artifact_revisions",
            sa.Column("build_hash", sa.String(length=64), nullable=False, server_default=""),
        )
        op.create_index("ix_artifact_revisions_build_hash", "artifact_revisions", ["build_hash"], unique=False)

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE artifact_revisions
            SET source_files = jsonb_build_array(
                jsonb_build_object(
                    'path', COALESCE(NULLIF(entry_module_path, ''), 'handler.py'),
                    'content', COALESCE(source_code, '')
                )
            )
            WHERE source_files = '[]'::jsonb
            """
        )
    )
    bind.execute(sa.text("UPDATE artifact_revisions SET build_hash = bundle_hash WHERE COALESCE(build_hash, '') = ''"))
    op.alter_column("artifact_revisions", "source_code", existing_type=sa.Text(), nullable=True)
    op.alter_column("artifact_revisions", "source_files", server_default=None)
    op.alter_column("artifact_revisions", "entry_module_path", server_default=None)
    op.alter_column("artifact_revisions", "build_hash", server_default=None)

    run_columns = _column_names("artifact_runs")
    if "runtime_metadata" not in run_columns:
        op.add_column(
            "artifact_runs",
            sa.Column("runtime_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        )
        op.alter_column("artifact_runs", "runtime_metadata", server_default=None)

    op.execute("UPDATE artifact_runs SET sandbox_backend = 'cloudflare_workers' WHERE sandbox_backend = 'difysandbox'")

    tables = _table_names()
    deployment_status = postgresql.ENUM("pending", "ready", "failed", name="artifactdeploymentstatus", create_type=False)
    if not _pg_type_exists("artifactdeploymentstatus"):
        deployment_status.create(bind, checkfirst=False)

    if "artifact_deployments" not in tables:
        op.create_table(
            "artifact_deployments",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("namespace", sa.String(), nullable=False),
            sa.Column("build_hash", sa.String(length=64), nullable=False),
            sa.Column("status", deployment_status, nullable=False, server_default="pending"),
            sa.Column("worker_name", sa.String(), nullable=False),
            sa.Column("script_name", sa.String(), nullable=False),
            sa.Column("deployment_id", sa.String(), nullable=True),
            sa.Column("version_id", sa.String(), nullable=True),
            sa.Column("runtime_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("error_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["revision_id"], ["artifact_revisions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_artifact_deployments_build_hash", "artifact_deployments", ["build_hash"], unique=False)
        op.create_index("ix_artifact_deployments_revision_id", "artifact_deployments", ["revision_id"], unique=False)
        op.create_index("ix_artifact_deployments_tenant_id", "artifact_deployments", ["tenant_id"], unique=False)
        op.create_index(
            "uq_artifact_deployments_namespace_build_hash",
            "artifact_deployments",
            ["tenant_id", "namespace", "build_hash"],
            unique=True,
        )

    if "artifact_tenant_runtime_policies" not in tables:
        op.create_table(
            "artifact_tenant_runtime_policies",
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("interactive_concurrency_limit", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("background_concurrency_limit", sa.Integer(), nullable=False, server_default="2"),
            sa.Column("test_concurrency_limit", sa.Integer(), nullable=False, server_default="2"),
            sa.Column("interactive_cpu_ms", sa.Integer(), nullable=False, server_default="30000"),
            sa.Column("background_cpu_ms", sa.Integer(), nullable=False, server_default="60000"),
            sa.Column("test_cpu_ms", sa.Integer(), nullable=False, server_default="30000"),
            sa.Column("interactive_subrequests", sa.Integer(), nullable=False, server_default="50"),
            sa.Column("background_subrequests", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("test_subrequests", sa.Integer(), nullable=False, server_default="50"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("tenant_id"),
        )


def downgrade() -> None:
    tables = _table_names()
    if "artifact_tenant_runtime_policies" in tables:
        op.drop_table("artifact_tenant_runtime_policies")
    if "artifact_deployments" in tables:
        op.drop_index("uq_artifact_deployments_namespace_build_hash", table_name="artifact_deployments")
        op.drop_index("ix_artifact_deployments_tenant_id", table_name="artifact_deployments")
        op.drop_index("ix_artifact_deployments_revision_id", table_name="artifact_deployments")
        op.drop_index("ix_artifact_deployments_build_hash", table_name="artifact_deployments")
        op.drop_table("artifact_deployments")
    if _pg_type_exists("artifactdeploymentstatus"):
        postgresql.ENUM("pending", "ready", "failed", name="artifactdeploymentstatus", create_type=False).drop(
            op.get_bind(),
            checkfirst=False,
        )

    run_columns = _column_names("artifact_runs")
    if "runtime_metadata" in run_columns:
        op.drop_column("artifact_runs", "runtime_metadata")

    revision_columns = _column_names("artifact_revisions")
    if "build_hash" in revision_columns:
        op.drop_index("ix_artifact_revisions_build_hash", table_name="artifact_revisions")
        op.drop_column("artifact_revisions", "build_hash")
    if "entry_module_path" in revision_columns:
        op.drop_column("artifact_revisions", "entry_module_path")
    if "source_files" in revision_columns:
        op.drop_column("artifact_revisions", "source_files")
    op.alter_column("artifact_revisions", "source_code", existing_type=sa.Text(), nullable=False)
