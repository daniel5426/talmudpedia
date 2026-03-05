"""hard cut versions metadata and run fields

Revision ID: b8d1e2f3a4b5
Revises: 6a1d4e9b2c7f, a4b5c6d7e8f9
Create Date: 2026-03-01 03:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b8d1e2f3a4b5"
down_revision: Union[str, Sequence[str], None] = ("6a1d4e9b2c7f", "a4b5c6d7e8f9")
branch_labels = None
depends_on = None


def _table_has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _index_exists(inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def _unique_constraint_exists(inspector, table_name: str, constraint_name: str) -> bool:
    return any(constraint.get("name") == constraint_name for constraint in inspector.get_unique_constraints(table_name))


def _drop_fk_for_column(table_name: str, column_name: str) -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for fk in inspector.get_foreign_keys(table_name):
        constrained = fk.get("constrained_columns") or []
        if column_name in constrained and fk.get("name"):
            op.drop_constraint(fk["name"], table_name, type_="foreignkey")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _table_has_column(inspector, "published_app_revisions", "version_seq"):
        op.add_column("published_app_revisions", sa.Column("version_seq", sa.BigInteger(), nullable=True))
    if not _table_has_column(inspector, "published_app_revisions", "origin_kind"):
        op.add_column("published_app_revisions", sa.Column("origin_kind", sa.String(length=32), nullable=True))
    if not _table_has_column(inspector, "published_app_revisions", "origin_run_id"):
        op.add_column("published_app_revisions", sa.Column("origin_run_id", postgresql.UUID(as_uuid=True), nullable=True))
    if not _table_has_column(inspector, "published_app_revisions", "restored_from_revision_id"):
        op.add_column(
            "published_app_revisions",
            sa.Column("restored_from_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    bind.execute(
        sa.text(
            """
            UPDATE published_app_revisions
            SET origin_kind = CASE
                WHEN kind::text = 'published' THEN 'publish_output'
                ELSE 'unknown'
            END
            WHERE origin_kind IS NULL OR origin_kind = ''
            """
        )
    )

    bind.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY published_app_id
                           ORDER BY created_at ASC, id ASC
                       ) AS seq
                FROM published_app_revisions
            )
            UPDATE published_app_revisions p
            SET version_seq = ranked.seq
            FROM ranked
            WHERE p.id = ranked.id
              AND p.version_seq IS NULL
            """
        )
    )

    op.alter_column("published_app_revisions", "origin_kind", existing_type=sa.String(length=32), nullable=False)
    op.alter_column("published_app_revisions", "version_seq", existing_type=sa.BigInteger(), nullable=False)

    inspector = inspect(bind)
    if not any(fk.get("name") == "fk_published_app_revisions_origin_run_id" for fk in inspector.get_foreign_keys("published_app_revisions")):
        op.create_foreign_key(
            "fk_published_app_revisions_origin_run_id",
            "published_app_revisions",
            "agent_runs",
            ["origin_run_id"],
            ["id"],
            ondelete="SET NULL",
        )

    inspector = inspect(bind)
    if not any(
        fk.get("name") == "fk_published_app_revisions_restored_from_revision_id"
        for fk in inspector.get_foreign_keys("published_app_revisions")
    ):
        op.create_foreign_key(
            "fk_published_app_revisions_restored_from_revision_id",
            "published_app_revisions",
            "published_app_revisions",
            ["restored_from_revision_id"],
            ["id"],
            ondelete="SET NULL",
        )

    inspector = inspect(bind)
    if not _index_exists(inspector, "published_app_revisions", "ix_published_app_revisions_origin_kind"):
        op.create_index("ix_published_app_revisions_origin_kind", "published_app_revisions", ["origin_kind"], unique=False)
    if not _index_exists(inspector, "published_app_revisions", "ix_published_app_revisions_origin_run_id"):
        op.create_index("ix_published_app_revisions_origin_run_id", "published_app_revisions", ["origin_run_id"], unique=False)
    if not _index_exists(inspector, "published_app_revisions", "ix_published_app_revisions_restored_from_revision_id"):
        op.create_index(
            "ix_published_app_revisions_restored_from_revision_id",
            "published_app_revisions",
            ["restored_from_revision_id"],
            unique=False,
        )
    if not _index_exists(inspector, "published_app_revisions", "ix_published_app_revisions_app_created_at_desc"):
        op.create_index(
            "ix_published_app_revisions_app_created_at_desc",
            "published_app_revisions",
            ["published_app_id", sa.text("created_at DESC")],
            unique=False,
        )
    if not _unique_constraint_exists(inspector, "published_app_revisions", "uq_published_app_revisions_app_version_seq"):
        op.create_unique_constraint(
            "uq_published_app_revisions_app_version_seq",
            "published_app_revisions",
            ["published_app_id", "version_seq"],
        )

    inspector = inspect(bind)
    if _table_has_column(inspector, "agent_runs", "checkpoint_revision_id"):
        if _index_exists(inspector, "agent_runs", "ix_agent_runs_checkpoint_revision_id"):
            op.drop_index("ix_agent_runs_checkpoint_revision_id", table_name="agent_runs")
        _drop_fk_for_column("agent_runs", "checkpoint_revision_id")
        op.drop_column("agent_runs", "checkpoint_revision_id")

    inspector = inspect(bind)
    if _table_has_column(inspector, "agent_runs", "batch_owner"):
        op.drop_column("agent_runs", "batch_owner")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _table_has_column(inspector, "agent_runs", "batch_owner"):
        op.add_column(
            "agent_runs",
            sa.Column("batch_owner", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )

    inspector = inspect(bind)
    if not _table_has_column(inspector, "agent_runs", "checkpoint_revision_id"):
        op.add_column("agent_runs", sa.Column("checkpoint_revision_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            "fk_agent_runs_checkpoint_revision_id",
            "agent_runs",
            "published_app_revisions",
            ["checkpoint_revision_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index("ix_agent_runs_checkpoint_revision_id", "agent_runs", ["checkpoint_revision_id"], unique=False)

    inspector = inspect(bind)
    if _unique_constraint_exists(inspector, "published_app_revisions", "uq_published_app_revisions_app_version_seq"):
        op.drop_constraint("uq_published_app_revisions_app_version_seq", "published_app_revisions", type_="unique")
    if _index_exists(inspector, "published_app_revisions", "ix_published_app_revisions_app_created_at_desc"):
        op.drop_index("ix_published_app_revisions_app_created_at_desc", table_name="published_app_revisions")
    if _index_exists(inspector, "published_app_revisions", "ix_published_app_revisions_restored_from_revision_id"):
        op.drop_index("ix_published_app_revisions_restored_from_revision_id", table_name="published_app_revisions")
    if _index_exists(inspector, "published_app_revisions", "ix_published_app_revisions_origin_run_id"):
        op.drop_index("ix_published_app_revisions_origin_run_id", table_name="published_app_revisions")
    if _index_exists(inspector, "published_app_revisions", "ix_published_app_revisions_origin_kind"):
        op.drop_index("ix_published_app_revisions_origin_kind", table_name="published_app_revisions")

    _drop_fk_for_column("published_app_revisions", "restored_from_revision_id")
    _drop_fk_for_column("published_app_revisions", "origin_run_id")

    inspector = inspect(bind)
    if _table_has_column(inspector, "published_app_revisions", "restored_from_revision_id"):
        op.drop_column("published_app_revisions", "restored_from_revision_id")
    if _table_has_column(inspector, "published_app_revisions", "origin_run_id"):
        op.drop_column("published_app_revisions", "origin_run_id")
    if _table_has_column(inspector, "published_app_revisions", "origin_kind"):
        op.drop_column("published_app_revisions", "origin_kind")
    if _table_has_column(inspector, "published_app_revisions", "version_seq"):
        op.drop_column("published_app_revisions", "version_seq")
