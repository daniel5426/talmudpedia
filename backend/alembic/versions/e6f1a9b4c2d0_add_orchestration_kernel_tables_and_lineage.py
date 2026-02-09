"""add orchestration kernel tables and lineage

Revision ID: e6f1a9b4c2d0
Revises: d7b9f4c2a1e8
Create Date: 2026-02-08 19:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e6f1a9b4c2d0'
down_revision: Union[str, None] = 'd7b9f4c2a1e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agent_runs', sa.Column('root_run_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('agent_runs', sa.Column('parent_run_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('agent_runs', sa.Column('parent_node_id', sa.String(), nullable=True))
    op.add_column('agent_runs', sa.Column('depth', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('agent_runs', sa.Column('spawn_key', sa.String(), nullable=True))
    op.add_column('agent_runs', sa.Column('orchestration_group_id', postgresql.UUID(as_uuid=True), nullable=True))

    op.create_table(
        'orchestrator_policies',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('orchestrator_agent_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('enforce_published_only', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('default_failure_policy', sa.String(), nullable=False, server_default='best_effort'),
        sa.Column('max_depth', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('max_fanout', sa.Integer(), nullable=False, server_default='8'),
        sa.Column('max_children_total', sa.Integer(), nullable=False, server_default='32'),
        sa.Column('join_timeout_s', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('allowed_scope_subset', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('capability_manifest_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['orchestrator_agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'orchestrator_agent_id', name='uq_orchestrator_policy_agent'),
    )
    op.create_index(op.f('ix_orchestrator_policies_tenant_id'), 'orchestrator_policies', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_orchestrator_policies_orchestrator_agent_id'), 'orchestrator_policies', ['orchestrator_agent_id'], unique=False)

    op.create_table(
        'orchestrator_target_allowlists',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('orchestrator_agent_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('target_agent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('target_agent_slug', sa.String(), nullable=True),
        sa.Column('capability_tag', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['orchestrator_agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_orchestrator_target_allowlists_tenant_id'), 'orchestrator_target_allowlists', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_orchestrator_target_allowlists_orchestrator_agent_id'), 'orchestrator_target_allowlists', ['orchestrator_agent_id'], unique=False)
    op.create_index(op.f('ix_orchestrator_target_allowlists_target_agent_id'), 'orchestrator_target_allowlists', ['target_agent_id'], unique=False)
    op.create_index('ix_orchestrator_target_allowlists_orch_slug', 'orchestrator_target_allowlists', ['orchestrator_agent_id', 'target_agent_slug'], unique=False)

    op.create_table(
        'orchestration_groups',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('orchestrator_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('parent_node_id', sa.String(), nullable=True),
        sa.Column('failure_policy', sa.String(), nullable=False, server_default='best_effort'),
        sa.Column('join_mode', sa.String(), nullable=False, server_default='all'),
        sa.Column('quorum_threshold', sa.Integer(), nullable=True),
        sa.Column('timeout_s', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('status', sa.String(), nullable=False, server_default='running'),
        sa.Column('policy_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['orchestrator_run_id'], ['agent_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_orchestration_groups_tenant_id'), 'orchestration_groups', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_orchestration_groups_orchestrator_run_id'), 'orchestration_groups', ['orchestrator_run_id'], unique=False)

    op.create_table(
        'orchestration_group_members',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('group_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ordinal', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(), nullable=False, server_default='queued'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['orchestration_groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['agent_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_id', 'run_id', name='uq_orchestration_group_member'),
    )
    op.create_index(op.f('ix_orchestration_group_members_group_id'), 'orchestration_group_members', ['group_id'], unique=False)
    op.create_index(op.f('ix_orchestration_group_members_run_id'), 'orchestration_group_members', ['run_id'], unique=False)

    op.create_index(op.f('ix_agent_runs_root_run_id'), 'agent_runs', ['root_run_id'], unique=False)
    op.create_index(op.f('ix_agent_runs_parent_run_id'), 'agent_runs', ['parent_run_id'], unique=False)
    op.create_index(op.f('ix_agent_runs_orchestration_group_id'), 'agent_runs', ['orchestration_group_id'], unique=False)
    op.create_index('ix_agent_runs_root_created_at', 'agent_runs', ['root_run_id', 'created_at'], unique=False)
    op.create_index('ix_agent_runs_parent_created_at', 'agent_runs', ['parent_run_id', 'created_at'], unique=False)

    op.create_unique_constraint('uq_agent_runs_parent_spawn_key', 'agent_runs', ['parent_run_id', 'spawn_key'])
    op.create_foreign_key(
        'fk_agent_runs_root_run_id',
        'agent_runs',
        'agent_runs',
        ['root_run_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_agent_runs_parent_run_id',
        'agent_runs',
        'agent_runs',
        ['parent_run_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_agent_runs_orchestration_group_id',
        'agent_runs',
        'orchestration_groups',
        ['orchestration_group_id'],
        ['id'],
        ondelete='SET NULL',
    )

    op.alter_column('agent_runs', 'depth', server_default=None)


def downgrade() -> None:
    op.drop_constraint('fk_agent_runs_orchestration_group_id', 'agent_runs', type_='foreignkey')
    op.drop_constraint('fk_agent_runs_parent_run_id', 'agent_runs', type_='foreignkey')
    op.drop_constraint('fk_agent_runs_root_run_id', 'agent_runs', type_='foreignkey')
    op.drop_constraint('uq_agent_runs_parent_spawn_key', 'agent_runs', type_='unique')

    op.drop_index('ix_agent_runs_parent_created_at', table_name='agent_runs')
    op.drop_index('ix_agent_runs_root_created_at', table_name='agent_runs')
    op.drop_index(op.f('ix_agent_runs_orchestration_group_id'), table_name='agent_runs')
    op.drop_index(op.f('ix_agent_runs_parent_run_id'), table_name='agent_runs')
    op.drop_index(op.f('ix_agent_runs_root_run_id'), table_name='agent_runs')

    op.drop_table('orchestration_group_members')
    op.drop_table('orchestration_groups')

    op.drop_index('ix_orchestrator_target_allowlists_orch_slug', table_name='orchestrator_target_allowlists')
    op.drop_table('orchestrator_target_allowlists')

    op.drop_table('orchestrator_policies')

    op.drop_column('agent_runs', 'orchestration_group_id')
    op.drop_column('agent_runs', 'spawn_key')
    op.drop_column('agent_runs', 'depth')
    op.drop_column('agent_runs', 'parent_node_id')
    op.drop_column('agent_runs', 'parent_run_id')
    op.drop_column('agent_runs', 'root_run_id')
