"""add projects and browser sessions

Revision ID: 9c4d2e1f7a8b
Revises: 6f4a7b2c9d1e, b2c3d4e5f6a7, c3f4e5a6b7d8
Create Date: 2026-04-14 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "9c4d2e1f7a8b"
down_revision = ("6f4a7b2c9d1e", "b2c3d4e5f6a7", "c3f4e5a6b7d8")
branch_labels = None
depends_on = None


project_status_enum = postgresql.ENUM(
    "active",
    "archived",
    name="projectstatus",
    create_type=False,
)
browser_session_status_enum = postgresql.ENUM(
    "active",
    "revoked",
    name="browsersessionstatus",
    create_type=False,
)


def upgrade() -> None:
    project_status_enum.create(op.get_bind(), checkfirst=True)
    browser_session_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", project_status_enum, nullable=False, server_default="active"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])
    op.create_index("ix_projects_slug", "projects", ["slug"])
    op.create_unique_constraint("uq_projects_organization_slug", "projects", ["organization_id", "slug"])

    op.create_table(
        "browser_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("status", browser_session_status_enum, nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_browser_sessions_token_hash"),
    )
    op.create_index("ix_browser_sessions_user_id", "browser_sessions", ["user_id"])
    op.create_index("ix_browser_sessions_organization_id", "browser_sessions", ["organization_id"])
    op.create_index("ix_browser_sessions_project_id", "browser_sessions", ["project_id"])
    op.create_index("ix_browser_sessions_token_hash", "browser_sessions", ["token_hash"])

    op.add_column(
        "org_invites",
        sa.Column(
            "project_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("org_invites", "project_ids")

    op.drop_index("ix_browser_sessions_token_hash", table_name="browser_sessions")
    op.drop_index("ix_browser_sessions_project_id", table_name="browser_sessions")
    op.drop_index("ix_browser_sessions_organization_id", table_name="browser_sessions")
    op.drop_index("ix_browser_sessions_user_id", table_name="browser_sessions")
    op.drop_table("browser_sessions")

    op.drop_constraint("uq_projects_organization_slug", "projects", type_="unique")
    op.drop_index("ix_projects_slug", table_name="projects")
    op.drop_index("ix_projects_organization_id", table_name="projects")
    op.drop_table("projects")

    browser_session_status_enum.drop(op.get_bind(), checkfirst=True)
    project_status_enum.drop(op.get_bind(), checkfirst=True)
