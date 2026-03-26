"""add resource policy sets

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-26
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


resource_policy_principal_type = postgresql.ENUM(
    "tenant_user",
    "published_app_account",
    "embedded_external_user",
    name="resourcepolicyprincipaltype",
    create_type=False,
)
resource_policy_resource_type = postgresql.ENUM(
    "agent",
    "tool",
    "knowledge_store",
    "model",
    name="resourcepolicyresourcetype",
    create_type=False,
)
resource_policy_rule_type = postgresql.ENUM(
    "allow",
    "quota",
    name="resourcepolicyruletype",
    create_type=False,
)
resource_policy_quota_unit = postgresql.ENUM(
    "tokens",
    name="resourcepolicyquotaunit",
    create_type=False,
)
resource_policy_quota_window = postgresql.ENUM(
    "monthly",
    name="resourcepolicyquotawindow",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE resourcepolicyprincipaltype AS ENUM ('tenant_user', 'published_app_account', 'embedded_external_user');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE resourcepolicyresourcetype AS ENUM ('agent', 'tool', 'knowledge_store', 'model');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE resourcepolicyruletype AS ENUM ('allow', 'quota');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE resourcepolicyquotaunit AS ENUM ('tokens');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE resourcepolicyquotawindow AS ENUM ('monthly');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END
        $$;
        """
    )

    op.create_table(
        "resource_policy_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_resource_policy_sets_tenant_name"),
    )
    op.create_index(op.f("ix_resource_policy_sets_tenant_id"), "resource_policy_sets", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_resource_policy_sets_created_by"), "resource_policy_sets", ["created_by"], unique=False)

    op.create_table(
        "resource_policy_set_includes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_policy_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("included_policy_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["included_policy_set_id"], ["resource_policy_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_policy_set_id"], ["resource_policy_sets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "parent_policy_set_id",
            "included_policy_set_id",
            name="uq_resource_policy_set_include_edge",
        ),
    )
    op.create_index(
        op.f("ix_resource_policy_set_includes_parent_policy_set_id"),
        "resource_policy_set_includes",
        ["parent_policy_set_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_resource_policy_set_includes_included_policy_set_id"),
        "resource_policy_set_includes",
        ["included_policy_set_id"],
        unique=False,
    )

    op.create_table(
        "resource_policy_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", resource_policy_resource_type, nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("rule_type", resource_policy_rule_type, nullable=False),
        sa.Column("quota_unit", resource_policy_quota_unit, nullable=True),
        sa.Column("quota_window", resource_policy_quota_window, nullable=True),
        sa.Column("quota_limit", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["policy_set_id"], ["resource_policy_sets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_resource_policy_rules_policy_set_id"), "resource_policy_rules", ["policy_set_id"], unique=False)
    op.create_index(op.f("ix_resource_policy_rules_resource_type"), "resource_policy_rules", ["resource_type"], unique=False)
    op.create_index(op.f("ix_resource_policy_rules_resource_id"), "resource_policy_rules", ["resource_id"], unique=False)
    op.create_index(op.f("ix_resource_policy_rules_rule_type"), "resource_policy_rules", ["rule_type"], unique=False)
    op.create_index(
        "uq_resource_policy_rules_allow_resource",
        "resource_policy_rules",
        ["policy_set_id", "resource_type", "resource_id"],
        unique=True,
        postgresql_where=sa.text("rule_type = 'allow'"),
    )
    op.create_index(
        "uq_resource_policy_rules_quota_resource",
        "resource_policy_rules",
        ["policy_set_id", "resource_type", "resource_id", "quota_unit", "quota_window"],
        unique=True,
        postgresql_where=sa.text("rule_type = 'quota'"),
    )

    op.create_table(
        "resource_policy_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_type", resource_policy_principal_type, nullable=False),
        sa.Column("policy_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_app_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("embedded_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_user_id", sa.String(length=255), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["embedded_agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_set_id"], ["resource_policy_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_app_account_id"], ["published_app_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_resource_policy_assignments_tenant_id"), "resource_policy_assignments", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_resource_policy_assignments_principal_type"), "resource_policy_assignments", ["principal_type"], unique=False)
    op.create_index(op.f("ix_resource_policy_assignments_policy_set_id"), "resource_policy_assignments", ["policy_set_id"], unique=False)
    op.create_index(op.f("ix_resource_policy_assignments_user_id"), "resource_policy_assignments", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_resource_policy_assignments_published_app_account_id"),
        "resource_policy_assignments",
        ["published_app_account_id"],
        unique=False,
    )
    op.create_index(op.f("ix_resource_policy_assignments_embedded_agent_id"), "resource_policy_assignments", ["embedded_agent_id"], unique=False)
    op.create_index(op.f("ix_resource_policy_assignments_external_user_id"), "resource_policy_assignments", ["external_user_id"], unique=False)
    op.create_index(op.f("ix_resource_policy_assignments_created_by"), "resource_policy_assignments", ["created_by"], unique=False)
    op.create_index(
        "uq_resource_policy_assignments_tenant_user",
        "resource_policy_assignments",
        ["tenant_id", "principal_type", "user_id"],
        unique=True,
        postgresql_where=sa.text("principal_type = 'tenant_user' AND user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_resource_policy_assignments_app_account",
        "resource_policy_assignments",
        ["tenant_id", "principal_type", "published_app_account_id"],
        unique=True,
        postgresql_where=sa.text("principal_type = 'published_app_account' AND published_app_account_id IS NOT NULL"),
    )
    op.create_index(
        "uq_resource_policy_assignments_embedded_user",
        "resource_policy_assignments",
        ["tenant_id", "principal_type", "embedded_agent_id", "external_user_id"],
        unique=True,
        postgresql_where=sa.text(
            "principal_type = 'embedded_external_user' AND embedded_agent_id IS NOT NULL AND external_user_id IS NOT NULL"
        ),
    )

    op.create_table(
        "resource_policy_quota_counters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_type", resource_policy_principal_type, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_app_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("embedded_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_user_id", sa.String(length=255), nullable=True),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quota_window", resource_policy_quota_window, nullable=False, server_default=sa.text("'monthly'")),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("reserved_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["embedded_agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_id"], ["model_registry.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_app_account_id"], ["published_app_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "principal_type",
            "user_id",
            "published_app_account_id",
            "embedded_agent_id",
            "external_user_id",
            "model_id",
            "quota_window",
            "period_start",
            name="uq_resource_policy_quota_counter_scope_period",
        ),
    )
    op.create_index(op.f("ix_resource_policy_quota_counters_tenant_id"), "resource_policy_quota_counters", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_resource_policy_quota_counters_principal_type"), "resource_policy_quota_counters", ["principal_type"], unique=False)
    op.create_index(op.f("ix_resource_policy_quota_counters_user_id"), "resource_policy_quota_counters", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_resource_policy_quota_counters_published_app_account_id"),
        "resource_policy_quota_counters",
        ["published_app_account_id"],
        unique=False,
    )
    op.create_index(op.f("ix_resource_policy_quota_counters_embedded_agent_id"), "resource_policy_quota_counters", ["embedded_agent_id"], unique=False)
    op.create_index(op.f("ix_resource_policy_quota_counters_external_user_id"), "resource_policy_quota_counters", ["external_user_id"], unique=False)
    op.create_index(op.f("ix_resource_policy_quota_counters_model_id"), "resource_policy_quota_counters", ["model_id"], unique=False)
    op.create_index(op.f("ix_resource_policy_quota_counters_period_start"), "resource_policy_quota_counters", ["period_start"], unique=False)

    op.create_table(
        "resource_policy_quota_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_type", resource_policy_principal_type, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_app_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("embedded_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_user_id", sa.String(length=255), nullable=True),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quota_window", resource_policy_quota_window, nullable=False, server_default=sa.text("'monthly'")),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["embedded_agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_id"], ["model_registry.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["published_app_account_id"], ["published_app_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_resource_policy_quota_reservations_run_id"), "resource_policy_quota_reservations", ["run_id"], unique=True)
    op.create_index(op.f("ix_resource_policy_quota_reservations_tenant_id"), "resource_policy_quota_reservations", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_resource_policy_quota_reservations_principal_type"), "resource_policy_quota_reservations", ["principal_type"], unique=False)
    op.create_index(op.f("ix_resource_policy_quota_reservations_user_id"), "resource_policy_quota_reservations", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_resource_policy_quota_reservations_published_app_account_id"),
        "resource_policy_quota_reservations",
        ["published_app_account_id"],
        unique=False,
    )
    op.create_index(op.f("ix_resource_policy_quota_reservations_embedded_agent_id"), "resource_policy_quota_reservations", ["embedded_agent_id"], unique=False)
    op.create_index(op.f("ix_resource_policy_quota_reservations_external_user_id"), "resource_policy_quota_reservations", ["external_user_id"], unique=False)
    op.create_index(op.f("ix_resource_policy_quota_reservations_model_id"), "resource_policy_quota_reservations", ["model_id"], unique=False)
    op.create_index(op.f("ix_resource_policy_quota_reservations_period_start"), "resource_policy_quota_reservations", ["period_start"], unique=False)

    op.add_column("published_apps", sa.Column("default_policy_set_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_published_apps_default_policy_set_id"), "published_apps", ["default_policy_set_id"], unique=False)
    op.create_foreign_key(
        "fk_published_apps_default_policy_set_id",
        "published_apps",
        "resource_policy_sets",
        ["default_policy_set_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("agents", sa.Column("default_embed_policy_set_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_agents_default_embed_policy_set_id"), "agents", ["default_embed_policy_set_id"], unique=False)
    op.create_foreign_key(
        "fk_agents_default_embed_policy_set_id",
        "agents",
        "resource_policy_sets",
        ["default_embed_policy_set_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("agent_runs", sa.Column("external_user_id", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_agent_runs_external_user_id"), "agent_runs", ["external_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_runs_external_user_id"), table_name="agent_runs")
    op.drop_column("agent_runs", "external_user_id")

    op.drop_constraint("fk_agents_default_embed_policy_set_id", "agents", type_="foreignkey")
    op.drop_index(op.f("ix_agents_default_embed_policy_set_id"), table_name="agents")
    op.drop_column("agents", "default_embed_policy_set_id")

    op.drop_constraint("fk_published_apps_default_policy_set_id", "published_apps", type_="foreignkey")
    op.drop_index(op.f("ix_published_apps_default_policy_set_id"), table_name="published_apps")
    op.drop_column("published_apps", "default_policy_set_id")

    op.drop_index(op.f("ix_resource_policy_quota_reservations_period_start"), table_name="resource_policy_quota_reservations")
    op.drop_index(op.f("ix_resource_policy_quota_reservations_model_id"), table_name="resource_policy_quota_reservations")
    op.drop_index(op.f("ix_resource_policy_quota_reservations_external_user_id"), table_name="resource_policy_quota_reservations")
    op.drop_index(op.f("ix_resource_policy_quota_reservations_embedded_agent_id"), table_name="resource_policy_quota_reservations")
    op.drop_index(op.f("ix_resource_policy_quota_reservations_published_app_account_id"), table_name="resource_policy_quota_reservations")
    op.drop_index(op.f("ix_resource_policy_quota_reservations_user_id"), table_name="resource_policy_quota_reservations")
    op.drop_index(op.f("ix_resource_policy_quota_reservations_principal_type"), table_name="resource_policy_quota_reservations")
    op.drop_index(op.f("ix_resource_policy_quota_reservations_tenant_id"), table_name="resource_policy_quota_reservations")
    op.drop_index(op.f("ix_resource_policy_quota_reservations_run_id"), table_name="resource_policy_quota_reservations")
    op.drop_table("resource_policy_quota_reservations")

    op.drop_index(op.f("ix_resource_policy_quota_counters_period_start"), table_name="resource_policy_quota_counters")
    op.drop_index(op.f("ix_resource_policy_quota_counters_model_id"), table_name="resource_policy_quota_counters")
    op.drop_index(op.f("ix_resource_policy_quota_counters_external_user_id"), table_name="resource_policy_quota_counters")
    op.drop_index(op.f("ix_resource_policy_quota_counters_embedded_agent_id"), table_name="resource_policy_quota_counters")
    op.drop_index(op.f("ix_resource_policy_quota_counters_published_app_account_id"), table_name="resource_policy_quota_counters")
    op.drop_index(op.f("ix_resource_policy_quota_counters_user_id"), table_name="resource_policy_quota_counters")
    op.drop_index(op.f("ix_resource_policy_quota_counters_principal_type"), table_name="resource_policy_quota_counters")
    op.drop_index(op.f("ix_resource_policy_quota_counters_tenant_id"), table_name="resource_policy_quota_counters")
    op.drop_table("resource_policy_quota_counters")

    op.drop_index("uq_resource_policy_assignments_embedded_user", table_name="resource_policy_assignments")
    op.drop_index("uq_resource_policy_assignments_app_account", table_name="resource_policy_assignments")
    op.drop_index("uq_resource_policy_assignments_tenant_user", table_name="resource_policy_assignments")
    op.drop_index(op.f("ix_resource_policy_assignments_created_by"), table_name="resource_policy_assignments")
    op.drop_index(op.f("ix_resource_policy_assignments_external_user_id"), table_name="resource_policy_assignments")
    op.drop_index(op.f("ix_resource_policy_assignments_embedded_agent_id"), table_name="resource_policy_assignments")
    op.drop_index(op.f("ix_resource_policy_assignments_published_app_account_id"), table_name="resource_policy_assignments")
    op.drop_index(op.f("ix_resource_policy_assignments_user_id"), table_name="resource_policy_assignments")
    op.drop_index(op.f("ix_resource_policy_assignments_policy_set_id"), table_name="resource_policy_assignments")
    op.drop_index(op.f("ix_resource_policy_assignments_principal_type"), table_name="resource_policy_assignments")
    op.drop_index(op.f("ix_resource_policy_assignments_tenant_id"), table_name="resource_policy_assignments")
    op.drop_table("resource_policy_assignments")

    op.drop_index("uq_resource_policy_rules_quota_resource", table_name="resource_policy_rules")
    op.drop_index("uq_resource_policy_rules_allow_resource", table_name="resource_policy_rules")
    op.drop_index(op.f("ix_resource_policy_rules_rule_type"), table_name="resource_policy_rules")
    op.drop_index(op.f("ix_resource_policy_rules_resource_id"), table_name="resource_policy_rules")
    op.drop_index(op.f("ix_resource_policy_rules_resource_type"), table_name="resource_policy_rules")
    op.drop_index(op.f("ix_resource_policy_rules_policy_set_id"), table_name="resource_policy_rules")
    op.drop_table("resource_policy_rules")

    op.drop_index(op.f("ix_resource_policy_set_includes_included_policy_set_id"), table_name="resource_policy_set_includes")
    op.drop_index(op.f("ix_resource_policy_set_includes_parent_policy_set_id"), table_name="resource_policy_set_includes")
    op.drop_table("resource_policy_set_includes")

    op.drop_index(op.f("ix_resource_policy_sets_created_by"), table_name="resource_policy_sets")
    op.drop_index(op.f("ix_resource_policy_sets_tenant_id"), table_name="resource_policy_sets")
    op.drop_table("resource_policy_sets")

    op.execute("DROP TYPE IF EXISTS resourcepolicyquotawindow")
    op.execute("DROP TYPE IF EXISTS resourcepolicyquotaunit")
    op.execute("DROP TYPE IF EXISTS resourcepolicyruletype")
    op.execute("DROP TYPE IF EXISTS resourcepolicyresourcetype")
    op.execute("DROP TYPE IF EXISTS resourcepolicyprincipaltype")
