"""add publish job stage and heartbeat fields

Revision ID: a4b5c6d7e8f9
Revises: f9b4e1c2d3a6
Create Date: 2026-02-26 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "f9b4e1c2d3a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "published_app_publish_jobs" not in inspector.get_table_names():
        return

    if not _table_has_column(inspector, "published_app_publish_jobs", "stage"):
        op.add_column("published_app_publish_jobs", sa.Column("stage", sa.String(length=64), nullable=True))
    inspector = sa.inspect(bind)
    if not _table_has_column(inspector, "published_app_publish_jobs", "last_heartbeat_at"):
        op.add_column(
            "published_app_publish_jobs",
            sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "published_app_publish_jobs" not in inspector.get_table_names():
        return
    if _table_has_column(inspector, "published_app_publish_jobs", "last_heartbeat_at"):
        op.drop_column("published_app_publish_jobs", "last_heartbeat_at")
    inspector = sa.inspect(bind)
    if _table_has_column(inspector, "published_app_publish_jobs", "stage"):
        op.drop_column("published_app_publish_jobs", "stage")

