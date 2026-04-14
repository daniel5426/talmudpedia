"""add run invocations and context window json

Revision ID: ff1e2d3c4b5a
Revises: fe2a3b4c5d6e
Create Date: 2026-03-29 23:59:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "ff1e2d3c4b5a"
down_revision: Union[str, Sequence[str], None] = "fe2a3b4c5d6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        return set(inspector.get_table_names())
    except Exception:
        return set()


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        return {col["name"] for col in inspector.get_columns(table_name)}
    except Exception:
        return set()


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        return {idx["name"] for idx in inspector.get_indexes(table_name)}
    except Exception:
        return set()


def upgrade() -> None:
    tables = _table_names()

    if "agent_runs" in tables:
        run_columns = _column_names("agent_runs")
        if "context_window_json" not in run_columns:
            op.add_column(
                "agent_runs",
                sa.Column("context_window_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            )

        if "usage_source" in run_columns:
            bind = op.get_bind()
            bind.execute(
                sa.text(
                    """
                    UPDATE agent_runs
                    SET usage_source = CASE
                        WHEN usage_source IN ('provider_reported', 'sdk_reported') THEN 'exact'
                        WHEN usage_source IN ('estimated', 'legacy_estimated') THEN 'estimated'
                        WHEN usage_source IN ('unknown', 'legacy_unknown') THEN 'unknown'
                        WHEN usage_source IS NULL AND COALESCE(total_tokens, usage_tokens, 0) > 0 THEN 'estimated'
                        ELSE 'unknown'
                    END
                    """
                )
            )

    if "agent_run_invocations" not in tables:
        op.create_table(
            "agent_run_invocations",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("node_id", sa.String(), nullable=True),
            sa.Column("node_name", sa.String(), nullable=True),
            sa.Column("node_type", sa.String(), nullable=True),
            sa.Column("model_id", sa.String(), nullable=True),
            sa.Column("resolved_provider", sa.String(), nullable=True),
            sa.Column("resolved_provider_model_id", sa.String(), nullable=True),
            sa.Column("usage_source", sa.String(), nullable=False, server_default="unknown"),
            sa.Column("context_source", sa.String(), nullable=False, server_default="unknown"),
            sa.Column("input_tokens", sa.Integer(), nullable=True),
            sa.Column("output_tokens", sa.Integer(), nullable=True),
            sa.Column("total_tokens", sa.Integer(), nullable=True),
            sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
            sa.Column("cached_output_tokens", sa.Integer(), nullable=True),
            sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
            sa.Column("context_input_tokens", sa.Integer(), nullable=True),
            sa.Column("max_context_tokens", sa.Integer(), nullable=True),
            sa.Column("max_context_tokens_source", sa.String(), nullable=True),
            sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_id", "sequence", name="uq_agent_run_invocations_run_sequence"),
        )
        op.create_index("ix_agent_run_invocations_run_id", "agent_run_invocations", ["run_id"], unique=False)
        op.create_index("ix_agent_run_invocations_usage_source", "agent_run_invocations", ["usage_source"], unique=False)
        op.create_index(
            "ix_agent_run_invocations_run_sequence",
            "agent_run_invocations",
            ["run_id", "sequence"],
            unique=False,
        )


def downgrade() -> None:
    tables = _table_names()
    if "agent_run_invocations" in tables:
        index_names = _index_names("agent_run_invocations")
        if "ix_agent_run_invocations_run_sequence" in index_names:
            op.drop_index("ix_agent_run_invocations_run_sequence", table_name="agent_run_invocations")
        if "ix_agent_run_invocations_usage_source" in index_names:
            op.drop_index("ix_agent_run_invocations_usage_source", table_name="agent_run_invocations")
        if "ix_agent_run_invocations_run_id" in index_names:
            op.drop_index("ix_agent_run_invocations_run_id", table_name="agent_run_invocations")
        op.drop_table("agent_run_invocations")

    if "agent_runs" in tables:
        run_columns = _column_names("agent_runs")
        if "context_window_json" in run_columns:
            op.drop_column("agent_runs", "context_window_json")
