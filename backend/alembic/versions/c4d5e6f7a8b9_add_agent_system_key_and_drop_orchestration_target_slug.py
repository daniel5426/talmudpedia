"""add agent system_key and drop orchestration target slug

Revision ID: e0f1a2b3c4d5
Revises: 1a2b3c4d5e6f, 8f1a2b3c4d5e, b4c5d6e7f8a9
Create Date: 2026-04-21 21:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "e0f1a2b3c4d5"
down_revision: Union[str, Sequence[str], None] = ("1a2b3c4d5e6f", "8f1a2b3c4d5e", "b4c5d6e7f8a9")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _column_exists(inspector, "agents", "system_key"):
        op.add_column("agents", sa.Column("system_key", sa.String(), nullable=True))
    if not _index_exists(inspector, "agents", "ix_agents_system_key"):
        op.create_index(op.f("ix_agents_system_key"), "agents", ["system_key"], unique=False)
    if not _index_exists(inspector, "agents", "uq_agents_tenant_system_key"):
        op.create_index(
            "uq_agents_tenant_system_key",
            "agents",
            ["tenant_id", "system_key"],
            unique=True,
            postgresql_where=sa.text("tenant_id IS NOT NULL AND system_key IS NOT NULL"),
        )

    bind.execute(sa.text(
        """
        UPDATE agents
        SET system_key = CASE slug
            WHEN 'platform-architect' THEN 'platform_architect'
            WHEN 'artifact-coding-agent' THEN 'artifact_coding_agent'
            WHEN 'published-app-coding-agent' THEN 'published_app_coding_agent'
            ELSE system_key
        END
        WHERE system_key IS NULL
          AND slug IN ('platform-architect', 'artifact-coding-agent', 'published-app-coding-agent')
        """
    ))

    if _column_exists(inspector, "orchestrator_target_allowlists", "target_agent_slug"):
        bind.execute(sa.text(
            """
            UPDATE orchestrator_target_allowlists AS o
            SET target_agent_id = a.id
            FROM agents AS a
            WHERE o.target_agent_id IS NULL
              AND o.target_agent_slug IS NOT NULL
              AND a.tenant_id = o.tenant_id
              AND a.slug = o.target_agent_slug
            """
        ))
        unresolved = int(bind.execute(sa.text(
            """
            SELECT count(*)
            FROM orchestrator_target_allowlists
            WHERE target_agent_slug IS NOT NULL
              AND target_agent_id IS NULL
            """
        )).scalar() or 0)
        if unresolved:
            raise RuntimeError("Cannot drop target_agent_slug: unresolved allowlist rows remain")
        if _index_exists(inspector, "orchestrator_target_allowlists", "ix_orchestrator_target_allowlists_orch_slug"):
            op.drop_index("ix_orchestrator_target_allowlists_orch_slug", table_name="orchestrator_target_allowlists")
        op.drop_column("orchestrator_target_allowlists", "target_agent_slug")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _column_exists(inspector, "orchestrator_target_allowlists", "target_agent_slug"):
        op.add_column("orchestrator_target_allowlists", sa.Column("target_agent_slug", sa.String(), nullable=True))
        bind.execute(sa.text(
            """
            UPDATE orchestrator_target_allowlists AS o
            SET target_agent_slug = a.slug
            FROM agents AS a
            WHERE o.target_agent_id = a.id
              AND o.target_agent_slug IS NULL
            """
        ))
        op.create_index(
            "ix_orchestrator_target_allowlists_orch_slug",
            "orchestrator_target_allowlists",
            ["orchestrator_agent_id", "target_agent_slug"],
            unique=False,
        )

    if _index_exists(inspector, "agents", "uq_agents_tenant_system_key"):
        op.drop_index("uq_agents_tenant_system_key", table_name="agents")
    if _index_exists(inspector, "agents", "ix_agents_system_key"):
        op.drop_index(op.f("ix_agents_system_key"), table_name="agents")
    if _column_exists(inspector, "agents", "system_key"):
        op.drop_column("agents", "system_key")
