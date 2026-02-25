"""add chat history reverse paging index

Revision ID: a1c4d9e8f7b6
Revises: f9b4e1c2d3a6
Create Date: 2026-02-25 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1c4d9e8f7b6"
down_revision: Union[str, Sequence[str], None] = "f9b4e1c2d3a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "published_app_coding_chat_messages" not in inspector.get_table_names():
        return

    index_name = "ix_pacm_session_created_id_desc"
    if not _index_exists(inspector, "published_app_coding_chat_messages", index_name):
        op.create_index(
            index_name,
            "published_app_coding_chat_messages",
            ["session_id", sa.text("created_at DESC"), sa.text("id DESC")],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "published_app_coding_chat_messages" not in inspector.get_table_names():
        return

    index_name = "ix_pacm_session_created_id_desc"
    if _index_exists(inspector, "published_app_coding_chat_messages", index_name):
        op.drop_index(index_name, table_name="published_app_coding_chat_messages")
