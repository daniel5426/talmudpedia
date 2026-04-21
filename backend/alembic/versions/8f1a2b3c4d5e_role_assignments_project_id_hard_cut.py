"""role_assignments_project_id_hard_cut

Revision ID: 8f1a2b3c4d5e
Revises: 4e3b3d2e51c9
Create Date: 2026-04-20 21:15:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "8f1a2b3c4d5e"
down_revision: Union[str, None] = "4e3b3d2e51c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = "9c4d2e1f7a8b"


ROLE_ASSIGNMENTS = "role_assignments"


def _scalar(bind, sql: str) -> int:
    return int(bind.execute(sa.text(sql)).scalar() or 0)


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column(
        ROLE_ASSIGNMENTS,
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    invalid_actor_type = _scalar(
        bind,
        "SELECT count(*) FROM role_assignments WHERE actor_type IS DISTINCT FROM 'USER'",
    )
    if invalid_actor_type:
        raise RuntimeError("role_assignments contains non-user actor_type rows; hard cut aborted")

    invalid_scope_type = _scalar(
        bind,
        "SELECT count(*) FROM role_assignments WHERE scope_type NOT IN ('organization', 'project', 'tenant') OR scope_type IS NULL",
    )
    if invalid_scope_type:
        raise RuntimeError("role_assignments contains unsupported scope_type rows; hard cut aborted")

    bind.execute(
        sa.text(
            """
            UPDATE role_assignments
            SET project_id = CASE
                WHEN scope_type = 'project' THEN scope_id
                WHEN scope_type = 'tenant' THEN NULL
                ELSE NULL
            END
            """
        )
    )

    bind.execute(
        sa.text(
            """
            DELETE FROM role_assignments ra
            WHERE ra.project_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM projects p
                  WHERE p.id = ra.project_id
              )
            """
        )
    )

    op.create_foreign_key(
        "fk_role_assignments_project_id_projects",
        ROLE_ASSIGNMENTS,
        "projects",
        ["project_id"],
        ["id"],
    )
    op.create_index(
        "uq_role_assignments_org_user",
        ROLE_ASSIGNMENTS,
        ["tenant_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("project_id IS NULL"),
    )
    op.create_index(
        "uq_role_assignments_project_user",
        ROLE_ASSIGNMENTS,
        ["tenant_id", "user_id", "project_id"],
        unique=True,
        postgresql_where=sa.text("project_id IS NOT NULL"),
    )

    op.drop_index(op.f("ix_role_assignments_scope_id"), table_name=ROLE_ASSIGNMENTS)
    op.drop_column(ROLE_ASSIGNMENTS, "scope_type")
    op.drop_column(ROLE_ASSIGNMENTS, "scope_id")
    op.drop_column(ROLE_ASSIGNMENTS, "actor_type")


def downgrade() -> None:
    op.add_column(
        ROLE_ASSIGNMENTS,
        sa.Column("actor_type", sa.Enum("USER", "SERVICE", "AGENT", name="actortype"), nullable=False, server_default="USER"),
    )
    op.add_column(ROLE_ASSIGNMENTS, sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False))
    op.add_column(ROLE_ASSIGNMENTS, sa.Column("scope_type", sa.String(), nullable=False, server_default="organization"))

    op.execute(
        """
        UPDATE role_assignments
        SET scope_type = CASE WHEN project_id IS NULL THEN 'organization' ELSE 'project' END,
            scope_id = COALESCE(project_id, tenant_id),
            actor_type = 'USER'
        """
    )

    op.create_index(op.f("ix_role_assignments_scope_id"), ROLE_ASSIGNMENTS, ["scope_id"], unique=False)
    op.drop_index("uq_role_assignments_project_user", table_name=ROLE_ASSIGNMENTS)
    op.drop_index("uq_role_assignments_org_user", table_name=ROLE_ASSIGNMENTS)
    op.drop_constraint("fk_role_assignments_project_id_projects", ROLE_ASSIGNMENTS, type_="foreignkey")
    op.drop_column(ROLE_ASSIGNMENTS, "project_id")
