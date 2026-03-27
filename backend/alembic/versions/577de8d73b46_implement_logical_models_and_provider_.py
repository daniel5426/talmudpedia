"""implement_logical_models_and_provider_bindings

Revision ID: 577de8d73b46
Revises: 494b4ffe4e52
Create Date: 2026-01-18 22:49:47.267396

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '577de8d73b46'
down_revision: Union[str, None] = '494b4ffe4e52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

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

    existing_tables = set(inspector.get_table_names())

    # 2. Create model_provider_bindings table
    if 'model_provider_bindings' not in existing_tables:
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

    provider_binding_indexes = {
        index["name"] for index in inspect(bind).get_indexes("model_provider_bindings")
    }
    if op.f('ix_model_provider_bindings_model_id') not in provider_binding_indexes:
        op.create_index(op.f('ix_model_provider_bindings_model_id'), 'model_provider_bindings', ['model_id'], unique=False)
    if op.f('ix_model_provider_bindings_tenant_id') not in provider_binding_indexes:
        op.create_index(op.f('ix_model_provider_bindings_tenant_id'), 'model_provider_bindings', ['tenant_id'], unique=False)

    # 3. Update model_registry
    op.execute("TRUNCATE TABLE model_registry CASCADE")

    model_registry_columns = {
        column["name"] for column in inspect(bind).get_columns("model_registry")
    }

    if 'slug' not in model_registry_columns:
        op.add_column('model_registry', sa.Column('slug', sa.String(), nullable=False))
    if 'description' not in model_registry_columns:
        op.add_column('model_registry', sa.Column('description', sa.String(), nullable=True))
    
    # Use postgresql.ENUM with create_type=False
    if 'capability_type' not in model_registry_columns:
        op.add_column('model_registry', sa.Column('capability_type', postgresql.ENUM('CHAT', 'COMPLETION', 'EMBEDDING', 'VISION', 'AUDIO', 'SPEECH_TO_TEXT', 'TEXT_TO_SPEECH', 'IMAGE', 'RERANK', name='modelcapabilitytype', create_type=False), nullable=False))
    if 'status' not in model_registry_columns:
        op.add_column('model_registry', sa.Column('status', postgresql.ENUM('ACTIVE', 'DEPRECATED', 'DISABLED', name='modelstatus', create_type=False), nullable=False))
    
    if 'default_resolution_policy' not in model_registry_columns:
        op.add_column('model_registry', sa.Column('default_resolution_policy', postgresql.JSONB(astext_type=sa.Text()), nullable=False))
    if 'version' not in model_registry_columns:
        op.add_column('model_registry', sa.Column('version', sa.Integer(), nullable=False))
    
    # Changing provider to nullable
    if 'provider' in model_registry_columns:
        op.alter_column('model_registry', 'provider',
                   existing_type=postgresql.ENUM('OPENAI', 'ANTHROPIC', 'GOOGLE', 'AZURE', 'CUSTOM', name='modelprovidertype'),
                   nullable=True)
               
    model_registry_indexes = {index["name"] for index in inspect(bind).get_indexes("model_registry")}
    if op.f('ix_model_registry_slug') not in model_registry_indexes:
        op.create_index(op.f('ix_model_registry_slug'), 'model_registry', ['slug'], unique=False)

    model_registry_columns = {
        column["name"] for column in inspect(bind).get_columns("model_registry")
    }
    if 'display_name' in model_registry_columns:
        op.drop_column('model_registry', 'display_name')


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # This downgrade is destructive as we loose new data and structure
    model_registry_columns = {
        column["name"] for column in inspector.get_columns("model_registry")
    }
    model_registry_indexes = {
        index["name"] for index in inspector.get_indexes("model_registry")
    }

    if 'display_name' not in model_registry_columns:
        op.add_column('model_registry', sa.Column('display_name', sa.VARCHAR(), autoincrement=False, nullable=True))
    if op.f('ix_model_registry_slug') in model_registry_indexes:
        op.drop_index(op.f('ix_model_registry_slug'), table_name='model_registry')
    
    op.execute("TRUNCATE TABLE model_registry CASCADE")
    
    if 'provider' in model_registry_columns:
        op.alter_column('model_registry', 'provider',
                   existing_type=postgresql.ENUM('OPENAI', 'ANTHROPIC', 'GOOGLE', 'AZURE', 'CUSTOM', name='modelprovidertype'),
                   nullable=False)
               
    model_registry_columns = {
        column["name"] for column in inspect(bind).get_columns("model_registry")
    }
    if 'version' in model_registry_columns:
        op.drop_column('model_registry', 'version')
    if 'default_resolution_policy' in model_registry_columns:
        op.drop_column('model_registry', 'default_resolution_policy')
    if 'status' in model_registry_columns:
        op.drop_column('model_registry', 'status')
    if 'capability_type' in model_registry_columns:
        op.drop_column('model_registry', 'capability_type')
    if 'description' in model_registry_columns:
        op.drop_column('model_registry', 'description')
    if 'slug' in model_registry_columns:
        op.drop_column('model_registry', 'slug')
    
    existing_tables = set(inspect(bind).get_table_names())
    if 'model_provider_bindings' in existing_tables:
        provider_binding_indexes = {
            index["name"] for index in inspect(bind).get_indexes("model_provider_bindings")
        }
        if op.f('ix_model_provider_bindings_tenant_id') in provider_binding_indexes:
            op.drop_index(op.f('ix_model_provider_bindings_tenant_id'), table_name='model_provider_bindings')
        if op.f('ix_model_provider_bindings_model_id') in provider_binding_indexes:
            op.drop_index(op.f('ix_model_provider_bindings_model_id'), table_name='model_provider_bindings')
        op.drop_table('model_provider_bindings')
    
    op.execute("DROP TYPE IF EXISTS modelcapabilitytype")
    op.execute("DROP TYPE IF EXISTS modelstatus")
