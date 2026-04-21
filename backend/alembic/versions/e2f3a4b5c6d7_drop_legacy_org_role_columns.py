"""drop legacy org role columns

Revision ID: e2f3a4b5c6d7
Revises: e1f2a3b4c5d6
Create Date: 2026-04-21 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e2f3a4b5c6d7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


ORG_ROLE_ENUM = postgresql.ENUM("owner", "admin", "member", name="orgrole")


def upgrade() -> None:
    with op.batch_alter_table("org_memberships") as batch_op:
        batch_op.drop_column("role")

    with op.batch_alter_table("org_invites") as batch_op:
        batch_op.drop_column("role")

    bind = op.get_bind()
    ORG_ROLE_ENUM.drop(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    ORG_ROLE_ENUM.create(bind, checkfirst=True)

    with op.batch_alter_table("org_memberships") as batch_op:
        batch_op.add_column(
            sa.Column("role", sa.Enum("owner", "admin", "member", name="orgrole"), nullable=False, server_default="member")
        )

    with op.batch_alter_table("org_invites") as batch_op:
        batch_op.add_column(
            sa.Column("role", sa.Enum("owner", "admin", "member", name="orgrole"), nullable=False, server_default="member")
        )

    with op.batch_alter_table("org_memberships") as batch_op:
        batch_op.alter_column("role", server_default=None)

    with op.batch_alter_table("org_invites") as batch_op:
        batch_op.alter_column("role", server_default=None)
