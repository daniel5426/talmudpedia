"""Add agent schema with graph fields

Revision ID: 2b63d49ec891
Revises: 1a55c38cc390
Create Date: 2026-01-12 23:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2b63d49ec891'
down_revision: Union[str, None] = '1a55c38cc390'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create AgentStatus enum
    agent_status_enum = postgresql.ENUM('draft', 'published', 'deprecated', 'archived', name='agentstatus')
    
    # Create RunStatus enum
    run_status_enum = postgresql.ENUM('queued', 'running', 'completed', 'failed', 'cancelled', name='runstatus')
    
    # Create agents table
    op.create_table(
        'agents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False, index=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), unique=True, nullable=False, index=True),
        sa.Column('description', sa.String(), nullable=True),
        
        # Graph Definition (DAG nodes and edges for visual builder)
        sa.Column('graph_definition', postgresql.JSONB, server_default='{"nodes": [], "edges": []}', nullable=False),
        
        # Legacy simple config (backward compatibility)
        sa.Column('model_provider', sa.String(), nullable=True),
        sa.Column('model_name', sa.String(), nullable=True),
        sa.Column('temperature', sa.Float(), server_default='0.7'),
        sa.Column('system_prompt', sa.String(), nullable=True),
        
        # Tool references
        sa.Column('tools', postgresql.JSONB, server_default='[]', nullable=False),
        
        # Referenced resources from graph
        sa.Column('referenced_model_ids', postgresql.JSONB, server_default='[]', nullable=False),
        sa.Column('referenced_tool_ids', postgresql.JSONB, server_default='[]', nullable=False),
        
        # Configuration
        sa.Column('memory_config', postgresql.JSONB, server_default='{"short_term_enabled": true, "short_term_max_messages": 20, "long_term_enabled": false, "long_term_index_id": null}', nullable=False),
        sa.Column('execution_constraints', postgresql.JSONB, server_default='{"timeout_seconds": 300, "max_tokens": null, "max_iterations": 10, "allow_parallel_tools": true}', nullable=False),
        
        # Versioning & Status
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('status', agent_status_enum, server_default='draft', nullable=False),
        
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('is_public', sa.Boolean(), server_default='false', nullable=False),
        
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
    )
    
    # Create agent_versions table
    op.create_table(
        'agent_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('config_snapshot', postgresql.JSONB, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
    )
    
    # Create agent_runs table
    op.create_table(
        'agent_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False, index=True),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True, index=True),
        
        sa.Column('status', run_status_enum, server_default='queued', nullable=False),
        
        sa.Column('input_params', postgresql.JSONB, server_default='{}'),
        sa.Column('output_result', postgresql.JSONB, nullable=True),
        sa.Column('error_message', sa.String(), nullable=True),
        
        sa.Column('usage_tokens', sa.Integer(), server_default='0'),
        sa.Column('cost', sa.String(), nullable=True),
        
        sa.Column('trace_id', sa.String(), nullable=True),
        
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    
    # Create agent_traces table
    op.create_table(
        'agent_traces',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agent_runs.id', ondelete='CASCADE'), nullable=False, index=True),
        
        sa.Column('span_id', sa.String(), nullable=False),
        sa.Column('parent_span_id', sa.String(), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        
        sa.Column('span_type', sa.String(), nullable=False),  # tool, llm, chain, etc
        
        sa.Column('inputs', postgresql.JSONB, nullable=True),
        sa.Column('outputs', postgresql.JSONB, nullable=True),
        
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        
        sa.Column('metadata', postgresql.JSONB, server_default='{}', nullable=False),
    )
    
    # Create indexes for better query performance
    op.create_index('ix_agents_status', 'agents', ['status'])
    op.create_index('ix_agent_runs_status', 'agent_runs', ['status'])
    op.create_index('ix_agent_traces_span_id', 'agent_traces', ['span_id'])


def downgrade() -> None:
    # Drop tables
    op.drop_table('agent_traces')
    op.drop_table('agent_runs')
    op.drop_table('agent_versions')
    op.drop_table('agents')
    
    # Drop enums
    postgresql.ENUM(name='agentstatus').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='runstatus').drop(op.get_bind(), checkfirst=True)
