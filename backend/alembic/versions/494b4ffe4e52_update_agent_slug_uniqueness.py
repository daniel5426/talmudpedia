"""update_agent_slug_uniqueness

Revision ID: 494b4ffe4e52
Revises: fad169b1b128
Create Date: 2026-01-18 22:39:46.906821

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '494b4ffe4e52'
down_revision: Union[str, None] = 'fad169b1b128'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the global unique index
    op.drop_index('ix_agents_slug', table_name='agents')
    
    # Add the per-tenant unique constraint
    op.create_unique_constraint('uq_agent_tenant_slug', 'agents', ['tenant_id', 'slug'])
    
    # Re-create the index on slug as non-unique for performance
    op.create_index('ix_agents_slug', 'agents', ['slug'], unique=False)


def downgrade() -> None:
    # Drop the non-unique index
    op.drop_index('ix_agents_slug', table_name='agents')
    
    # Drop the per-tenant unique constraint
    op.drop_constraint('uq_agent_tenant_slug', 'agents', type_='unique')
    
    # Re-create the global unique index
    op.create_index('ix_agents_slug', 'agents', ['slug'], unique=True)
