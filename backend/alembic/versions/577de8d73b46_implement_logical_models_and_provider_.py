"""implement_logical_models_and_provider_bindings

Revision ID: 577de8d73b46
Revises: 494b4ffe4e52
Create Date: 2026-01-18 22:49:47.267396

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '577de8d73b46'
down_revision: Union[str, None] = '494b4ffe4e52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0. Handle Enum updates (must happen outside transaction block usually, or be careful)
    # We use autocommit block for ADD VALUE to be safe
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE modelprovidertype ADD VALUE IF NOT EXISTS 'GEMINI'")
        op.execute("ALTER TYPE modelprovidertype ADD VALUE IF NOT EXISTS 'HUGGINGFACE'")
        op.execute("ALTER TYPE modelprovidertype ADD VALUE IF NOT EXISTS 'LOCAL'")
        op.execute("ALTER TYPE modelprovidertype ADD VALUE IF NOT EXISTS 'COHERE'")
        op.execute("ALTER TYPE modelprovidertype ADD VALUE IF NOT EXISTS 'GROQ'")
        op.execute("ALTER TYPE modelprovidertype ADD VALUE IF NOT EXISTS 'MISTRAL'")
        op.execute("ALTER TYPE modelprovidertype ADD VALUE IF NOT EXISTS 'TOGETHER'")

    # 1. Create new Enum types manually
    op.execute("DO $$ BEGIN CREATE TYPE modelcapabilitytype AS ENUM ('CHAT', 'COMPLETION', 'EMBEDDING', 'VISION', 'AUDIO', 'SPEECH_TO_TEXT', 'TEXT_TO_SPEECH', 'IMAGE', 'RERANK'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE modelstatus AS ENUM ('ACTIVE', 'DEPRECATED', 'DISABLED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;")

    # 2. Create model_provider_bindings table
    op.create_table('model_provider_bindings',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('model_id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=True),
    # Use postgresql.ENUM with create_type=False to avoid re-creation
    sa.Column('provider', postgresql.ENUM('OPENAI', 'ANTHROPIC', 'GOOGLE', 'AZURE', 'GEMINI', 'HUGGINGFACE', 'LOCAL', 'COHERE', 'GROQ', 'MISTRAL', 'TOGETHER', 'CUSTOM', name='modelprovidertype', create_type=False), nullable=False),
    sa.Column('provider_model_id', sa.String(), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('is_enabled', sa.Boolean(), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('credentials_ref', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['model_id'], ['model_registry.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_model_provider_bindings_model_id'), 'model_provider_bindings', ['model_id'], unique=False)
    op.create_index(op.f('ix_model_provider_bindings_tenant_id'), 'model_provider_bindings', ['tenant_id'], unique=False)

    # 3. Update model_registry
    op.execute("TRUNCATE TABLE model_registry CASCADE")

    op.add_column('model_registry', sa.Column('slug', sa.String(), nullable=False))
    op.add_column('model_registry', sa.Column('description', sa.String(), nullable=True))
    
    # Use postgresql.ENUM with create_type=False
    op.add_column('model_registry', sa.Column('capability_type', postgresql.ENUM('CHAT', 'COMPLETION', 'EMBEDDING', 'VISION', 'AUDIO', 'SPEECH_TO_TEXT', 'TEXT_TO_SPEECH', 'IMAGE', 'RERANK', name='modelcapabilitytype', create_type=False), nullable=False))
    op.add_column('model_registry', sa.Column('status', postgresql.ENUM('ACTIVE', 'DEPRECATED', 'DISABLED', name='modelstatus', create_type=False), nullable=False))
    
    op.add_column('model_registry', sa.Column('default_resolution_policy', postgresql.JSONB(astext_type=sa.Text()), nullable=False))
    op.add_column('model_registry', sa.Column('version', sa.Integer(), nullable=False))
    
    # Changing provider to nullable
    op.alter_column('model_registry', 'provider',
               existing_type=postgresql.ENUM('OPENAI', 'ANTHROPIC', 'GOOGLE', 'AZURE', 'CUSTOM', name='modelprovidertype'),
               nullable=True)
               
    op.create_index(op.f('ix_model_registry_slug'), 'model_registry', ['slug'], unique=False)
    op.drop_column('model_registry', 'display_name')


def downgrade() -> None:
    # This downgrade is destructive as we loose new data and structure
    op.add_column('model_registry', sa.Column('display_name', sa.VARCHAR(), autoincrement=False, nullable=True))
    op.drop_index(op.f('ix_model_registry_slug'), table_name='model_registry')
    
    op.execute("TRUNCATE TABLE model_registry CASCADE")
    
    op.alter_column('model_registry', 'provider',
               existing_type=postgresql.ENUM('OPENAI', 'ANTHROPIC', 'GOOGLE', 'AZURE', 'CUSTOM', name='modelprovidertype'),
               nullable=False)
               
    op.drop_column('model_registry', 'version')
    op.drop_column('model_registry', 'default_resolution_policy')
    op.drop_column('model_registry', 'status')
    op.drop_column('model_registry', 'capability_type')
    op.drop_column('model_registry', 'description')
    op.drop_column('model_registry', 'slug')
    
    op.drop_index(op.f('ix_model_provider_bindings_tenant_id'), table_name='model_provider_bindings')
    op.drop_index(op.f('ix_model_provider_bindings_model_id'), table_name='model_provider_bindings')
    op.drop_table('model_provider_bindings')
    
    op.execute("DROP TYPE IF EXISTS modelcapabilitytype")
    op.execute("DROP TYPE IF EXISTS modelstatus")
