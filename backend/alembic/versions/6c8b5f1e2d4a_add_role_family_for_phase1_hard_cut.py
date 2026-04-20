"""add_role_family_for_phase1_hard_cut

Revision ID: 6c8b5f1e2d4a
Revises: e6f1a9b4c2d0
Create Date: 2026-04-20 18:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6c8b5f1e2d4a"
down_revision: Union[str, None] = "e6f1a9b4c2d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("roles", sa.Column("family", sa.String(), nullable=True))
    op.execute(
        """
        UPDATE roles
        SET family = CASE
            WHEN name IN ('organization_owner', 'organization_admin', 'organization_member', 'owner', 'admin', 'member') THEN 'organization'
            WHEN name IN ('project_owner', 'project_admin', 'project_editor', 'project_viewer') THEN 'project'
            ELSE 'project'
        END
        """
    )
    op.alter_column("roles", "family", nullable=False)
    op.drop_constraint("uq_role_tenant_name", "roles", type_="unique")
    op.create_unique_constraint("uq_role_tenant_family_name", "roles", ["tenant_id", "family", "name"])
    op.create_index(op.f("ix_roles_family"), "roles", ["family"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_roles_family"), table_name="roles")
    op.drop_constraint("uq_role_tenant_family_name", "roles", type_="unique")
    op.create_unique_constraint("uq_role_tenant_name", "roles", ["tenant_id", "name"])
    op.drop_column("roles", "family")
