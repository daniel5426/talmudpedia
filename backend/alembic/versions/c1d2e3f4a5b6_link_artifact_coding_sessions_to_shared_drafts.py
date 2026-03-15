"""link artifact coding sessions to shared drafts

Revision ID: c1d2e3f4a5b6
Revises: ac34ef56ab78
Create Date: 2026-03-14 21:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "ac34ef56ab78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _index_exists(inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def _foreign_key_exists(inspector, table_name: str, constraint_name: str) -> bool:
    return any(fk.get("name") == constraint_name for fk in inspector.get_foreign_keys(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _table_has_column(inspector, "artifact_coding_sessions", "shared_draft_id"):
        op.add_column(
            "artifact_coding_sessions",
            sa.Column("shared_draft_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    inspector = inspect(bind)
    if not _index_exists(inspector, "artifact_coding_sessions", "ix_artifact_coding_sessions_shared_draft_id"):
        op.create_index(
            "ix_artifact_coding_sessions_shared_draft_id",
            "artifact_coding_sessions",
            ["shared_draft_id"],
            unique=False,
        )

    inspector = inspect(bind)
    if not _foreign_key_exists(
        inspector,
        "artifact_coding_sessions",
        "fk_artifact_coding_sessions_shared_draft_id",
    ):
        op.create_foreign_key(
            "fk_artifact_coding_sessions_shared_draft_id",
            "artifact_coding_sessions",
            "artifact_coding_shared_drafts",
            ["shared_draft_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    bind.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT DISTINCT ON (session_id)
                    session_id,
                    shared_draft_id
                FROM artifact_coding_run_snapshots
                WHERE session_id IS NOT NULL
                ORDER BY session_id, created_at DESC, id DESC
            )
            UPDATE artifact_coding_sessions AS sessions
            SET shared_draft_id = ranked.shared_draft_id
            FROM ranked
            WHERE sessions.id = ranked.session_id
              AND sessions.shared_draft_id IS NULL
            """
        )
    )

    bind.execute(
        sa.text(
            """
            UPDATE artifact_coding_sessions AS sessions
            SET shared_draft_id = drafts.id
            FROM artifact_coding_shared_drafts AS drafts
            WHERE sessions.shared_draft_id IS NULL
              AND sessions.tenant_id = drafts.tenant_id
              AND (
                    (sessions.artifact_id IS NOT NULL AND drafts.artifact_id = sessions.artifact_id)
                 OR (sessions.linked_artifact_id IS NOT NULL AND drafts.linked_artifact_id = sessions.linked_artifact_id)
                 OR (sessions.draft_key IS NOT NULL AND drafts.draft_key = sessions.draft_key)
              )
            """
        )
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO artifact_coding_shared_drafts (
                id,
                tenant_id,
                artifact_id,
                draft_key,
                linked_artifact_id,
                linked_at,
                working_draft_snapshot,
                last_test_run_id,
                last_run_id,
                created_at,
                updated_at
            )
            SELECT
                gen_random_uuid(),
                sessions.tenant_id,
                sessions.artifact_id,
                sessions.draft_key,
                sessions.linked_artifact_id,
                sessions.linked_at,
                '{}'::jsonb,
                NULL,
                sessions.last_run_id,
                now(),
                now()
            FROM artifact_coding_sessions AS sessions
            WHERE sessions.shared_draft_id IS NULL
            """
        )
    )

    bind.execute(
        sa.text(
            """
            UPDATE artifact_coding_sessions AS sessions
            SET shared_draft_id = drafts.id
            FROM artifact_coding_shared_drafts AS drafts
            WHERE sessions.shared_draft_id IS NULL
              AND sessions.tenant_id = drafts.tenant_id
              AND sessions.last_run_id IS NOT DISTINCT FROM drafts.last_run_id
              AND sessions.artifact_id IS NOT DISTINCT FROM drafts.artifact_id
              AND sessions.linked_artifact_id IS NOT DISTINCT FROM drafts.linked_artifact_id
              AND sessions.draft_key IS NOT DISTINCT FROM drafts.draft_key
            """
        )
    )

    op.alter_column(
        "artifact_coding_sessions",
        "shared_draft_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _foreign_key_exists(
        inspector,
        "artifact_coding_sessions",
        "fk_artifact_coding_sessions_shared_draft_id",
    ):
        op.drop_constraint(
            "fk_artifact_coding_sessions_shared_draft_id",
            "artifact_coding_sessions",
            type_="foreignkey",
        )

    inspector = inspect(bind)
    if _index_exists(inspector, "artifact_coding_sessions", "ix_artifact_coding_sessions_shared_draft_id"):
        op.drop_index("ix_artifact_coding_sessions_shared_draft_id", table_name="artifact_coding_sessions")

    inspector = inspect(bind)
    if _table_has_column(inspector, "artifact_coding_sessions", "shared_draft_id"):
        op.drop_column("artifact_coding_sessions", "shared_draft_id")
