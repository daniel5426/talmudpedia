"""Add knowledge_stores table

Revision ID: e1a2b3c4d5e6
Revises: cdfb1a48b29a
Create Date: 2026-02-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e1a2b3c4d5e6'
down_revision: Union[str, None] = '172b677007a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create knowledge store status enum
    knowledge_store_status = sa.Enum('active', 'syncing', 'error', 'archived', name='knowledgestorestatus')
    
    # Create storage backend enum
    storage_backend = sa.Enum('pgvector', 'pinecone', 'qdrant', name='storagebackend')
    
    # Create retrieval policy enum
    retrieval_policy = sa.Enum('semantic_only', 'hybrid', 'keyword_only', 'recency_boosted', name='retrievalpolicy')
    
    op.create_table(
        'knowledge_stores',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        
        # Identity
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        
        # Logical Configuration (The Contract)
        sa.Column('embedding_model_id', sa.String(), nullable=False),
        sa.Column('chunking_strategy', postgresql.JSONB(), server_default='{}', nullable=False),
        sa.Column('retrieval_policy', retrieval_policy, server_default='semantic_only', nullable=False),
        
        # Physical Binding (Implementation Detail)
        sa.Column('backend', storage_backend, server_default='pgvector', nullable=False),
        sa.Column('backend_config', postgresql.JSONB(), server_default='{}', nullable=False),
        
        # Status & Metrics
        sa.Column('status', knowledge_store_status, server_default='active', nullable=False),
        sa.Column('document_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('chunk_count', sa.Integer(), server_default='0', nullable=False),
        
        # Timestamps & Ownership
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Indexes
    op.create_index('ix_knowledge_stores_tenant_id', 'knowledge_stores', ['tenant_id'])
    op.create_index('ix_knowledge_stores_status', 'knowledge_stores', ['status'])


def downgrade() -> None:
    op.drop_index('ix_knowledge_stores_status')
    op.drop_index('ix_knowledge_stores_tenant_id')
    op.drop_table('knowledge_stores')
    op.execute('DROP TYPE knowledgestorestatus')
    op.execute('DROP TYPE storagebackend')
    op.execute('DROP TYPE retrievalpolicy')
