"""add_pipeline_step_execution

Revision ID: a9b8c7d6e5f4
Revises: 4f17fe6cd710
Create Date: 2026-01-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a9b8c7d6e5f4'
down_revision: Union[str, None] = '4f17fe6cd710'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the new enum type safely
    op.execute("DO $$ BEGIN CREATE TYPE pipelinestepstatus AS ENUM ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'SKIPPED'); EXCEPTION WHEN duplicate_object THEN null; END $$;")

    op.create_table('pipeline_step_executions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('job_id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('step_id', sa.String(), nullable=False),
    sa.Column('operator_id', sa.String(), nullable=False),
    sa.Column('status', postgresql.ENUM('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'SKIPPED', name='pipelinestepstatus', create_type=False), nullable=False),
    sa.Column('input_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('output_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('execution_order', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['job_id'], ['pipeline_jobs.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pipeline_step_executions_job_id'), 'pipeline_step_executions', ['job_id'], unique=False)
    op.create_index(op.f('ix_pipeline_step_executions_tenant_id'), 'pipeline_step_executions', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_pipeline_step_executions_tenant_id'), table_name='pipeline_step_executions')
    op.drop_index(op.f('ix_pipeline_step_executions_job_id'), table_name='pipeline_step_executions')
    op.drop_table('pipeline_step_executions')
    
    # Drop enum safely
    op.execute("DROP TYPE IF EXISTS pipelinestepstatus")
