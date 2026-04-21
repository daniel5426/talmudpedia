"""scope agent system key uniqueness to project

Revision ID: 0f1e2d3c4b6a
Revises: a0b1c2d3e4f5
Create Date: 2026-04-21 16:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0f1e2d3c4b6a"
down_revision: str | None = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_agents_tenant_system_key", table_name="agents")
    op.create_index(
        "uq_agents_project_system_key",
        "agents",
        ["organization_id", "project_id", "system_key"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NOT NULL AND system_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_agents_project_system_key", table_name="agents")
    op.create_index(
        "uq_agents_tenant_system_key",
        "agents",
        ["organization_id", "system_key"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NOT NULL AND system_key IS NOT NULL"),
    )
