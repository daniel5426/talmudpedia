"""add published apps phase1_3

Revision ID: 9a4c7e21b3d5
Revises: e6f1a9b4c2d0
Create Date: 2026-02-10 16:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9a4c7e21b3d5"
down_revision: Union[str, None] = "e6f1a9b4c2d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


published_app_status_enum = postgresql.ENUM(
    "draft",
    "published",
    "paused",
    "archived",
    name="publishedappstatus",
    create_type=False,
)
published_app_membership_status_enum = postgresql.ENUM(
    "active",
    "blocked",
    name="publishedappusermembershipstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    published_app_status_enum.create(bind, checkfirst=True)
    published_app_membership_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "published_apps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("status", published_app_status_enum, nullable=False, server_default="draft"),
        sa.Column("auth_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("auth_providers", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[\"password\"]'::jsonb")),
        sa.Column("published_url", sa.String(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_published_apps_tenant_name"),
    )
    op.create_index(op.f("ix_published_apps_agent_id"), "published_apps", ["agent_id"], unique=False)
    op.create_index(op.f("ix_published_apps_slug"), "published_apps", ["slug"], unique=True)
    op.create_index(op.f("ix_published_apps_tenant_id"), "published_apps", ["tenant_id"], unique=False)

    op.create_table(
        "published_app_user_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", published_app_membership_status_enum, nullable=False, server_default="active"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("published_app_id", "user_id", name="uq_published_app_user_membership"),
    )
    op.create_index(op.f("ix_published_app_user_memberships_published_app_id"), "published_app_user_memberships", ["published_app_id"], unique=False)
    op.create_index(op.f("ix_published_app_user_memberships_user_id"), "published_app_user_memberships", ["user_id"], unique=False)

    op.create_table(
        "published_app_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jti", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_published_app_sessions_app_user", "published_app_sessions", ["published_app_id", "user_id"], unique=False)
    op.create_index(op.f("ix_published_app_sessions_expires_at"), "published_app_sessions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_published_app_sessions_jti"), "published_app_sessions", ["jti"], unique=True)
    op.create_index(op.f("ix_published_app_sessions_published_app_id"), "published_app_sessions", ["published_app_id"], unique=False)
    op.create_index(op.f("ix_published_app_sessions_revoked_at"), "published_app_sessions", ["revoked_at"], unique=False)
    op.create_index(op.f("ix_published_app_sessions_user_id"), "published_app_sessions", ["user_id"], unique=False)

    op.add_column("chats", sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_chats_published_app_id",
        "chats",
        "published_apps",
        ["published_app_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_chats_published_app_id"), "chats", ["published_app_id"], unique=False)
    op.create_index("ix_chats_published_app_user_updated", "chats", ["published_app_id", "user_id", "updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chats_published_app_user_updated", table_name="chats")
    op.drop_index(op.f("ix_chats_published_app_id"), table_name="chats")
    op.drop_constraint("fk_chats_published_app_id", "chats", type_="foreignkey")
    op.drop_column("chats", "published_app_id")

    op.drop_index(op.f("ix_published_app_sessions_user_id"), table_name="published_app_sessions")
    op.drop_index(op.f("ix_published_app_sessions_revoked_at"), table_name="published_app_sessions")
    op.drop_index(op.f("ix_published_app_sessions_published_app_id"), table_name="published_app_sessions")
    op.drop_index(op.f("ix_published_app_sessions_jti"), table_name="published_app_sessions")
    op.drop_index(op.f("ix_published_app_sessions_expires_at"), table_name="published_app_sessions")
    op.drop_index("ix_published_app_sessions_app_user", table_name="published_app_sessions")
    op.drop_table("published_app_sessions")

    op.drop_index(op.f("ix_published_app_user_memberships_user_id"), table_name="published_app_user_memberships")
    op.drop_index(op.f("ix_published_app_user_memberships_published_app_id"), table_name="published_app_user_memberships")
    op.drop_table("published_app_user_memberships")

    op.drop_index(op.f("ix_published_apps_tenant_id"), table_name="published_apps")
    op.drop_index(op.f("ix_published_apps_slug"), table_name="published_apps")
    op.drop_index(op.f("ix_published_apps_agent_id"), table_name="published_apps")
    op.drop_table("published_apps")

    bind = op.get_bind()
    published_app_membership_status_enum.drop(bind, checkfirst=True)
    published_app_status_enum.drop(bind, checkfirst=True)
