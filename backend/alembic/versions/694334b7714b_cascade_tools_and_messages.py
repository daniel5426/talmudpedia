"""cascade_tools_and_messages

Revision ID: 694334b7714b
Revises: 98948ff46801
Create Date: 2026-01-14 01:07:29.139528

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '694334b7714b'
down_revision: Union[str, None] = '98948ff46801'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tool Registry - Tenant
    op.drop_constraint('tool_registry_tenant_id_fkey', 'tool_registry', type_='foreignkey')
    op.create_foreign_key('tool_registry_tenant_id_fkey', 'tool_registry', 'tenants', ['tenant_id'], ['id'], ondelete='CASCADE')

    # Tool Versions - Created By (Audit) -> SET NULL
    op.drop_constraint('tool_versions_created_by_fkey', 'tool_versions', type_='foreignkey')
    op.create_foreign_key('tool_versions_created_by_fkey', 'tool_versions', 'users', ['created_by'], ['id'], ondelete='SET NULL')

    # Messages - Chat
    op.drop_constraint('messages_chat_id_fkey', 'messages', type_='foreignkey')
    op.create_foreign_key('messages_chat_id_fkey', 'messages', 'chats', ['chat_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    # Messages
    op.drop_constraint('messages_chat_id_fkey', 'messages', type_='foreignkey')
    op.create_foreign_key('messages_chat_id_fkey', 'messages', 'chats', ['chat_id'], ['id'])

    # Tool Versions
    op.drop_constraint('tool_versions_created_by_fkey', 'tool_versions', type_='foreignkey')
    op.create_foreign_key('tool_versions_created_by_fkey', 'tool_versions', 'users', ['created_by'], ['id'])

    # Tool Registry
    op.drop_constraint('tool_registry_tenant_id_fkey', 'tool_registry', type_='foreignkey')
    op.create_foreign_key('tool_registry_tenant_id_fkey', 'tool_registry', 'tenants', ['tenant_id'], ['id'])
