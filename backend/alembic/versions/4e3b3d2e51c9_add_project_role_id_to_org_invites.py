"""add project_role_id to org_invites

Revision ID: 4e3b3d2e51c9
Revises: 6c8b5f1e2d4a
Create Date: 2026-04-20 17:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "4e3b3d2e51c9"
down_revision = "6c8b5f1e2d4a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "org_invites",
        sa.Column("project_role_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_org_invites_project_role_id_roles",
        "org_invites",
        "roles",
        ["project_role_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_org_invites_project_role_id_roles", "org_invites", type_="foreignkey")
    op.drop_column("org_invites", "project_role_id")
