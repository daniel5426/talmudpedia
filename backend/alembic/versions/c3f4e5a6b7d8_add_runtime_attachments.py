"""add runtime attachments

Revision ID: c3f4e5a6b7d8
Revises: 0a1b2c3d4e5f, 11e6a7c4b9d2, a1b9d7c5e3f0
Create Date: 2026-03-19 16:15:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "c3f4e5a6b7d8"
down_revision = ("0a1b2c3d4e5f", "11e6a7c4b9d2", "a1b9d7c5e3f0")
branch_labels = None
depends_on = ("1f2e3d4c5b6a",)


agentthreadsurface = postgresql.ENUM(
    "internal",
    "embedded_runtime",
    "published_host_runtime",
    "artifact_coding_agent",
    "published_app_coding_agent",
    name="agentthreadsurface",
    create_type=False,
)
runtimeattachmentkind = postgresql.ENUM(
    "image",
    "document",
    "audio",
    name="runtimeattachmentkind",
    create_type=False,
)
runtimeattachmentstatus = postgresql.ENUM(
    "uploaded",
    "processed",
    "failed",
    name="runtimeattachmentstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    runtimeattachmentkind.create(bind, checkfirst=True)
    runtimeattachmentstatus.create(bind, checkfirst=True)

    op.create_table(
        "runtime_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("app_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tenant_api_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_app_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_user_id", sa.String(length=255), nullable=True),
        sa.Column("external_session_id", sa.String(length=255), nullable=True),
        sa.Column("surface", agentthreadsurface, nullable=False),
        sa.Column("kind", runtimeattachmentkind, nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("filename", sa.String(length=1024), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=2048), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", runtimeattachmentstatus, nullable=False),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["app_account_id"], ["published_app_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["published_app_id"], ["published_apps.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_api_key_id"], ["tenant_api_keys.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["agent_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(op.f("ix_runtime_attachments_agent_id"), "runtime_attachments", ["agent_id"], unique=False)
    op.create_index(op.f("ix_runtime_attachments_app_account_id"), "runtime_attachments", ["app_account_id"], unique=False)
    op.create_index(op.f("ix_runtime_attachments_external_session_id"), "runtime_attachments", ["external_session_id"], unique=False)
    op.create_index(op.f("ix_runtime_attachments_external_user_id"), "runtime_attachments", ["external_user_id"], unique=False)
    op.create_index(op.f("ix_runtime_attachments_kind"), "runtime_attachments", ["kind"], unique=False)
    op.create_index(op.f("ix_runtime_attachments_published_app_id"), "runtime_attachments", ["published_app_id"], unique=False)
    op.create_index(op.f("ix_runtime_attachments_sha256"), "runtime_attachments", ["sha256"], unique=False)
    op.create_index(op.f("ix_runtime_attachments_status"), "runtime_attachments", ["status"], unique=False)
    op.create_index(op.f("ix_runtime_attachments_surface"), "runtime_attachments", ["surface"], unique=False)
    op.create_index(op.f("ix_runtime_attachments_tenant_api_key_id"), "runtime_attachments", ["tenant_api_key_id"], unique=False)
    op.create_index(op.f("ix_runtime_attachments_tenant_id"), "runtime_attachments", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_runtime_attachments_thread_id"), "runtime_attachments", ["thread_id"], unique=False)
    op.create_index(op.f("ix_runtime_attachments_user_id"), "runtime_attachments", ["user_id"], unique=False)
    op.create_index(
        "ix_runtime_attachments_scope_lookup",
        "runtime_attachments",
        ["tenant_id", "surface", "thread_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_runtime_attachments_embed_lookup",
        "runtime_attachments",
        ["tenant_id", "agent_id", "external_user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "agent_thread_turn_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attachment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["attachment_id"], ["runtime_attachments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["turn_id"], ["agent_thread_turns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("turn_id", "attachment_id", name="uq_agent_thread_turn_attachment"),
    )
    op.create_index(
        op.f("ix_agent_thread_turn_attachments_attachment_id"),
        "agent_thread_turn_attachments",
        ["attachment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_thread_turn_attachments_turn_id"),
        "agent_thread_turn_attachments",
        ["turn_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_thread_turn_attachments_turn_id"), table_name="agent_thread_turn_attachments")
    op.drop_index(op.f("ix_agent_thread_turn_attachments_attachment_id"), table_name="agent_thread_turn_attachments")
    op.drop_table("agent_thread_turn_attachments")

    op.drop_index("ix_runtime_attachments_scope_lookup", table_name="runtime_attachments")
    op.drop_index("ix_runtime_attachments_embed_lookup", table_name="runtime_attachments")
    op.drop_index(op.f("ix_runtime_attachments_user_id"), table_name="runtime_attachments")
    op.drop_index(op.f("ix_runtime_attachments_thread_id"), table_name="runtime_attachments")
    op.drop_index(op.f("ix_runtime_attachments_tenant_id"), table_name="runtime_attachments")
    op.drop_index(op.f("ix_runtime_attachments_tenant_api_key_id"), table_name="runtime_attachments")
    op.drop_index(op.f("ix_runtime_attachments_surface"), table_name="runtime_attachments")
    op.drop_index(op.f("ix_runtime_attachments_status"), table_name="runtime_attachments")
    op.drop_index(op.f("ix_runtime_attachments_sha256"), table_name="runtime_attachments")
    op.drop_index(op.f("ix_runtime_attachments_published_app_id"), table_name="runtime_attachments")
    op.drop_index(op.f("ix_runtime_attachments_kind"), table_name="runtime_attachments")
    op.drop_index(op.f("ix_runtime_attachments_external_user_id"), table_name="runtime_attachments")
    op.drop_index(op.f("ix_runtime_attachments_external_session_id"), table_name="runtime_attachments")
    op.drop_index(op.f("ix_runtime_attachments_app_account_id"), table_name="runtime_attachments")
    op.drop_index(op.f("ix_runtime_attachments_agent_id"), table_name="runtime_attachments")
    op.drop_table("runtime_attachments")

    bind = op.get_bind()
    runtimeattachmentstatus.drop(bind, checkfirst=True)
    runtimeattachmentkind.drop(bind, checkfirst=True)
