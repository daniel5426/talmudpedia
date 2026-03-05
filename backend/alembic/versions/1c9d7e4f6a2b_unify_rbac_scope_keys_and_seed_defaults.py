"""unify rbac scope keys and seed defaults

Revision ID: 1c9d7e4f6a2b
Revises: 7a1f3b4c5d6e
Create Date: 2026-03-05 17:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "1c9d7e4f6a2b"
down_revision: Union[str, Sequence[str], None] = "7a1f3b4c5d6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_ROLE_SCOPES: dict[str, list[str]] = {
    "owner": sorted(
        {
            "pipelines.catalog.read",
            "pipelines.read",
            "pipelines.write",
            "pipelines.delete",
            "agents.read",
            "agents.write",
            "agents.execute",
            "agents.run_tests",
            "agents.delete",
            "tools.read",
            "tools.write",
            "tools.delete",
            "artifacts.read",
            "artifacts.write",
            "artifacts.delete",
            "models.read",
            "models.write",
            "credentials.read",
            "credentials.write",
            "knowledge_stores.read",
            "knowledge_stores.write",
            "workload_security.read",
            "workload_security.write",
            "auth.write",
            "orchestration.spawn_run",
            "orchestration.spawn_group",
            "orchestration.join",
            "orchestration.cancel_subtree",
            "orchestration.evaluate_and_replan",
            "orchestration.query_tree",
            "apps.read",
            "apps.write",
            "roles.read",
            "roles.write",
            "roles.assign",
            "membership.read",
            "membership.write",
            "membership.delete",
            "audit.read",
            "stats.read",
            "users.read",
            "users.write",
            "threads.read",
            "threads.write",
            "tenants.read",
            "tenants.write",
        }
    ),
    "admin": sorted(
        {
            "pipelines.catalog.read",
            "pipelines.read",
            "pipelines.write",
            "pipelines.delete",
            "agents.read",
            "agents.write",
            "agents.execute",
            "agents.run_tests",
            "agents.delete",
            "tools.read",
            "tools.write",
            "tools.delete",
            "artifacts.read",
            "artifacts.write",
            "artifacts.delete",
            "models.read",
            "models.write",
            "credentials.read",
            "credentials.write",
            "knowledge_stores.read",
            "knowledge_stores.write",
            "workload_security.read",
            "workload_security.write",
            "apps.read",
            "apps.write",
            "roles.read",
            "roles.write",
            "roles.assign",
            "membership.read",
            "membership.write",
            "membership.delete",
            "audit.read",
            "stats.read",
            "users.read",
            "users.write",
            "threads.read",
            "threads.write",
            "tenants.read",
            "tenants.write",
        }
    ),
    "member": sorted(
        {
            "pipelines.catalog.read",
            "pipelines.read",
            "agents.read",
            "agents.execute",
            "artifacts.read",
            "tools.read",
            "models.read",
            "knowledge_stores.read",
            "credentials.read",
            "threads.read",
            "users.read",
            "stats.read",
            "apps.read",
        }
    ),
}


def _drop_constraint_if_exists(bind, table_name: str, constraint_name: str) -> None:
    inspector = sa.inspect(bind)
    constraints = {c.get("name") for c in inspector.get_unique_constraints(table_name)}
    if constraint_name in constraints:
        op.drop_constraint(constraint_name, table_name, type_="unique")


def _resolve_actor_type_user_label(bind) -> str:
    labels = [
        row[0]
        for row in bind.execute(
            sa.text(
                """
                SELECT e.enumlabel
                FROM pg_type t
                JOIN pg_enum e ON e.enumtypid = t.oid
                WHERE t.typname = 'actortype'
                ORDER BY e.enumsortorder
                """
            )
        ).fetchall()
    ]
    if "user" in labels:
        return "user"
    if "USER" in labels:
        return "USER"
    return "user"


def upgrade() -> None:
    bind = op.get_bind()
    actor_type_user_label = _resolve_actor_type_user_label(bind)

    op.add_column(
        "agents",
        sa.Column("workload_scope_profile", sa.String(), nullable=False, server_default="default_agent_run"),
    )
    op.add_column(
        "agents",
        sa.Column("workload_scope_overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )

    op.add_column("role_permissions", sa.Column("scope_key", sa.String(), nullable=True))

    with op.batch_alter_table("role_permissions") as batch_op:
        batch_op.alter_column("resource_type", existing_type=sa.Enum(name="resourcetype"), nullable=True)
        batch_op.alter_column("action", existing_type=sa.Enum(name="action"), nullable=True)

    _drop_constraint_if_exists(bind, "role_permissions", "uq_role_permission")
    _drop_constraint_if_exists(bind, "role_permissions", "uq_role_permission_scope")

    # Reset existing tenant RBAC model and seed immutable defaults.
    op.execute(sa.text("DELETE FROM role_permissions"))
    op.execute(sa.text("DELETE FROM role_assignments"))
    op.execute(sa.text("DELETE FROM roles"))

    tenant_rows = bind.execute(sa.text("SELECT id FROM tenants")).fetchall()
    memberships_rows = bind.execute(
        sa.text("SELECT tenant_id, user_id, role FROM org_memberships WHERE status = 'active'")
    ).fetchall()

    role_ids_by_tenant: dict[str, dict[str, str]] = {}

    for tenant_row in tenant_rows:
        tenant_id = str(tenant_row[0])
        role_ids_by_tenant[tenant_id] = {}

        for role_name in ("owner", "admin", "member"):
            role_id = str(uuid.uuid4())
            role_ids_by_tenant[tenant_id][role_name] = role_id
            bind.execute(
                sa.text(
                    """
                    INSERT INTO roles (id, tenant_id, name, description, is_system, created_at, updated_at)
                    VALUES (:id, :tenant_id, :name, :description, true, NOW(), NOW())
                    """
                ),
                {
                    "id": role_id,
                    "tenant_id": tenant_id,
                    "name": role_name,
                    "description": f"System default {role_name} role",
                },
            )

            for scope_key in DEFAULT_ROLE_SCOPES[role_name]:
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO role_permissions (id, role_id, scope_key, resource_type, action)
                        VALUES (:id, :role_id, :scope_key, NULL, NULL)
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "role_id": role_id,
                        "scope_key": scope_key,
                    },
                )

    # Seed tenant-scope role assignments for existing memberships.
    for membership_row in memberships_rows:
        tenant_id = str(membership_row[0])
        user_id = str(membership_row[1])
        membership_role = str(membership_row[2] or "member").lower()
        if membership_role not in {"owner", "admin", "member"}:
            membership_role = "member"

        role_id = role_ids_by_tenant.get(tenant_id, {}).get(membership_role)
        if not role_id:
            continue

        bind.execute(
            sa.text(
                """
                INSERT INTO role_assignments (
                    id, tenant_id, role_id, user_id, actor_type, scope_id, scope_type, assigned_by, assigned_at
                )
                VALUES (
                    :id, :tenant_id, :role_id, :user_id, :actor_type_value, :scope_id, 'tenant', :assigned_by, NOW()
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "role_id": role_id,
                "user_id": user_id,
                "actor_type_value": actor_type_user_label,
                "scope_id": tenant_id,
                "assigned_by": user_id,
            },
        )

    with op.batch_alter_table("role_permissions") as batch_op:
        batch_op.create_unique_constraint("uq_role_permission_scope", ["role_id", "scope_key"])
        batch_op.alter_column("scope_key", existing_type=sa.String(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("role_permissions") as batch_op:
        batch_op.drop_constraint("uq_role_permission_scope", type_="unique")
        batch_op.alter_column("scope_key", existing_type=sa.String(), nullable=True)

    op.execute(sa.text("DELETE FROM role_permissions WHERE scope_key IS NOT NULL"))

    with op.batch_alter_table("role_permissions") as batch_op:
        batch_op.alter_column("resource_type", existing_type=sa.Enum(name="resourcetype"), nullable=False)
        batch_op.alter_column("action", existing_type=sa.Enum(name="action"), nullable=False)

    with op.batch_alter_table("role_permissions") as batch_op:
        batch_op.create_unique_constraint("uq_role_permission", ["role_id", "resource_type", "action"])

    op.drop_column("role_permissions", "scope_key")
    op.drop_column("agents", "workload_scope_overrides")
    op.drop_column("agents", "workload_scope_profile")
