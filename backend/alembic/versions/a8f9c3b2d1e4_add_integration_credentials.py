"""add_integration_credentials

Revision ID: a8f9c3b2d1e4
Revises: 7c9f1c2d3e4f
Create Date: 2026-02-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a8f9c3b2d1e4'
down_revision: Union[str, None] = '7c9f1c2d3e4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    integration_category = postgresql.ENUM(
        'llm_provider',
        'vector_store',
        'artifact_secret',
        'custom',
        name='integrationcredentialcategory',
        create_type=False,
    )
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE integrationcredentialcategory AS ENUM ('llm_provider', 'vector_store', 'artifact_secret', 'custom');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
    )

    if 'integration_credentials' not in inspector.get_table_names():
        op.create_table(
            'integration_credentials',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
            sa.Column('category', integration_category, nullable=False),
            sa.Column('provider_key', sa.String(), nullable=False),
            sa.Column('provider_variant', sa.String(), nullable=True),
            sa.Column('display_name', sa.String(), nullable=False),
            sa.Column('credentials', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    existing_indexes = {idx['name'] for idx in inspector.get_indexes('integration_credentials')} if 'integration_credentials' in inspector.get_table_names() else set()
    if 'ix_integration_credentials_tenant_id' not in existing_indexes:
        op.create_index('ix_integration_credentials_tenant_id', 'integration_credentials', ['tenant_id'], unique=False)
    if 'ix_integration_credentials_provider_key' not in existing_indexes:
        op.create_index('ix_integration_credentials_provider_key', 'integration_credentials', ['provider_key'], unique=False)
    if 'uq_integration_credentials_variant' not in existing_indexes:
        op.create_index(
            'uq_integration_credentials_variant',
            'integration_credentials',
            ['tenant_id', 'category', 'provider_key', 'provider_variant'],
            unique=True,
            postgresql_where=sa.text('provider_variant IS NOT NULL'),
        )
    if 'uq_integration_credentials_no_variant' not in existing_indexes:
        op.create_index(
            'uq_integration_credentials_no_variant',
            'integration_credentials',
            ['tenant_id', 'category', 'provider_key'],
            unique=True,
            postgresql_where=sa.text('provider_variant IS NULL'),
        )

    mpb_columns_info = inspector.get_columns('model_provider_bindings')
    mpb_columns = {col['name'] for col in mpb_columns_info}
    if 'credentials_ref' not in mpb_columns:
        op.add_column('model_provider_bindings', sa.Column('credentials_ref', postgresql.UUID(as_uuid=True), nullable=True))
        mpb_columns_info = inspector.get_columns('model_provider_bindings')
    else:
        for col in mpb_columns_info:
            if col['name'] == 'credentials_ref' and not isinstance(col['type'], postgresql.UUID):
                op.execute("ALTER TABLE model_provider_bindings ALTER COLUMN credentials_ref TYPE UUID USING credentials_ref::uuid")
                break
    mpb_indexes = {idx['name'] for idx in inspector.get_indexes('model_provider_bindings')}
    if 'ix_model_provider_bindings_credentials_ref' not in mpb_indexes:
        op.create_index('ix_model_provider_bindings_credentials_ref', 'model_provider_bindings', ['credentials_ref'], unique=False)
    mpb_fks = {fk['name'] for fk in inspector.get_foreign_keys('model_provider_bindings')}
    if 'model_provider_bindings_credentials_ref_fkey' not in mpb_fks:
        op.create_foreign_key(
            'model_provider_bindings_credentials_ref_fkey',
            'model_provider_bindings',
            'integration_credentials',
            ['credentials_ref'],
            ['id'],
            ondelete='SET NULL',
        )

    ks_columns_info = inspector.get_columns('knowledge_stores')
    ks_columns = {col['name'] for col in ks_columns_info}
    if 'credentials_ref' not in ks_columns:
        op.add_column('knowledge_stores', sa.Column('credentials_ref', postgresql.UUID(as_uuid=True), nullable=True))
        ks_columns_info = inspector.get_columns('knowledge_stores')
    else:
        for col in ks_columns_info:
            if col['name'] == 'credentials_ref' and not isinstance(col['type'], postgresql.UUID):
                op.execute("ALTER TABLE knowledge_stores ALTER COLUMN credentials_ref TYPE UUID USING credentials_ref::uuid")
                break
    ks_indexes = {idx['name'] for idx in inspector.get_indexes('knowledge_stores')}
    if 'ix_knowledge_stores_credentials_ref' not in ks_indexes:
        op.create_index('ix_knowledge_stores_credentials_ref', 'knowledge_stores', ['credentials_ref'], unique=False)
    ks_fks = {fk['name'] for fk in inspector.get_foreign_keys('knowledge_stores')}
    if 'knowledge_stores_credentials_ref_fkey' not in ks_fks:
        op.create_foreign_key(
            'knowledge_stores_credentials_ref_fkey',
            'knowledge_stores',
            'integration_credentials',
            ['credentials_ref'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    op.drop_constraint('knowledge_stores_credentials_ref_fkey', 'knowledge_stores', type_='foreignkey')
    op.drop_index('ix_knowledge_stores_credentials_ref', table_name='knowledge_stores')
    op.drop_column('knowledge_stores', 'credentials_ref')

    op.drop_constraint('model_provider_bindings_credentials_ref_fkey', 'model_provider_bindings', type_='foreignkey')
    op.drop_index('ix_model_provider_bindings_credentials_ref', table_name='model_provider_bindings')
    op.drop_column('model_provider_bindings', 'credentials_ref')

    op.drop_index('uq_integration_credentials_no_variant', table_name='integration_credentials')
    op.drop_index('uq_integration_credentials_variant', table_name='integration_credentials')
    op.drop_index('ix_integration_credentials_provider_key', table_name='integration_credentials')
    op.drop_index('ix_integration_credentials_tenant_id', table_name='integration_credentials')
    op.drop_table('integration_credentials')

    integration_category = sa.Enum(
        'llm_provider',
        'vector_store',
        'artifact_secret',
        'custom',
        name='integrationcredentialcategory',
    )
    integration_category.drop(op.get_bind(), checkfirst=True)
