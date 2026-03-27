"""add_custom_operators

Revision ID: 4f17fe6cd710
Revises: b6484bf3357d
Create Date: 2026-01-23 02:16:07.476179

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4f17fe6cd710'
down_revision: Union[str, None] = 'b6484bf3357d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE operatorcategory AS ENUM (
                'SOURCE', 'NORMALIZATION', 'ENRICHMENT', 'CHUNKING', 'EMBEDDING',
                'STORAGE', 'RETRIEVAL', 'RERANKING', 'CUSTOM', 'TRANSFORM',
                'LLM', 'OUTPUT', 'CONTROL'
            );
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    if 'custom_operators' not in set(inspector.get_table_names()):
        op.create_table('custom_operators',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column(
            'category',
            postgresql.ENUM(
                'SOURCE', 'NORMALIZATION', 'ENRICHMENT', 'CHUNKING', 'EMBEDDING',
                'STORAGE', 'RETRIEVAL', 'RERANKING', 'CUSTOM', 'TRANSFORM',
                'LLM', 'OUTPUT', 'CONTROL',
                name='operatorcategory',
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('python_code', sa.Text(), nullable=False),
        sa.Column('input_type', sa.String(), nullable=False),
        sa.Column('output_type', sa.String(), nullable=False),
        sa.Column('config_schema', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
        )

    custom_operator_indexes = {
        index["name"] for index in inspect(bind).get_indexes("custom_operators")
    }
    if op.f('ix_custom_operators_tenant_id') not in custom_operator_indexes:
        op.create_index(op.f('ix_custom_operators_tenant_id'), 'custom_operators', ['tenant_id'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if 'custom_operators' in set(inspect(bind).get_table_names()):
        custom_operator_indexes = {
            index["name"] for index in inspect(bind).get_indexes("custom_operators")
        }
        if op.f('ix_custom_operators_tenant_id') in custom_operator_indexes:
            op.drop_index(op.f('ix_custom_operators_tenant_id'), table_name='custom_operators')
        op.drop_table('custom_operators')
