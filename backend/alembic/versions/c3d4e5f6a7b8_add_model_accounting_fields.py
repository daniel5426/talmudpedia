"""add model accounting fields

Revision ID: c3d4e5f6a7b8
Revises: 1f2e3d4c5b6a, b2c3d4e5f6a7
Create Date: 2026-03-26
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = ("1f2e3d4c5b6a", "b2c3d4e5f6a7")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "model_provider_bindings",
        sa.Column(
            "pricing_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.add_column("agent_runs", sa.Column("resolved_binding_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("agent_runs", sa.Column("resolved_provider", sa.String(), nullable=True))
    op.add_column("agent_runs", sa.Column("resolved_provider_model_id", sa.String(), nullable=True))
    op.add_column("agent_runs", sa.Column("usage_source", sa.String(), nullable=True))
    op.add_column("agent_runs", sa.Column("cost_source", sa.String(), nullable=True))
    op.add_column("agent_runs", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("agent_runs", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("agent_runs", sa.Column("total_tokens", sa.Integer(), nullable=True))
    op.add_column("agent_runs", sa.Column("cached_input_tokens", sa.Integer(), nullable=True))
    op.add_column("agent_runs", sa.Column("cached_output_tokens", sa.Integer(), nullable=True))
    op.add_column("agent_runs", sa.Column("reasoning_tokens", sa.Integer(), nullable=True))
    op.add_column("agent_runs", sa.Column("usage_breakdown_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("agent_runs", sa.Column("cost_usd", sa.Float(), nullable=True))
    op.add_column("agent_runs", sa.Column("cost_breakdown_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("agent_runs", sa.Column("pricing_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_index(op.f("ix_agent_runs_resolved_binding_id"), "agent_runs", ["resolved_binding_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_resolved_provider"), "agent_runs", ["resolved_provider"], unique=False)
    op.create_index(op.f("ix_agent_runs_usage_source"), "agent_runs", ["usage_source"], unique=False)
    op.create_index(op.f("ix_agent_runs_cost_source"), "agent_runs", ["cost_source"], unique=False)
    op.create_foreign_key(
        "fk_agent_runs_resolved_binding_id",
        "agent_runs",
        "model_provider_bindings",
        ["resolved_binding_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        sa.text(
            """
            UPDATE agent_runs
            SET
                total_tokens = usage_tokens,
                usage_source = CASE
                    WHEN COALESCE(usage_tokens, 0) > 0 THEN 'legacy_estimated'
                    ELSE 'legacy_unknown'
                END
            WHERE total_tokens IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint("fk_agent_runs_resolved_binding_id", "agent_runs", type_="foreignkey")
    op.drop_index(op.f("ix_agent_runs_cost_source"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_usage_source"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_resolved_provider"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_resolved_binding_id"), table_name="agent_runs")

    op.drop_column("agent_runs", "pricing_snapshot_json")
    op.drop_column("agent_runs", "cost_breakdown_json")
    op.drop_column("agent_runs", "cost_usd")
    op.drop_column("agent_runs", "usage_breakdown_json")
    op.drop_column("agent_runs", "reasoning_tokens")
    op.drop_column("agent_runs", "cached_output_tokens")
    op.drop_column("agent_runs", "cached_input_tokens")
    op.drop_column("agent_runs", "total_tokens")
    op.drop_column("agent_runs", "output_tokens")
    op.drop_column("agent_runs", "input_tokens")
    op.drop_column("agent_runs", "cost_source")
    op.drop_column("agent_runs", "usage_source")
    op.drop_column("agent_runs", "resolved_provider_model_id")
    op.drop_column("agent_runs", "resolved_provider")
    op.drop_column("agent_runs", "resolved_binding_id")

    op.drop_column("model_provider_bindings", "pricing_config")
