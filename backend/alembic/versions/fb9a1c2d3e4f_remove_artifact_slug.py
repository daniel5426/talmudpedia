"""remove artifact slug column

Revision ID: fb9a1c2d3e4f
Revises: fc2d3e4f5a6
Create Date: 2026-03-16 20:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "fb9a1c2d3e4f"
down_revision: Union[str, Sequence[str], None] = "fc2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _index_exists(inspector, table_name: str, index_name: str) -> bool:
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_name = "artifacts"
    if _index_exists(inspector, table_name, "uq_artifacts_tenant_slug"):
        op.drop_index("uq_artifacts_tenant_slug", table_name=table_name)
    if _column_exists(inspector, table_name, "slug"):
        op.drop_column(table_name, "slug")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_name = "artifacts"
    if not _column_exists(inspector, table_name, "slug"):
        op.add_column(table_name, sa.Column("slug", sa.String(), nullable=True))
    inspector = inspect(bind)
    if not _index_exists(inspector, table_name, "uq_artifacts_tenant_slug"):
        op.create_index("uq_artifacts_tenant_slug", table_name, ["tenant_id", "slug"], unique=True)
