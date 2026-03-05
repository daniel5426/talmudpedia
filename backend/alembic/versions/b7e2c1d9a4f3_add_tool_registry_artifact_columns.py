"""add missing tool_registry artifact columns

Revision ID: b7e2c1d9a4f3
Revises: a1c4d9e8f7b6
Create Date: 2026-02-25 23:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7e2c1d9a4f3"
down_revision: Union[str, Sequence[str], None] = "a1c4d9e8f7b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    table_name = "tool_registry"
    if table_name not in inspector.get_table_names():
        return

    if not _column_exists(inspector, table_name, "artifact_id"):
        op.add_column(table_name, sa.Column("artifact_id", sa.String(), nullable=True))

    if not _column_exists(inspector, table_name, "artifact_version"):
        op.add_column(table_name, sa.Column("artifact_version", sa.String(), nullable=True))

    inspector = sa.inspect(bind)
    index_name = "ix_tool_registry_artifact_id"
    if _column_exists(inspector, table_name, "artifact_id") and not _index_exists(inspector, table_name, index_name):
        op.create_index(index_name, table_name, ["artifact_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    table_name = "tool_registry"
    if table_name not in inspector.get_table_names():
        return

    index_name = "ix_tool_registry_artifact_id"
    if _index_exists(inspector, table_name, index_name):
        op.drop_index(index_name, table_name=table_name)

    inspector = sa.inspect(bind)
    if _column_exists(inspector, table_name, "artifact_version"):
        op.drop_column(table_name, "artifact_version")
    if _column_exists(inspector, table_name, "artifact_id"):
        op.drop_column(table_name, "artifact_id")
