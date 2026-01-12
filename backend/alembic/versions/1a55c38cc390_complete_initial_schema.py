"""Complete Initial Schema

Revision ID: 1a55c38cc390
Revises: 
Create Date: 2026-01-12 22:53:32.358811

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a55c38cc390'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create ENUMs first
    tenant_status_enum = sa.Enum('active', 'suspended', 'pending', name='tenantstatus')
    org_unit_type_enum = sa.Enum('org', 'dept', 'team', name='orgunittype')
    
    # Create tenants table
    op.create_table(
        'tenants',
        sa.Column('id', sa.UUID(), nullable=False, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('status', tenant_status_enum, nullable=False, server_default='active'),
        sa.Column('settings', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_tenants_slug', 'tenants', ['slug'], unique=True)

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), nullable=False, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=True),
        sa.Column('google_id', sa.String(), nullable=True),
        sa.Column('full_name', sa.String(), nullable=True),
        sa.Column('avatar', sa.String(), nullable=True),
        sa.Column('role', sa.String(), nullable=False, server_default='user'),
        sa.Column('token_usage', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_google_id', 'users', ['google_id'], unique=True)

    # Create org_units table
    op.create_table(
        'org_units',
        sa.Column('id', sa.UUID(), nullable=False, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.UUID(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('parent_id', sa.UUID(), sa.ForeignKey('org_units.id'), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('type', org_unit_type_enum, nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_org_units_tenant_id', 'org_units', ['tenant_id'])
    op.create_index('ix_org_units_parent_id', 'org_units', ['parent_id'])
    op.create_index('ix_org_units_slug', 'org_units', ['slug'])

    # Create org_memberships table
    op.create_table(
        'org_memberships',
        sa.Column('id', sa.UUID(), nullable=False, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.UUID(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('org_unit_id', sa.UUID(), sa.ForeignKey('org_units.id'), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='active'),
        sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('org_memberships')
    op.drop_table('org_units')
    op.drop_table('users')
    op.drop_table('tenants')
    op.execute('DROP TYPE tenantstatus')
    op.execute('DROP TYPE orgunittype')
