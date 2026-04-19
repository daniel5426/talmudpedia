"""add workos identity mapping

Revision ID: 6c4d5e7f8a9b
Revises: fe2a3b4c5d6e
Create Date: 2026-04-19 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "6c4d5e7f8a9b"
down_revision: Union[str, Sequence[str], None] = "fe2a3b4c5d6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("workos_organization_id", sa.String(), nullable=True))
    op.create_index(op.f("ix_tenants_workos_organization_id"), "tenants", ["workos_organization_id"], unique=True)

    op.add_column("users", sa.Column("workos_user_id", sa.String(), nullable=True))
    op.create_index(op.f("ix_users_workos_user_id"), "users", ["workos_user_id"], unique=True)

    op.add_column("org_memberships", sa.Column("workos_membership_id", sa.String(), nullable=True))
    op.create_index(op.f("ix_org_memberships_workos_membership_id"), "org_memberships", ["workos_membership_id"], unique=True)

    op.create_table(
        "workos_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workos_event_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="received"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workos_webhook_events_workos_event_id"), "workos_webhook_events", ["workos_event_id"], unique=True)
    op.create_index(op.f("ix_workos_webhook_events_event_type"), "workos_webhook_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_workos_webhook_events_organization_id"), "workos_webhook_events", ["organization_id"], unique=False)
    op.create_index(op.f("ix_workos_webhook_events_user_id"), "workos_webhook_events", ["user_id"], unique=False)
    op.create_index(op.f("ix_workos_webhook_events_status"), "workos_webhook_events", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_workos_webhook_events_status"), table_name="workos_webhook_events")
    op.drop_index(op.f("ix_workos_webhook_events_user_id"), table_name="workos_webhook_events")
    op.drop_index(op.f("ix_workos_webhook_events_organization_id"), table_name="workos_webhook_events")
    op.drop_index(op.f("ix_workos_webhook_events_event_type"), table_name="workos_webhook_events")
    op.drop_index(op.f("ix_workos_webhook_events_workos_event_id"), table_name="workos_webhook_events")
    op.drop_table("workos_webhook_events")

    op.drop_index(op.f("ix_org_memberships_workos_membership_id"), table_name="org_memberships")
    op.drop_column("org_memberships", "workos_membership_id")

    op.drop_index(op.f("ix_users_workos_user_id"), table_name="users")
    op.drop_column("users", "workos_user_id")

    op.drop_index(op.f("ix_tenants_workos_organization_id"), table_name="tenants")
    op.drop_column("tenants", "workos_organization_id")
