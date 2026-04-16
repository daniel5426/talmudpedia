"""add files domain v1

Revision ID: a8f3c1d2e4b5
Revises: 9c4d2e1f7a8b
Create Date: 2026-04-16 14:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "a8f3c1d2e4b5"
down_revision = "9c4d2e1f7a8b"
branch_labels = None
depends_on = None


file_space_status_enum = postgresql.ENUM(
    "active",
    "archived",
    name="filespacestatus",
    create_type=False,
)
file_entry_type_enum = postgresql.ENUM(
    "file",
    "directory",
    name="fileentrytype",
    create_type=False,
)
file_access_mode_enum = postgresql.ENUM(
    "read",
    "read_write",
    name="fileaccessmode",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    file_space_status_enum.create(bind, checkfirst=True)
    file_entry_type_enum.create(bind, checkfirst=True)
    file_access_mode_enum.create(bind, checkfirst=True)

    op.create_table(
        "file_spaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", file_space_status_enum, nullable=False, server_default="active"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_file_spaces_tenant_id", "file_spaces", ["tenant_id"])
    op.create_index("ix_file_spaces_project_id", "file_spaces", ["project_id"])
    op.create_index("ix_file_spaces_status", "file_spaces", ["status"])

    op.create_table(
        "file_space_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("space_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path", sa.String(length=2048), nullable=False),
        sa.Column("entry_type", file_entry_type_enum, nullable=False),
        sa.Column("current_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("is_text", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["space_id"], ["file_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("space_id", "path", name="uq_file_space_entries_space_path"),
    )
    op.create_index("ix_file_space_entries_space_id", "file_space_entries", ["space_id"])
    op.create_index("ix_file_space_entries_entry_type", "file_space_entries", ["entry_type"])
    op.create_index("ix_file_space_entries_current_revision_id", "file_space_entries", ["current_revision_id"])
    op.create_index("ix_file_space_entries_created_by", "file_space_entries", ["created_by"])
    op.create_index("ix_file_space_entries_updated_by", "file_space_entries", ["updated_by"])
    op.create_index("ix_file_space_entries_deleted_at", "file_space_entries", ["deleted_at"])
    op.create_index(
        "ix_file_space_entries_space_deleted_path",
        "file_space_entries",
        ["space_id", "deleted_at", "path"],
    )

    op.create_table(
        "file_entry_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=2048), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("is_text", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("encoding", sa.String(length=64), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["file_space_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_file_entry_revisions_storage_key"),
    )
    op.create_index("ix_file_entry_revisions_entry_id", "file_entry_revisions", ["entry_id"])
    op.create_index("ix_file_entry_revisions_sha256", "file_entry_revisions", ["sha256"])
    op.create_index("ix_file_entry_revisions_created_by", "file_entry_revisions", ["created_by"])
    op.create_index("ix_file_entry_revisions_created_by_run_id", "file_entry_revisions", ["created_by_run_id"])
    op.create_index("ix_file_entry_revisions_entry_created", "file_entry_revisions", ["entry_id", "created_at"])

    op.create_foreign_key(
        "fk_file_space_entries_current_revision_id",
        "file_space_entries",
        "file_entry_revisions",
        ["current_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "agent_file_space_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_space_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("access_mode", file_access_mode_enum, nullable=False, server_default="read"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_space_id"], ["file_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "agent_id",
            "file_space_id",
            name="uq_agent_file_space_project_agent_space",
        ),
    )
    op.create_index("ix_agent_file_space_links_tenant_id", "agent_file_space_links", ["tenant_id"])
    op.create_index("ix_agent_file_space_links_project_id", "agent_file_space_links", ["project_id"])
    op.create_index("ix_agent_file_space_links_agent_id", "agent_file_space_links", ["agent_id"])
    op.create_index("ix_agent_file_space_links_file_space_id", "agent_file_space_links", ["file_space_id"])
    op.create_index("ix_agent_file_space_links_access_mode", "agent_file_space_links", ["access_mode"])
    op.create_index("ix_agent_file_space_links_created_by", "agent_file_space_links", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_agent_file_space_links_created_by", table_name="agent_file_space_links")
    op.drop_index("ix_agent_file_space_links_access_mode", table_name="agent_file_space_links")
    op.drop_index("ix_agent_file_space_links_file_space_id", table_name="agent_file_space_links")
    op.drop_index("ix_agent_file_space_links_agent_id", table_name="agent_file_space_links")
    op.drop_index("ix_agent_file_space_links_project_id", table_name="agent_file_space_links")
    op.drop_index("ix_agent_file_space_links_tenant_id", table_name="agent_file_space_links")
    op.drop_table("agent_file_space_links")

    op.drop_constraint("fk_file_space_entries_current_revision_id", "file_space_entries", type_="foreignkey")
    op.drop_index("ix_file_entry_revisions_entry_created", table_name="file_entry_revisions")
    op.drop_index("ix_file_entry_revisions_created_by_run_id", table_name="file_entry_revisions")
    op.drop_index("ix_file_entry_revisions_created_by", table_name="file_entry_revisions")
    op.drop_index("ix_file_entry_revisions_sha256", table_name="file_entry_revisions")
    op.drop_index("ix_file_entry_revisions_entry_id", table_name="file_entry_revisions")
    op.drop_table("file_entry_revisions")

    op.drop_index("ix_file_space_entries_space_deleted_path", table_name="file_space_entries")
    op.drop_index("ix_file_space_entries_deleted_at", table_name="file_space_entries")
    op.drop_index("ix_file_space_entries_updated_by", table_name="file_space_entries")
    op.drop_index("ix_file_space_entries_created_by", table_name="file_space_entries")
    op.drop_index("ix_file_space_entries_current_revision_id", table_name="file_space_entries")
    op.drop_index("ix_file_space_entries_entry_type", table_name="file_space_entries")
    op.drop_index("ix_file_space_entries_space_id", table_name="file_space_entries")
    op.drop_table("file_space_entries")

    op.drop_index("ix_file_spaces_status", table_name="file_spaces")
    op.drop_index("ix_file_spaces_project_id", table_name="file_spaces")
    op.drop_index("ix_file_spaces_tenant_id", table_name="file_spaces")
    op.drop_table("file_spaces")

    bind = op.get_bind()
    file_access_mode_enum.drop(bind, checkfirst=True)
    file_entry_type_enum.drop(bind, checkfirst=True)
    file_space_status_enum.drop(bind, checkfirst=True)
