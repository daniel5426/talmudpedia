"""add published app runtime sdk and external oidc

Revision ID: f3d5c7b9a1e2
Revises: e8c1b2a4d9f0
Create Date: 2026-02-22 19:35:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "f3d5c7b9a1e2"
down_revision = "e8c1b2a4d9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "published_apps",
        sa.Column(
            "allowed_origins",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "published_apps",
        sa.Column(
            "external_auth_oidc",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    op.create_table(
        "published_app_external_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(), nullable=False, server_default=sa.text("'oidc'")),
        sa.Column("issuer", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "published_app_id",
            "provider",
            "issuer",
            "subject",
            name="uq_published_app_external_identity_subject",
        ),
    )
    op.create_index(
        "ix_published_app_external_identities_published_app_id",
        "published_app_external_identities",
        ["published_app_id"],
    )
    op.create_index(
        "ix_published_app_external_identities_user_id",
        "published_app_external_identities",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_published_app_external_identities_user_id", table_name="published_app_external_identities")
    op.drop_index(
        "ix_published_app_external_identities_published_app_id",
        table_name="published_app_external_identities",
    )
    op.drop_table("published_app_external_identities")

    op.drop_column("published_apps", "external_auth_oidc")
    op.drop_column("published_apps", "allowed_origins")
