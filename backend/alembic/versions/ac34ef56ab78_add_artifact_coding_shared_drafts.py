"""add artifact coding shared drafts

Revision ID: ac34ef56ab78
Revises: ab12cd34ef56
Create Date: 2026-03-11 20:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "ac34ef56ab78"
down_revision: Union[str, Sequence[str], None] = "ab12cd34ef56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "artifact_coding_shared_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("draft_key", sa.String(length=128), nullable=True),
        sa.Column("linked_artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("working_draft_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_test_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["last_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["last_test_run_id"], ["artifact_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_artifact_id"], ["artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_artifact_coding_shared_drafts_tenant_id"), "artifact_coding_shared_drafts", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_artifact_coding_shared_drafts_artifact_id"), "artifact_coding_shared_drafts", ["artifact_id"], unique=False)
    op.create_index(op.f("ix_artifact_coding_shared_drafts_draft_key"), "artifact_coding_shared_drafts", ["draft_key"], unique=False)
    op.create_index(op.f("ix_artifact_coding_shared_drafts_linked_artifact_id"), "artifact_coding_shared_drafts", ["linked_artifact_id"], unique=False)
    op.create_index(op.f("ix_artifact_coding_shared_drafts_last_test_run_id"), "artifact_coding_shared_drafts", ["last_test_run_id"], unique=False)
    op.create_index(op.f("ix_artifact_coding_shared_drafts_last_run_id"), "artifact_coding_shared_drafts", ["last_run_id"], unique=False)
    op.create_index(
        "uq_artifact_coding_shared_drafts_tenant_artifact",
        "artifact_coding_shared_drafts",
        ["tenant_id", "artifact_id"],
        unique=True,
        postgresql_where=sa.text("artifact_id IS NOT NULL"),
    )
    op.create_index(
        "uq_artifact_coding_shared_drafts_tenant_draft_key",
        "artifact_coding_shared_drafts",
        ["tenant_id", "draft_key"],
        unique=True,
        postgresql_where=sa.text("draft_key IS NOT NULL"),
    )

    op.create_table(
        "artifact_coding_run_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shared_draft_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("draft_key", sa.String(length=128), nullable=True),
        sa.Column("snapshot_kind", sa.String(length=32), nullable=False, server_default="pre_run"),
        sa.Column("draft_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["artifact_coding_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["shared_draft_id"], ["artifact_coding_shared_drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_artifact_coding_run_snapshots_tenant_id"), "artifact_coding_run_snapshots", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_artifact_coding_run_snapshots_shared_draft_id"), "artifact_coding_run_snapshots", ["shared_draft_id"], unique=False)
    op.create_index(op.f("ix_artifact_coding_run_snapshots_run_id"), "artifact_coding_run_snapshots", ["run_id"], unique=False)
    op.create_index(op.f("ix_artifact_coding_run_snapshots_session_id"), "artifact_coding_run_snapshots", ["session_id"], unique=False)
    op.create_index(op.f("ix_artifact_coding_run_snapshots_artifact_id"), "artifact_coding_run_snapshots", ["artifact_id"], unique=False)
    op.create_index(op.f("ix_artifact_coding_run_snapshots_draft_key"), "artifact_coding_run_snapshots", ["draft_key"], unique=False)
    op.create_index(
        "uq_artifact_coding_run_snapshots_run_kind",
        "artifact_coding_run_snapshots",
        ["run_id", "snapshot_kind"],
        unique=True,
    )

    with op.batch_alter_table("artifact_coding_sessions") as batch_op:
        batch_op.drop_index("ix_artifact_coding_sessions_last_test_run_id")
        batch_op.drop_column("last_test_run_id")
        batch_op.drop_column("working_draft_snapshot")


def downgrade() -> None:
    with op.batch_alter_table("artifact_coding_sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "working_draft_snapshot",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            )
        )
        batch_op.add_column(
            sa.Column("last_test_run_id", postgresql.UUID(as_uuid=True), nullable=True)
        )
        batch_op.create_index("ix_artifact_coding_sessions_last_test_run_id", ["last_test_run_id"], unique=False)

    op.drop_index("uq_artifact_coding_run_snapshots_run_kind", table_name="artifact_coding_run_snapshots")
    op.drop_index(op.f("ix_artifact_coding_run_snapshots_draft_key"), table_name="artifact_coding_run_snapshots")
    op.drop_index(op.f("ix_artifact_coding_run_snapshots_artifact_id"), table_name="artifact_coding_run_snapshots")
    op.drop_index(op.f("ix_artifact_coding_run_snapshots_session_id"), table_name="artifact_coding_run_snapshots")
    op.drop_index(op.f("ix_artifact_coding_run_snapshots_run_id"), table_name="artifact_coding_run_snapshots")
    op.drop_index(op.f("ix_artifact_coding_run_snapshots_shared_draft_id"), table_name="artifact_coding_run_snapshots")
    op.drop_index(op.f("ix_artifact_coding_run_snapshots_tenant_id"), table_name="artifact_coding_run_snapshots")
    op.drop_table("artifact_coding_run_snapshots")

    op.drop_index("uq_artifact_coding_shared_drafts_tenant_draft_key", table_name="artifact_coding_shared_drafts")
    op.drop_index("uq_artifact_coding_shared_drafts_tenant_artifact", table_name="artifact_coding_shared_drafts")
    op.drop_index(op.f("ix_artifact_coding_shared_drafts_last_run_id"), table_name="artifact_coding_shared_drafts")
    op.drop_index(op.f("ix_artifact_coding_shared_drafts_last_test_run_id"), table_name="artifact_coding_shared_drafts")
    op.drop_index(op.f("ix_artifact_coding_shared_drafts_linked_artifact_id"), table_name="artifact_coding_shared_drafts")
    op.drop_index(op.f("ix_artifact_coding_shared_drafts_draft_key"), table_name="artifact_coding_shared_drafts")
    op.drop_index(op.f("ix_artifact_coding_shared_drafts_artifact_id"), table_name="artifact_coding_shared_drafts")
    op.drop_index(op.f("ix_artifact_coding_shared_drafts_tenant_id"), table_name="artifact_coding_shared_drafts")
    op.drop_table("artifact_coding_shared_drafts")
