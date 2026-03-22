"""add published app analytics events

Revision ID: fe2a3b4c5d6e
Revises: fd1a2b3c4d5e
Create Date: 2026-03-22 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect, text


revision: str = "fe2a3b4c5d6e"
down_revision: Union[str, Sequence[str], None] = "fd1a2b3c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    bind.execute(
        text(
            """
            DO $$
            BEGIN
                CREATE TYPE publishedappanalyticseventtype AS ENUM (
                    'bootstrap_view',
                    'visit_started'
                );
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END
            $$;
            """
        )
    )
    bind.execute(
        text(
            """
            DO $$
            BEGIN
                CREATE TYPE publishedappanalyticssurface AS ENUM (
                    'host_runtime',
                    'external_runtime',
                    'preview_runtime'
                );
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END
            $$;
            """
        )
    )

    if "published_app_analytics_events" in inspector.get_table_names():
        return

    analytics_event_type = postgresql.ENUM(
        "bootstrap_view",
        "visit_started",
        name="publishedappanalyticseventtype",
        create_type=False,
    )
    analytics_surface = postgresql.ENUM(
        "host_runtime",
        "external_runtime",
        "preview_runtime",
        name="publishedappanalyticssurface",
        create_type=False,
    )

    op.create_table(
        "published_app_analytics_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", analytics_event_type, nullable=False),
        sa.Column("surface", analytics_surface, nullable=False),
        sa.Column("visitor_key", sa.String(length=128), nullable=False),
        sa.Column("visit_key", sa.String(length=128), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=True),
        sa.Column("referer", sa.String(length=1024), nullable=True),
        sa.Column("user_agent", sa.String(length=1024), nullable=True),
        sa.Column("ip_hash", sa.String(length=128), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["app_account_id"], ["published_app_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["published_app_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_published_app_analytics_events_tenant_id"), "published_app_analytics_events", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_published_app_analytics_events_published_app_id"), "published_app_analytics_events", ["published_app_id"], unique=False)
    op.create_index(op.f("ix_published_app_analytics_events_app_account_id"), "published_app_analytics_events", ["app_account_id"], unique=False)
    op.create_index(op.f("ix_published_app_analytics_events_session_id"), "published_app_analytics_events", ["session_id"], unique=False)
    op.create_index(op.f("ix_published_app_analytics_events_event_type"), "published_app_analytics_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_published_app_analytics_events_surface"), "published_app_analytics_events", ["surface"], unique=False)
    op.create_index(op.f("ix_published_app_analytics_events_visitor_key"), "published_app_analytics_events", ["visitor_key"], unique=False)
    op.create_index(op.f("ix_published_app_analytics_events_visit_key"), "published_app_analytics_events", ["visit_key"], unique=False)
    op.create_index(op.f("ix_published_app_analytics_events_ip_hash"), "published_app_analytics_events", ["ip_hash"], unique=False)
    op.create_index(op.f("ix_published_app_analytics_events_occurred_at"), "published_app_analytics_events", ["occurred_at"], unique=False)
    op.create_index(
        "ix_published_app_analytics_app_visitor_event_occurred",
        "published_app_analytics_events",
        ["published_app_id", "visitor_key", "event_type", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_published_app_analytics_tenant_app_occurred",
        "published_app_analytics_events",
        ["tenant_id", "published_app_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_published_app_analytics_tenant_app_occurred", table_name="published_app_analytics_events")
    op.drop_index("ix_published_app_analytics_app_visitor_event_occurred", table_name="published_app_analytics_events")
    op.drop_index(op.f("ix_published_app_analytics_events_occurred_at"), table_name="published_app_analytics_events")
    op.drop_index(op.f("ix_published_app_analytics_events_ip_hash"), table_name="published_app_analytics_events")
    op.drop_index(op.f("ix_published_app_analytics_events_visit_key"), table_name="published_app_analytics_events")
    op.drop_index(op.f("ix_published_app_analytics_events_visitor_key"), table_name="published_app_analytics_events")
    op.drop_index(op.f("ix_published_app_analytics_events_surface"), table_name="published_app_analytics_events")
    op.drop_index(op.f("ix_published_app_analytics_events_event_type"), table_name="published_app_analytics_events")
    op.drop_index(op.f("ix_published_app_analytics_events_session_id"), table_name="published_app_analytics_events")
    op.drop_index(op.f("ix_published_app_analytics_events_app_account_id"), table_name="published_app_analytics_events")
    op.drop_index(op.f("ix_published_app_analytics_events_published_app_id"), table_name="published_app_analytics_events")
    op.drop_index(op.f("ix_published_app_analytics_events_tenant_id"), table_name="published_app_analytics_events")
    op.drop_table("published_app_analytics_events")

    bind = op.get_bind()
    postgresql.ENUM(name="publishedappanalyticssurface").drop(bind, checkfirst=True)
    postgresql.ENUM(name="publishedappanalyticseventtype").drop(bind, checkfirst=True)
