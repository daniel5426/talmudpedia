"""add_on_delete_cascade_to_chats_user_id

Revision ID: 999c908e4fce
Revises: 2891b6fde332
Create Date: 2026-01-14 00:34:52.104492

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '999c908e4fce'
down_revision: Union[str, None] = '2891b6fde332'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('chats_user_id_fkey', 'chats', type_='foreignkey')
    op.create_foreign_key('chats_user_id_fkey', 'chats', 'users', ['user_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    op.drop_constraint('chats_user_id_fkey', 'chats', type_='foreignkey')
    op.create_foreign_key('chats_user_id_fkey', 'chats', 'users', ['user_id'], ['id'])
