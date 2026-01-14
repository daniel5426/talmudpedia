"""add_cascading_deletes_to_core_tables

Revision ID: 98948ff46801
Revises: 999c908e4fce
Create Date: 2026-01-14 01:05:01.948847

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '98948ff46801'
down_revision: Union[str, None] = '999c908e4fce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Org Memberships
    op.drop_constraint('org_memberships_user_id_fkey', 'org_memberships', type_='foreignkey')
    op.create_foreign_key('org_memberships_user_id_fkey', 'org_memberships', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    op.drop_constraint('org_memberships_tenant_id_fkey', 'org_memberships', type_='foreignkey')
    op.create_foreign_key('org_memberships_tenant_id_fkey', 'org_memberships', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    op.drop_constraint('org_memberships_org_unit_id_fkey', 'org_memberships', type_='foreignkey')
    op.create_foreign_key('org_memberships_org_unit_id_fkey', 'org_memberships', 'org_units', ['org_unit_id'], ['id'], ondelete='CASCADE')

    # Org Units
    op.drop_constraint('org_units_tenant_id_fkey', 'org_units', type_='foreignkey')
    op.create_foreign_key('org_units_tenant_id_fkey', 'org_units', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    op.drop_constraint('org_units_parent_id_fkey', 'org_units', type_='foreignkey')
    op.create_foreign_key('org_units_parent_id_fkey', 'org_units', 'org_units', ['parent_id'], ['id'], ondelete='CASCADE')

    # RBAC - Roles
    op.drop_constraint('roles_tenant_id_fkey', 'roles', type_='foreignkey')
    op.create_foreign_key('roles_tenant_id_fkey', 'roles', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    # RBAC - Role Permissions
    op.drop_constraint('role_permissions_role_id_fkey', 'role_permissions', type_='foreignkey')
    op.create_foreign_key('role_permissions_role_id_fkey', 'role_permissions', 'roles', ['role_id'], ['id'], ondelete='CASCADE')

    # RBAC - Role Assignments
    op.drop_constraint('role_assignments_user_id_fkey', 'role_assignments', type_='foreignkey')
    op.create_foreign_key('role_assignments_user_id_fkey', 'role_assignments', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    op.drop_constraint('role_assignments_tenant_id_fkey', 'role_assignments', type_='foreignkey')
    op.create_foreign_key('role_assignments_tenant_id_fkey', 'role_assignments', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    op.drop_constraint('role_assignments_role_id_fkey', 'role_assignments', type_='foreignkey')
    op.create_foreign_key('role_assignments_role_id_fkey', 'role_assignments', 'roles', ['role_id'], ['id'], ondelete='CASCADE')

    # Tools
    op.drop_constraint('tool_versions_tool_id_fkey', 'tool_versions', type_='foreignkey')
    op.create_foreign_key('tool_versions_tool_id_fkey', 'tool_versions', 'tool_registry', ['tool_id'], ['id'], ondelete='CASCADE')

    # Chats - Tenant (User was done in separate migration)
    op.drop_constraint('chats_tenant_id_fkey', 'chats', type_='foreignkey')
    op.create_foreign_key('chats_tenant_id_fkey', 'chats', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    # Chats
    op.drop_constraint('chats_tenant_id_fkey', 'chats', type_='foreignkey')
    op.create_foreign_key('chats_tenant_id_fkey', 'chats', 'tenants', ['tenant_id'], ['id'])

    # Tools
    op.drop_constraint('tool_versions_tool_id_fkey', 'tool_versions', type_='foreignkey')
    op.create_foreign_key('tool_versions_tool_id_fkey', 'tool_versions', 'tool_registry', ['tool_id'], ['id'])

    # RBAC
    op.drop_constraint('role_assignments_role_id_fkey', 'role_assignments', type_='foreignkey')
    op.create_foreign_key('role_assignments_role_id_fkey', 'role_assignments', 'roles', ['role_id'], ['id'])

    op.drop_constraint('role_assignments_tenant_id_fkey', 'role_assignments', type_='foreignkey')
    op.create_foreign_key('role_assignments_tenant_id_fkey', 'role_assignments', 'tenants', ['tenant_id'], ['id'])

    op.drop_constraint('role_assignments_user_id_fkey', 'role_assignments', type_='foreignkey')
    op.create_foreign_key('role_assignments_user_id_fkey', 'role_assignments', 'users', ['user_id'], ['id'])

    op.drop_constraint('role_permissions_role_id_fkey', 'role_permissions', type_='foreignkey')
    op.create_foreign_key('role_permissions_role_id_fkey', 'role_permissions', 'roles', ['role_id'], ['id'])

    op.drop_constraint('roles_tenant_id_fkey', 'roles', type_='foreignkey')
    op.create_foreign_key('roles_tenant_id_fkey', 'roles', 'tenants', ['tenant_id'], ['id'])

    # Org Units
    op.drop_constraint('org_units_parent_id_fkey', 'org_units', type_='foreignkey')
    op.create_foreign_key('org_units_parent_id_fkey', 'org_units', 'org_units', ['parent_id'], ['id'])

    op.drop_constraint('org_units_tenant_id_fkey', 'org_units', type_='foreignkey')
    op.create_foreign_key('org_units_tenant_id_fkey', 'org_units', 'tenants', ['tenant_id'], ['id'])

    # Org Memberships
    op.drop_constraint('org_memberships_org_unit_id_fkey', 'org_memberships', type_='foreignkey')
    op.create_foreign_key('org_memberships_org_unit_id_fkey', 'org_memberships', 'org_units', ['org_unit_id'], ['id'])

    op.drop_constraint('org_memberships_tenant_id_fkey', 'org_memberships', type_='foreignkey')
    op.create_foreign_key('org_memberships_tenant_id_fkey', 'org_memberships', 'tenants', ['tenant_id'], ['id'])

    op.drop_constraint('org_memberships_user_id_fkey', 'org_memberships', type_='foreignkey')
    op.create_foreign_key('org_memberships_user_id_fkey', 'org_memberships', 'users', ['user_id'], ['id'])
