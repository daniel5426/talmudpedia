"""add artifact runtime v1 tables

Revision ID: c4b2f6a9d1e0
Revises: 8b1d2e3f4a5c, aa19c4e7d2b1
Create Date: 2026-03-10 12:00:00.000000

"""
from __future__ import annotations

import json
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c4b2f6a9d1e0"
down_revision: Union[str, Sequence[str], None] = ("8b1d2e3f4a5c", "aa19c4e7d2b1")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


artifact_scope_enum = postgresql.ENUM("rag", "agent", "both", "tool", name="artifactscope", create_type=False)
artifact_status_enum = postgresql.ENUM("draft", "published", "disabled", name="artifactstatus", create_type=False)
artifact_run_domain_enum = postgresql.ENUM("test", "agent", "rag", "tool", name="artifactrundomain", create_type=False)
artifact_run_status_enum = postgresql.ENUM(
    "queued",
    "running",
    "completed",
    "failed",
    "cancel_requested",
    "cancelled",
    name="artifactrunstatus",
    create_type=False,
)


def _has_type(type_name: str) -> bool:
    bind = op.get_bind()
    query = sa.text(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_type t
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE t.typname = :type_name
              AND n.nspname = current_schema()
        )
        """
    )
    return bool(bind.execute(query, {"type_name": type_name}).scalar())


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        return {col["name"] for col in inspector.get_columns(table_name)}
    except Exception:
        return set()


def upgrade() -> None:
    bind = op.get_bind()

    if not _has_type("artifactscope"):
        artifact_scope_enum.create(bind, checkfirst=False)
    if not _has_type("artifactstatus"):
        artifact_status_enum.create(bind, checkfirst=False)
    if not _has_type("artifactrundomain"):
        artifact_run_domain_enum.create(bind, checkfirst=False)
    if not _has_type("artifactrunstatus"):
        artifact_run_status_enum.create(bind, checkfirst=False)

    if not _has_table("artifacts"):
        op.create_table(
            "artifacts",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("slug", sa.String(), nullable=False),
            sa.Column("display_name", sa.String(), nullable=False),
            sa.Column("description", sa.String(), nullable=True),
            sa.Column("category", sa.String(), nullable=False, server_default=sa.text("'custom'")),
            sa.Column("input_type", sa.String(), nullable=False, server_default=sa.text("'raw_documents'")),
            sa.Column("output_type", sa.String(), nullable=False, server_default=sa.text("'raw_documents'")),
            sa.Column("scope", artifact_scope_enum, nullable=False, server_default=sa.text("'rag'")),
            sa.Column("status", artifact_status_enum, nullable=False, server_default=sa.text("'draft'")),
            sa.Column("latest_draft_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("latest_published_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("legacy_custom_operator_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("custom_operators.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_artifacts_tenant_id", "artifacts", ["tenant_id"], unique=False)
        op.create_index("uq_artifacts_tenant_slug", "artifacts", ["tenant_id", "slug"], unique=True)

    if not _has_table("artifact_revisions"):
        op.create_table(
            "artifact_revisions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=True),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("version_label", sa.String(), nullable=False, server_default=sa.text("'draft'")),
            sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_ephemeral", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("display_name", sa.String(), nullable=False),
            sa.Column("description", sa.String(), nullable=True),
            sa.Column("category", sa.String(), nullable=False, server_default=sa.text("'custom'")),
            sa.Column("input_type", sa.String(), nullable=False, server_default=sa.text("'raw_documents'")),
            sa.Column("output_type", sa.String(), nullable=False, server_default=sa.text("'raw_documents'")),
            sa.Column("scope", artifact_scope_enum, nullable=False, server_default=sa.text("'rag'")),
            sa.Column("source_code", sa.Text(), nullable=False),
            sa.Column("manifest_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("config_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("outputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("reads", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("writes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("dependency_hash", sa.String(length=64), nullable=False, server_default=sa.text("''")),
            sa.Column("bundle_hash", sa.String(length=64), nullable=False, server_default=sa.text("''")),
            sa.Column("bundle_storage_key", sa.String(), nullable=True),
            sa.Column("bundle_inline_bytes", sa.LargeBinary(), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_artifact_revisions_artifact_id", "artifact_revisions", ["artifact_id"], unique=False)
        op.create_index("ix_artifact_revisions_tenant_id", "artifact_revisions", ["tenant_id"], unique=False)
        op.create_index("ix_artifact_revisions_bundle_hash", "artifact_revisions", ["bundle_hash"], unique=False)

    if not _has_table("artifact_runs"):
        op.create_table(
            "artifact_runs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True),
            sa.Column("revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifact_revisions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("domain", artifact_run_domain_enum, nullable=False, server_default=sa.text("'test'")),
            sa.Column("status", artifact_run_status_enum, nullable=False, server_default=sa.text("'queued'")),
            sa.Column("queue_class", sa.String(), nullable=False, server_default=sa.text("'artifact_test'")),
            sa.Column("sandbox_backend", sa.String(), nullable=False, server_default=sa.text("'difysandbox'")),
            sa.Column("worker_id", sa.String(), nullable=True),
            sa.Column("sandbox_session_id", sa.String(), nullable=True),
            sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("config_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("context_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("error_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("stdout_excerpt", sa.Text(), nullable=True),
            sa.Column("stderr_excerpt", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
        )
        op.create_index("ix_artifact_runs_tenant_id", "artifact_runs", ["tenant_id"], unique=False)
        op.create_index("ix_artifact_runs_artifact_id", "artifact_runs", ["artifact_id"], unique=False)
        op.create_index("ix_artifact_runs_revision_id", "artifact_runs", ["revision_id"], unique=False)
        op.create_index("ix_artifact_runs_status", "artifact_runs", ["status"], unique=False)

    if not _has_table("artifact_run_events"):
        op.create_table(
            "artifact_run_events",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifact_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("event_type", sa.String(), nullable=False),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        )
        op.create_index("ix_artifact_run_events_run_id", "artifact_run_events", ["run_id"], unique=False)
        op.create_index("uq_artifact_run_events_run_sequence", "artifact_run_events", ["run_id", "sequence"], unique=True)

    op.create_foreign_key(
        "fk_artifacts_latest_draft_revision_id",
        "artifacts",
        "artifact_revisions",
        ["latest_draft_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_artifacts_latest_published_revision_id",
        "artifacts",
        "artifact_revisions",
        ["latest_published_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _backfill_custom_operators()

    op.alter_column("artifacts", "category", server_default=None)
    op.alter_column("artifacts", "input_type", server_default=None)
    op.alter_column("artifacts", "output_type", server_default=None)
    op.alter_column("artifacts", "scope", server_default=None)
    op.alter_column("artifacts", "status", server_default=None)
    op.alter_column("artifact_revisions", "revision_number", server_default=None)
    op.alter_column("artifact_revisions", "version_label", server_default=None)
    op.alter_column("artifact_revisions", "is_published", server_default=None)
    op.alter_column("artifact_revisions", "is_ephemeral", server_default=None)
    op.alter_column("artifact_revisions", "category", server_default=None)
    op.alter_column("artifact_revisions", "input_type", server_default=None)
    op.alter_column("artifact_revisions", "output_type", server_default=None)
    op.alter_column("artifact_revisions", "scope", server_default=None)
    op.alter_column("artifact_revisions", "manifest_json", server_default=None)
    op.alter_column("artifact_revisions", "config_schema", server_default=None)
    op.alter_column("artifact_revisions", "inputs", server_default=None)
    op.alter_column("artifact_revisions", "outputs", server_default=None)
    op.alter_column("artifact_revisions", "reads", server_default=None)
    op.alter_column("artifact_revisions", "writes", server_default=None)
    op.alter_column("artifact_revisions", "dependency_hash", server_default=None)
    op.alter_column("artifact_revisions", "bundle_hash", server_default=None)
    op.alter_column("artifact_runs", "domain", server_default=None)
    op.alter_column("artifact_runs", "status", server_default=None)
    op.alter_column("artifact_runs", "queue_class", server_default=None)
    op.alter_column("artifact_runs", "sandbox_backend", server_default=None)
    op.alter_column("artifact_runs", "cancel_requested", server_default=None)
    op.alter_column("artifact_runs", "input_payload", server_default=None)
    op.alter_column("artifact_runs", "config_payload", server_default=None)
    op.alter_column("artifact_runs", "context_payload", server_default=None)
    op.alter_column("artifact_run_events", "payload", server_default=None)


def _backfill_custom_operators() -> None:
    if not _has_table("custom_operators"):
        return

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = _column_names("custom_operators")
    if not cols:
        return

    query = sa.text(
        """
        SELECT id, tenant_id, name, display_name, description, category, python_code,
               input_type, output_type, config_schema, scope, created_by, created_at, updated_at
        FROM custom_operators
        """
    )
    rows = list(bind.execute(query).mappings().all())
    if not rows:
        return

    artifact_table = sa.table(
        "artifacts",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.column("slug", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("category", sa.String()),
        sa.column("input_type", sa.String()),
        sa.column("output_type", sa.String()),
        sa.column("scope", sa.String()),
        sa.column("status", sa.String()),
        sa.column("latest_draft_revision_id", postgresql.UUID(as_uuid=True)),
        sa.column("created_by", postgresql.UUID(as_uuid=True)),
        sa.column("legacy_custom_operator_id", postgresql.UUID(as_uuid=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    revision_table = sa.table(
        "artifact_revisions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("artifact_id", postgresql.UUID(as_uuid=True)),
        sa.column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.column("revision_number", sa.Integer()),
        sa.column("version_label", sa.String()),
        sa.column("is_published", sa.Boolean()),
        sa.column("is_ephemeral", sa.Boolean()),
        sa.column("display_name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("category", sa.String()),
        sa.column("input_type", sa.String()),
        sa.column("output_type", sa.String()),
        sa.column("scope", sa.String()),
        sa.column("source_code", sa.Text()),
        sa.column("manifest_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("config_schema", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("inputs", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("outputs", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("reads", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("writes", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("dependency_hash", sa.String(64)),
        sa.column("bundle_hash", sa.String(64)),
        sa.column("created_by", postgresql.UUID(as_uuid=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    existing_artifact_ids = {
        row[0]
        for row in bind.execute(sa.text("SELECT legacy_custom_operator_id FROM artifacts WHERE legacy_custom_operator_id IS NOT NULL")).fetchall()
    }
    for row in rows:
        legacy_id = row["id"]
        if legacy_id in existing_artifact_ids:
            continue

        artifact_id = uuid.uuid4()
        revision_id = uuid.uuid4()
        scope = (row.get("scope") or "rag").strip().lower()
        if scope not in {"rag", "agent", "both", "tool"}:
            scope = "rag"
        category = str(row.get("category") or "custom")
        config_schema = row.get("config_schema")
        if config_schema is None:
            config_schema = []
        if isinstance(config_schema, str):
            try:
                config_schema = json.loads(config_schema)
            except Exception:
                config_schema = []
        manifest = {
            "id": str(artifact_id),
            "legacy_custom_operator_id": str(legacy_id),
            "scope": scope,
            "category": category,
            "input_type": row.get("input_type") or "raw_documents",
            "output_type": row.get("output_type") or "raw_documents",
        }
        bind.execute(
            artifact_table.insert().values(
                id=artifact_id,
                tenant_id=row["tenant_id"],
                slug=row["name"],
                display_name=row["display_name"],
                description=row.get("description"),
                category=category,
                input_type=row.get("input_type") or "raw_documents",
                output_type=row.get("output_type") or "raw_documents",
                scope=scope,
                status="draft",
                latest_draft_revision_id=revision_id,
                created_by=row.get("created_by"),
                legacy_custom_operator_id=legacy_id,
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at") or row.get("created_at"),
            )
        )
        bind.execute(
            revision_table.insert().values(
                id=revision_id,
                artifact_id=artifact_id,
                tenant_id=row["tenant_id"],
                revision_number=1,
                version_label="draft",
                is_published=False,
                is_ephemeral=False,
                display_name=row["display_name"],
                description=row.get("description"),
                category=category,
                input_type=row.get("input_type") or "raw_documents",
                output_type=row.get("output_type") or "raw_documents",
                scope=scope,
                source_code=row.get("python_code") or "",
                manifest_json=manifest,
                config_schema=config_schema if isinstance(config_schema, list) else [],
                inputs=[],
                outputs=[],
                reads=[],
                writes=[],
                dependency_hash="",
                bundle_hash="",
                created_by=row.get("created_by"),
                created_at=row.get("created_at"),
            )
        )


def downgrade() -> None:
    op.drop_constraint("fk_artifacts_latest_published_revision_id", "artifacts", type_="foreignkey")
    op.drop_constraint("fk_artifacts_latest_draft_revision_id", "artifacts", type_="foreignkey")

    if _has_table("artifact_run_events"):
        op.drop_index("uq_artifact_run_events_run_sequence", table_name="artifact_run_events")
        op.drop_index("ix_artifact_run_events_run_id", table_name="artifact_run_events")
        op.drop_table("artifact_run_events")
    if _has_table("artifact_runs"):
        op.drop_index("ix_artifact_runs_status", table_name="artifact_runs")
        op.drop_index("ix_artifact_runs_revision_id", table_name="artifact_runs")
        op.drop_index("ix_artifact_runs_artifact_id", table_name="artifact_runs")
        op.drop_index("ix_artifact_runs_tenant_id", table_name="artifact_runs")
        op.drop_table("artifact_runs")
    if _has_table("artifact_revisions"):
        op.drop_index("ix_artifact_revisions_bundle_hash", table_name="artifact_revisions")
        op.drop_index("ix_artifact_revisions_tenant_id", table_name="artifact_revisions")
        op.drop_index("ix_artifact_revisions_artifact_id", table_name="artifact_revisions")
        op.drop_table("artifact_revisions")
    if _has_table("artifacts"):
        op.drop_index("uq_artifacts_tenant_slug", table_name="artifacts")
        op.drop_index("ix_artifacts_tenant_id", table_name="artifacts")
        op.drop_table("artifacts")

    bind = op.get_bind()
    if _has_type("artifactrunstatus"):
        artifact_run_status_enum.drop(bind, checkfirst=True)
    if _has_type("artifactrundomain"):
        artifact_run_domain_enum.drop(bind, checkfirst=True)
    if _has_type("artifactstatus"):
        artifact_status_enum.drop(bind, checkfirst=True)
    if _has_type("artifactscope"):
        artifact_scope_enum.drop(bind, checkfirst=True)
