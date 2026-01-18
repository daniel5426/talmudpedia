"""add cascade delete to chats and messages

Revision ID: fad169b1b128
Revises: 57f3b4a27d0e
Create Date: 2026-01-18 22:32:34.696304

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fad169b1b128'
down_revision: Union[str, None] = '57f3b4a27d0e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Chats
    op.drop_constraint('chats_user_id_fkey', 'chats', type_='foreignkey')
    op.create_foreign_key('chats_user_id_fkey', 'chats', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    
    op.drop_constraint('chats_tenant_id_fkey', 'chats', type_='foreignkey')
    op.create_foreign_key('chats_tenant_id_fkey', 'chats', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    # Messages
    op.drop_constraint('messages_chat_id_fkey', 'messages', type_='foreignkey')
    op.create_foreign_key('messages_chat_id_fkey', 'messages', 'chats', ['chat_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    # Messages
    op.drop_constraint('messages_chat_id_fkey', 'messages', type_='foreignkey')
    op.create_foreign_key('messages_chat_id_fkey', 'messages', 'chats', ['chat_id'], ['id'])

    # Chats
    op.drop_constraint('chats_tenant_id_fkey', 'chats', type_='foreignkey')
    op.create_foreign_key('chats_tenant_id_fkey', 'chats', 'tenants', ['tenant_id'], ['id'])

    op.drop_constraint('chats_user_id_fkey', 'chats', type_='foreignkey')
    op.create_foreign_key('chats_user_id_fkey', 'chats', 'users', ['user_id'], ['id'])
