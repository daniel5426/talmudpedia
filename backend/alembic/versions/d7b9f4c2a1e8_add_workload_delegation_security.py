"""add workload delegation security

Revision ID: d7b9f4c2a1e8
Revises: a8f9c3b2d1e4
Create Date: 2026-02-07 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd7b9f4c2a1e8'
down_revision: Union[str, None] = 'a8f9c3b2d1e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


workload_principal_type = postgresql.ENUM(
    'agent', 'artifact', 'tool', 'system',
    name='workloadprincipaltype',
    create_type=False,
)
workload_resource_type = postgresql.ENUM(
    'agent', 'artifact', 'tool',
    name='workloadresourcetype',
    create_type=False,
)
workload_policy_status = postgresql.ENUM(
    'pending', 'approved', 'rejected',
    name='workloadpolicystatus',
    create_type=False,
)
delegation_grant_status = postgresql.ENUM(
    'active', 'expired', 'revoked',
    name='delegationgrantstatus',
    create_type=False,
)
approval_status = postgresql.ENUM(
    'pending', 'approved', 'rejected',
    name='approvalstatus',
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    workload_principal_type.create(bind, checkfirst=True)
    workload_resource_type.create(bind, checkfirst=True)
    workload_policy_status.create(bind, checkfirst=True)
    delegation_grant_status.create(bind, checkfirst=True)
    approval_status.create(bind, checkfirst=True)

    op.create_table(
        'workload_principals',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('principal_type', workload_principal_type, nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'slug', name='uq_workload_principal_tenant_slug'),
    )
    op.create_index(op.f('ix_workload_principals_tenant_id'), 'workload_principals', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_workload_principals_slug'), 'workload_principals', ['slug'], unique=False)

    op.create_table(
        'workload_principal_bindings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('principal_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resource_type', workload_resource_type, nullable=False),
        sa.Column('resource_id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['principal_id'], ['workload_principals.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'resource_type', 'resource_id', name='uq_workload_binding_resource'),
    )
    op.create_index(op.f('ix_workload_principal_bindings_tenant_id'), 'workload_principal_bindings', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_workload_principal_bindings_principal_id'), 'workload_principal_bindings', ['principal_id'], unique=False)

    op.create_table(
        'workload_scope_policies',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('principal_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('requested_scopes', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('approved_scopes', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('status', workload_policy_status, nullable=False, server_default='pending'),
        sa.Column('approved_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['principal_id'], ['workload_principals.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('principal_id', 'version', name='uq_workload_policy_principal_version'),
    )
    op.create_index(op.f('ix_workload_scope_policies_principal_id'), 'workload_scope_policies', ['principal_id'], unique=False)

    op.create_table(
        'delegation_grants',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('principal_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('initiator_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('requested_scopes', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('effective_scopes', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('status', delegation_grant_status, nullable=False, server_default='active'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['initiator_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['principal_id'], ['workload_principals.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['agent_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_delegation_grants_tenant_id'), 'delegation_grants', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_delegation_grants_principal_id'), 'delegation_grants', ['principal_id'], unique=False)
    op.create_index(op.f('ix_delegation_grants_initiator_user_id'), 'delegation_grants', ['initiator_user_id'], unique=False)
    op.create_index(op.f('ix_delegation_grants_run_id'), 'delegation_grants', ['run_id'], unique=False)

    op.create_table(
        'token_jti_registry',
        sa.Column('jti', sa.String(), nullable=False),
        sa.Column('grant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revocation_reason', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['grant_id'], ['delegation_grants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('jti'),
    )
    op.create_index(op.f('ix_token_jti_registry_grant_id'), 'token_jti_registry', ['grant_id'], unique=False)
    op.create_index(op.f('ix_token_jti_registry_expires_at'), 'token_jti_registry', ['expires_at'], unique=False)

    op.create_table(
        'approval_decisions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('subject_type', sa.String(), nullable=False),
        sa.Column('subject_id', sa.String(), nullable=False),
        sa.Column('action_scope', sa.String(), nullable=False),
        sa.Column('status', approval_status, nullable=False, server_default='pending'),
        sa.Column('decided_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('rationale', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['decided_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_approval_subject', 'approval_decisions', ['tenant_id', 'subject_type', 'subject_id'], unique=False)

    op.add_column('agent_runs', sa.Column('workload_principal_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('agent_runs', sa.Column('delegation_grant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('agent_runs', sa.Column('initiator_user_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f('ix_agent_runs_workload_principal_id'), 'agent_runs', ['workload_principal_id'], unique=False)
    op.create_index(op.f('ix_agent_runs_delegation_grant_id'), 'agent_runs', ['delegation_grant_id'], unique=False)
    op.create_index(op.f('ix_agent_runs_initiator_user_id'), 'agent_runs', ['initiator_user_id'], unique=False)
    op.create_foreign_key(
        'fk_agent_runs_workload_principal_id',
        'agent_runs',
        'workload_principals',
        ['workload_principal_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_agent_runs_delegation_grant_id',
        'agent_runs',
        'delegation_grants',
        ['delegation_grant_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_agent_runs_initiator_user_id',
        'agent_runs',
        'users',
        ['initiator_user_id'],
        ['id'],
        ondelete='SET NULL',
    )

    op.add_column('audit_logs', sa.Column('initiator_user_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('audit_logs', sa.Column('workload_principal_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('audit_logs', sa.Column('delegation_grant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('audit_logs', sa.Column('token_jti', sa.String(), nullable=True))
    op.add_column('audit_logs', sa.Column('scopes', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index('ix_audit_logs_initiator_user_id', 'audit_logs', ['initiator_user_id'], unique=False)
    op.create_index('ix_audit_logs_workload_principal_id', 'audit_logs', ['workload_principal_id'], unique=False)
    op.create_index('ix_audit_logs_delegation_grant_id', 'audit_logs', ['delegation_grant_id'], unique=False)
    op.create_index('ix_audit_logs_token_jti', 'audit_logs', ['token_jti'], unique=False)


def downgrade() -> None:
    op.drop_constraint('fk_agent_runs_initiator_user_id', 'agent_runs', type_='foreignkey')
    op.drop_constraint('fk_agent_runs_delegation_grant_id', 'agent_runs', type_='foreignkey')
    op.drop_constraint('fk_agent_runs_workload_principal_id', 'agent_runs', type_='foreignkey')
    op.drop_index(op.f('ix_agent_runs_initiator_user_id'), table_name='agent_runs')
    op.drop_index(op.f('ix_agent_runs_delegation_grant_id'), table_name='agent_runs')
    op.drop_index(op.f('ix_agent_runs_workload_principal_id'), table_name='agent_runs')
    op.drop_column('agent_runs', 'initiator_user_id')
    op.drop_column('agent_runs', 'delegation_grant_id')
    op.drop_column('agent_runs', 'workload_principal_id')

    op.drop_index('ix_audit_logs_token_jti', table_name='audit_logs')
    op.drop_index('ix_audit_logs_delegation_grant_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_workload_principal_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_initiator_user_id', table_name='audit_logs')
    op.drop_column('audit_logs', 'scopes')
    op.drop_column('audit_logs', 'token_jti')
    op.drop_column('audit_logs', 'delegation_grant_id')
    op.drop_column('audit_logs', 'workload_principal_id')
    op.drop_column('audit_logs', 'initiator_user_id')

    op.drop_index('ix_approval_subject', table_name='approval_decisions')
    op.drop_table('approval_decisions')

    op.drop_index(op.f('ix_token_jti_registry_expires_at'), table_name='token_jti_registry')
    op.drop_index(op.f('ix_token_jti_registry_grant_id'), table_name='token_jti_registry')
    op.drop_table('token_jti_registry')

    op.drop_index(op.f('ix_delegation_grants_run_id'), table_name='delegation_grants')
    op.drop_index(op.f('ix_delegation_grants_initiator_user_id'), table_name='delegation_grants')
    op.drop_index(op.f('ix_delegation_grants_principal_id'), table_name='delegation_grants')
    op.drop_index(op.f('ix_delegation_grants_tenant_id'), table_name='delegation_grants')
    op.drop_table('delegation_grants')

    op.drop_index(op.f('ix_workload_scope_policies_principal_id'), table_name='workload_scope_policies')
    op.drop_table('workload_scope_policies')

    op.drop_index(op.f('ix_workload_principal_bindings_principal_id'), table_name='workload_principal_bindings')
    op.drop_index(op.f('ix_workload_principal_bindings_tenant_id'), table_name='workload_principal_bindings')
    op.drop_table('workload_principal_bindings')

    op.drop_index(op.f('ix_workload_principals_slug'), table_name='workload_principals')
    op.drop_index(op.f('ix_workload_principals_tenant_id'), table_name='workload_principals')
    op.drop_table('workload_principals')

    approval_status.drop(op.get_bind(), checkfirst=True)
    delegation_grant_status.drop(op.get_bind(), checkfirst=True)
    workload_policy_status.drop(op.get_bind(), checkfirst=True)
    workload_resource_type.drop(op.get_bind(), checkfirst=True)
    workload_principal_type.drop(op.get_bind(), checkfirst=True)
