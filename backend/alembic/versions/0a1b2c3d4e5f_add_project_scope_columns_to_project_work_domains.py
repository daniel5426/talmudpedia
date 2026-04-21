"""add project scope columns to project work domains

Revision ID: a0b1c2d3e4f5
Revises: e2f3a4b5c6d7
Create Date: 2026-04-21 15:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a0b1c2d3e4f5"
down_revision: str | None = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def _add_project_fk(batch_op, table_name: str) -> None:
    batch_op.add_column(sa.Column("project_id", sa.UUID(), nullable=True))
    batch_op.create_foreign_key(
        f"fk_{table_name}_project_id_projects",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    batch_op.create_index(f"ix_{table_name}_project_id", ["project_id"], unique=False)


def _drop_project_fk(batch_op, table_name: str) -> None:
    batch_op.drop_index(f"ix_{table_name}_project_id")
    batch_op.drop_constraint(f"fk_{table_name}_project_id_projects", type_="foreignkey")
    batch_op.drop_column("project_id")


def upgrade() -> None:
    for table_name in (
        "agents",
        "agent_runs",
        "agent_threads",
        "prompt_library",
        "tool_registry",
        "knowledge_stores",
        "visual_pipelines",
        "executable_pipelines",
        "pipeline_jobs",
        "artifacts",
        "artifact_runs",
        "runtime_attachments",
        "published_apps",
        "published_app_draft_workspaces",
        "published_app_draft_dev_sessions",
        "published_app_publish_jobs",
    ):
        with op.batch_alter_table(table_name) as batch_op:
            _add_project_fk(batch_op, table_name)

    with op.batch_alter_table("published_apps") as batch_op:
        batch_op.drop_constraint("uq_published_apps_tenant_name", type_="unique")
        batch_op.create_unique_constraint(
            "uq_published_apps_project_name",
            ["organization_id", "project_id", "name"],
        )

    op.drop_index("ix_agent_threads_scope_activity", table_name="agent_threads")
    op.drop_index("ix_agent_threads_app_account_activity", table_name="agent_threads")
    op.drop_index("ix_agent_threads_embed_activity", table_name="agent_threads")
    op.drop_index("ix_runtime_attachments_scope_lookup", table_name="runtime_attachments")
    op.drop_index("ix_runtime_attachments_embed_lookup", table_name="runtime_attachments")

    op.create_index(
        "ix_agent_threads_scope_activity",
        "agent_threads",
        ["organization_id", "project_id", "user_id", "last_activity_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_threads_app_account_activity",
        "agent_threads",
        ["organization_id", "project_id", "app_account_id", "last_activity_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_threads_embed_activity",
        "agent_threads",
        ["organization_id", "project_id", "agent_id", "external_user_id", "last_activity_at"],
        unique=False,
    )
    op.create_index(
        "ix_runtime_attachments_scope_lookup",
        "runtime_attachments",
        ["organization_id", "project_id", "surface", "thread_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_runtime_attachments_embed_lookup",
        "runtime_attachments",
        ["organization_id", "project_id", "agent_id", "external_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_prompt_library_project_name",
        "prompt_library",
        ["organization_id", "project_id", "name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_prompt_library_project_name", table_name="prompt_library")
    op.drop_index("ix_runtime_attachments_embed_lookup", table_name="runtime_attachments")
    op.drop_index("ix_runtime_attachments_scope_lookup", table_name="runtime_attachments")
    op.drop_index("ix_agent_threads_embed_activity", table_name="agent_threads")
    op.drop_index("ix_agent_threads_app_account_activity", table_name="agent_threads")
    op.drop_index("ix_agent_threads_scope_activity", table_name="agent_threads")
    op.create_index(
        "ix_runtime_attachments_scope_lookup",
        "runtime_attachments",
        ["organization_id", "surface", "thread_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_runtime_attachments_embed_lookup",
        "runtime_attachments",
        ["organization_id", "agent_id", "external_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_threads_scope_activity",
        "agent_threads",
        ["organization_id", "user_id", "last_activity_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_threads_app_account_activity",
        "agent_threads",
        ["organization_id", "app_account_id", "last_activity_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_threads_embed_activity",
        "agent_threads",
        ["organization_id", "agent_id", "external_user_id", "last_activity_at"],
        unique=False,
    )

    with op.batch_alter_table("published_apps") as batch_op:
        batch_op.drop_constraint("uq_published_apps_project_name", type_="unique")
        batch_op.create_unique_constraint(
            "uq_published_apps_tenant_name",
            ["organization_id", "name"],
        )

    for table_name in reversed(
        (
            "agents",
            "agent_runs",
            "agent_threads",
            "prompt_library",
            "tool_registry",
            "knowledge_stores",
            "visual_pipelines",
            "executable_pipelines",
            "pipeline_jobs",
            "artifacts",
            "artifact_runs",
            "runtime_attachments",
            "published_apps",
            "published_app_draft_workspaces",
            "published_app_draft_dev_sessions",
            "published_app_publish_jobs",
        )
    ):
        with op.batch_alter_table(table_name) as batch_op:
            _drop_project_fk(batch_op, table_name)
