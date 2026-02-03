"""add unique constraints to model registry

Revision ID: bb55ce1e499a
Revises: f7a2d3e4b5c6
Create Date: 2026-02-01 22:06:16.240517

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb55ce1e499a'
down_revision: Union[str, None] = 'f7a2d3e4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ModelRegistry partial indexes
    op.create_index('uq_model_registry_slug_tenant', 'model_registry', ['slug', 'tenant_id'], unique=True, postgresql_where=sa.text('tenant_id IS NOT NULL'))
    op.create_index('uq_model_registry_slug_global', 'model_registry', ['slug'], unique=True, postgresql_where=sa.text('tenant_id IS NULL'))

    # ModelProviderBinding partial indexes
    op.create_index('uq_model_binding_tenant', 'model_provider_bindings', ['model_id', 'provider', 'provider_model_id', 'tenant_id'], unique=True, postgresql_where=sa.text('tenant_id IS NOT NULL'))
    op.create_index('uq_model_binding_global', 'model_provider_bindings', ['model_id', 'provider', 'provider_model_id'], unique=True, postgresql_where=sa.text('tenant_id IS NULL'))


def downgrade() -> None:
    op.drop_index('uq_model_binding_global', table_name='model_provider_bindings')
    op.drop_index('uq_model_binding_tenant', table_name='model_provider_bindings')
    op.drop_index('uq_model_registry_slug_global', table_name='model_registry')
    op.drop_index('uq_model_registry_slug_tenant', table_name='model_registry')
