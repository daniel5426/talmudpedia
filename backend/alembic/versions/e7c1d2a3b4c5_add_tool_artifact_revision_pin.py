"""add tool artifact revision pin

Revision ID: e7c1d2a3b4c5
Revises: d6f7a8b9c0d1
Create Date: 2026-03-10 21:20:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e7c1d2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "d6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        return {col["name"] for col in inspector.get_columns(table_name)}
    except Exception:
        return set()


def _foreign_key_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        return {fk["name"] for fk in inspector.get_foreign_keys(table_name) if fk.get("name")}
    except Exception:
        return set()


def upgrade() -> None:
    columns = _column_names("tool_registry")
    if "artifact_revision_id" not in columns:
        op.add_column(
            "tool_registry",
            sa.Column("artifact_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_index(
            "ix_tool_registry_artifact_revision_id",
            "tool_registry",
            ["artifact_revision_id"],
            unique=False,
        )

    fk_names = _foreign_key_names("tool_registry")
    if "fk_tool_registry_artifact_revision_id" not in fk_names:
        op.create_foreign_key(
            "fk_tool_registry_artifact_revision_id",
            "tool_registry",
            "artifact_revisions",
            ["artifact_revision_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    fk_names = _foreign_key_names("tool_registry")
    if "fk_tool_registry_artifact_revision_id" in fk_names:
        op.drop_constraint("fk_tool_registry_artifact_revision_id", "tool_registry", type_="foreignkey")

    columns = _column_names("tool_registry")
    if "artifact_revision_id" in columns:
        op.drop_index("ix_tool_registry_artifact_revision_id", table_name="tool_registry")
        op.drop_column("tool_registry", "artifact_revision_id")
