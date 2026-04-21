"""hard cut system identity row keys

Revision ID: ac91de42bf67
Revises: d9e8f7a6b5c4
Create Date: 2026-04-21
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "ac91de42bf67"
down_revision: Union[str, Sequence[str], None] = "d9e8f7a6b5c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def _unique_exists(inspector: sa.Inspector, table_name: str, constraint_name: str) -> bool:
    return any(item.get("name") == constraint_name for item in inspector.get_unique_constraints(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    bind.execute(
        sa.text(
            """
            UPDATE agents
            SET slug = CASE system_key
                WHEN 'platform_architect' THEN 'sys-agent-766b178e44c6f732c6ce4ec1'
                WHEN 'artifact_coding_agent' THEN 'sys-agent-393ec9edf532ec20e4ca0e50'
                WHEN 'published_app_coding_agent' THEN 'sys-agent-44ae4f75a92edb50f62e3cfd'
                ELSE slug
            END
            WHERE system_key IN ('platform_architect', 'artifact_coding_agent', 'published_app_coding_agent')
            """
        )
    )

    bind.execute(
        sa.text(
            """
            UPDATE tool_registry
            SET builtin_key = CASE slug
                WHEN 'platform-sdk' THEN 'platform_sdk'
                WHEN 'platform-rag' THEN 'platform-rag'
                WHEN 'platform-agents' THEN 'platform-agents'
                WHEN 'platform-assets' THEN 'platform-assets'
                WHEN 'platform-governance' THEN 'platform-governance'
                ELSE builtin_key
            END,
            slug = CASE
                WHEN coalesce(builtin_key, CASE slug
                    WHEN 'platform-sdk' THEN 'platform_sdk'
                    WHEN 'platform-rag' THEN 'platform-rag'
                    WHEN 'platform-agents' THEN 'platform-agents'
                    WHEN 'platform-assets' THEN 'platform-assets'
                    WHEN 'platform-governance' THEN 'platform-governance'
                    ELSE NULL
                END) = 'platform_sdk' THEN 'sys-tool-71abcf617f22ab831775956a'
                WHEN coalesce(builtin_key, CASE slug
                    WHEN 'platform-sdk' THEN 'platform_sdk'
                    WHEN 'platform-rag' THEN 'platform-rag'
                    WHEN 'platform-agents' THEN 'platform-agents'
                    WHEN 'platform-assets' THEN 'platform-assets'
                    WHEN 'platform-governance' THEN 'platform-governance'
                    ELSE NULL
                END) = 'platform-rag' THEN 'sys-tool-188f463f8ac65bd25aa3d41b'
                WHEN coalesce(builtin_key, CASE slug
                    WHEN 'platform-sdk' THEN 'platform_sdk'
                    WHEN 'platform-rag' THEN 'platform-rag'
                    WHEN 'platform-agents' THEN 'platform-agents'
                    WHEN 'platform-assets' THEN 'platform-assets'
                    WHEN 'platform-governance' THEN 'platform-governance'
                    ELSE NULL
                END) = 'platform-agents' THEN 'sys-tool-a59e131f46692e8426cd6941'
                WHEN coalesce(builtin_key, CASE slug
                    WHEN 'platform-sdk' THEN 'platform_sdk'
                    WHEN 'platform-rag' THEN 'platform-rag'
                    WHEN 'platform-agents' THEN 'platform-agents'
                    WHEN 'platform-assets' THEN 'platform-assets'
                    WHEN 'platform-governance' THEN 'platform-governance'
                    ELSE NULL
                END) = 'platform-assets' THEN 'sys-tool-a0e136339f6f6b9e3f884860'
                WHEN coalesce(builtin_key, CASE slug
                    WHEN 'platform-sdk' THEN 'platform_sdk'
                    WHEN 'platform-rag' THEN 'platform-rag'
                    WHEN 'platform-agents' THEN 'platform-agents'
                    WHEN 'platform-assets' THEN 'platform-assets'
                    WHEN 'platform-governance' THEN 'platform-governance'
                    ELSE NULL
                END) = 'platform-governance' THEN 'sys-tool-0d7e2ceae5530f4104a21ccb'
                ELSE slug
            END
            WHERE tenant_id IS NULL
              AND (slug IN ('platform-sdk', 'platform-rag', 'platform-agents', 'platform-assets', 'platform-governance')
                   OR builtin_key IN ('platform_sdk', 'platform-rag', 'platform-agents', 'platform-assets', 'platform-governance'))
            """
        )
    )

    bind.execute(
        sa.text(
            """
            UPDATE org_units
            SET system_key = 'root'
            WHERE system_key IS NULL
              AND type = 'org'
            """
        )
    )

    if _unique_exists(inspector, "agents", "uq_agent_tenant_slug"):
        op.drop_constraint("uq_agent_tenant_slug", "agents", type_="unique")

    if _index_exists(inspector, "org_units", "uq_org_units_tenant_system_key"):
        op.drop_index("uq_org_units_tenant_system_key", table_name="org_units")
    op.create_index(
        "uq_org_units_tenant_system_key",
        "org_units",
        ["tenant_id", "system_key"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL AND system_key IS NOT NULL"),
    )

    if _index_exists(inspector, "tool_registry", "uq_tool_registry_global_builtin_key"):
        op.drop_index("uq_tool_registry_global_builtin_key", table_name="tool_registry")
    op.create_index(
        "uq_tool_registry_global_builtin_key",
        "tool_registry",
        ["builtin_key"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL AND builtin_key IS NOT NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _index_exists(inspector, "tool_registry", "uq_tool_registry_global_builtin_key"):
        op.drop_index("uq_tool_registry_global_builtin_key", table_name="tool_registry")
    op.create_index(
        "uq_tool_registry_global_builtin_key",
        "tool_registry",
        ["builtin_key"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL AND is_builtin_template = true AND builtin_key IS NOT NULL"),
    )

    if _index_exists(inspector, "org_units", "uq_org_units_tenant_system_key"):
        op.drop_index("uq_org_units_tenant_system_key", table_name="org_units")

    if not _unique_exists(inspector, "agents", "uq_agent_tenant_slug"):
        op.create_unique_constraint("uq_agent_tenant_slug", "agents", ["tenant_id", "slug"])
