"""add usage quota policies, counters, and reservations

Revision ID: 3f8a1c2d9b7e
Revises: b8d1e2f3a4b5, c7f1a2b3d4e5, a1c4d9e8f7b6, a4b5c6d7e8f9, b7e2c1d9a4f3, 9b6c5d4e3f21, d4e9f1a2b3c4, b1c2d3e4f5a6, c2f7a9d8e1b4, f9b4e1c2d3a6, 6a1d4e9b2c7f
Create Date: 2026-03-02 16:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "3f8a1c2d9b7e"
down_revision: Union[str, Sequence[str], None] = (
    "b8d1e2f3a4b5",
    "c7f1a2b3d4e5",
    "a1c4d9e8f7b6",
    "a4b5c6d7e8f9",
    "b7e2c1d9a4f3",
    "9b6c5d4e3f21",
    "d4e9f1a2b3c4",
    "b1c2d3e4f5a6",
    "c2f7a9d8e1b4",
    "f9b4e1c2d3a6",
    "6a1d4e9b2c7f",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


usage_quota_scope_type = postgresql.ENUM(
    "tenant",
    "user",
    name="usagequotascopetype",
    create_type=False,
)
usage_quota_period_type = postgresql.ENUM(
    "monthly",
    name="usagequotaperiodtype",
    create_type=False,
)
usage_quota_reservation_status = postgresql.ENUM(
    "active",
    "settled",
    "released",
    "expired",
    name="usagequotareservationstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    usage_quota_scope_type.create(bind, checkfirst=True)
    usage_quota_period_type.create(bind, checkfirst=True)
    usage_quota_reservation_status.create(bind, checkfirst=True)

    op.create_table(
        "usage_quota_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope_type", usage_quota_scope_type, nullable=False),
        sa.Column("period_type", usage_quota_period_type, nullable=False),
        sa.Column("limit_tokens", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(), server_default=sa.text("'UTC'"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_usage_quota_policies_tenant_id"), "usage_quota_policies", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_usage_quota_policies_user_id"), "usage_quota_policies", ["user_id"], unique=False)
    op.create_index(op.f("ix_usage_quota_policies_scope_type"), "usage_quota_policies", ["scope_type"], unique=False)
    op.create_index(
        "ix_usage_quota_policies_lookup",
        "usage_quota_policies",
        ["tenant_id", "user_id", "scope_type", "is_active"],
        unique=False,
    )

    op.create_table(
        "usage_quota_counters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_type", usage_quota_scope_type, nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("reserved_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope_type", "scope_id", "period_start", name="uq_usage_quota_counters_scope_period"),
    )
    op.create_index(op.f("ix_usage_quota_counters_scope_type"), "usage_quota_counters", ["scope_type"], unique=False)
    op.create_index(op.f("ix_usage_quota_counters_scope_id"), "usage_quota_counters", ["scope_id"], unique=False)
    op.create_index(op.f("ix_usage_quota_counters_period_start"), "usage_quota_counters", ["period_start"], unique=False)

    op.create_table(
        "usage_quota_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_tokens_user", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("reserved_tokens_tenant", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", usage_quota_reservation_status, server_default=sa.text("'active'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index(op.f("ix_usage_quota_reservations_run_id"), "usage_quota_reservations", ["run_id"], unique=True)
    op.create_index(op.f("ix_usage_quota_reservations_tenant_id"), "usage_quota_reservations", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_usage_quota_reservations_user_id"), "usage_quota_reservations", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_usage_quota_reservations_period_start"),
        "usage_quota_reservations",
        ["period_start"],
        unique=False,
    )
    op.create_index(op.f("ix_usage_quota_reservations_status"), "usage_quota_reservations", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_usage_quota_reservations_status"), table_name="usage_quota_reservations")
    op.drop_index(op.f("ix_usage_quota_reservations_period_start"), table_name="usage_quota_reservations")
    op.drop_index(op.f("ix_usage_quota_reservations_user_id"), table_name="usage_quota_reservations")
    op.drop_index(op.f("ix_usage_quota_reservations_tenant_id"), table_name="usage_quota_reservations")
    op.drop_index(op.f("ix_usage_quota_reservations_run_id"), table_name="usage_quota_reservations")
    op.drop_table("usage_quota_reservations")

    op.drop_index(op.f("ix_usage_quota_counters_period_start"), table_name="usage_quota_counters")
    op.drop_index(op.f("ix_usage_quota_counters_scope_id"), table_name="usage_quota_counters")
    op.drop_index(op.f("ix_usage_quota_counters_scope_type"), table_name="usage_quota_counters")
    op.drop_table("usage_quota_counters")

    op.drop_index("ix_usage_quota_policies_lookup", table_name="usage_quota_policies")
    op.drop_index(op.f("ix_usage_quota_policies_scope_type"), table_name="usage_quota_policies")
    op.drop_index(op.f("ix_usage_quota_policies_user_id"), table_name="usage_quota_policies")
    op.drop_index(op.f("ix_usage_quota_policies_tenant_id"), table_name="usage_quota_policies")
    op.drop_table("usage_quota_policies")

    bind = op.get_bind()
    usage_quota_reservation_status.drop(bind, checkfirst=True)
    usage_quota_period_type.drop(bind, checkfirst=True)
    usage_quota_scope_type.drop(bind, checkfirst=True)
