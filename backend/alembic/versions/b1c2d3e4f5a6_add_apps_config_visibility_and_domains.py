"""add published app config fields and custom domains

Revision ID: b1c2d3e4f5a6
Revises: a7c1d9e4b6f2
Create Date: 2026-02-15 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a7c1d9e4b6f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


published_app_visibility_enum = postgresql.ENUM(
    "public",
    "private",
    name="publishedappvisibility",
    create_type=False,
)

published_app_custom_domain_status_enum = postgresql.ENUM(
    "pending",
    "approved",
    "rejected",
    name="publishedappcustomdomainstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    published_app_visibility_enum.create(bind, checkfirst=True)
    published_app_custom_domain_status_enum.create(bind, checkfirst=True)

    op.add_column("published_apps", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("published_apps", sa.Column("logo_url", sa.String(), nullable=True))
    op.add_column(
        "published_apps",
        sa.Column(
            "visibility",
            published_app_visibility_enum,
            nullable=False,
            server_default="public",
        ),
    )
    op.add_column(
        "published_apps",
        sa.Column(
            "auth_template_key",
            sa.String(),
            nullable=False,
            server_default="auth-classic",
        ),
    )

    op.create_table(
        "published_app_custom_domains",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("host", sa.String(), nullable=False),
        sa.Column("status", published_app_custom_domain_status_enum, nullable=False, server_default="pending"),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("host", name="uq_published_app_custom_domains_host"),
        sa.UniqueConstraint("published_app_id", "host", name="uq_published_app_custom_domains_app_host"),
    )
    op.create_index(
        op.f("ix_published_app_custom_domains_published_app_id"),
        "published_app_custom_domains",
        ["published_app_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_published_app_custom_domains_host"),
        "published_app_custom_domains",
        ["host"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_published_app_custom_domains_host"), table_name="published_app_custom_domains")
    op.drop_index(op.f("ix_published_app_custom_domains_published_app_id"), table_name="published_app_custom_domains")
    op.drop_table("published_app_custom_domains")

    op.drop_column("published_apps", "auth_template_key")
    op.drop_column("published_apps", "visibility")
    op.drop_column("published_apps", "logo_url")
    op.drop_column("published_apps", "description")

    bind = op.get_bind()
    published_app_custom_domain_status_enum.drop(bind, checkfirst=True)
    published_app_visibility_enum.drop(bind, checkfirst=True)
