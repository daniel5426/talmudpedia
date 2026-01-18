"""add_org_role_and_invites

Revision ID: 4e6b690a38e2
Revises: 694334b7714b
Create Date: 2026-01-15 00:04:53.121233

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e6b690a38e2'
down_revision: Union[str, None] = '694334b7714b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create Enums
    # We must check if type exists because 'create_type=False' in SQLAlchemy doesn't apply to raw DDL here usually, 
    # but since this is manual, we'll just create them. 
    # Note: If reusing existing DB, handle carefully. Here assuming fresh types.
    
    # 1. Create Enums idempotently
    op.execute("DO $$ BEGIN CREATE TYPE orgrole AS ENUM ('owner', 'admin', 'member'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE membershipstatus AS ENUM ('active', 'pending', 'invited', 'suspended'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    
    # We still need the objects to reference them in columns below
    from sqlalchemy.dialects import postgresql
    org_role = postgresql.ENUM('owner', 'admin', 'member', name='orgrole', create_type=False)
    # membership_status = sa.Enum(...) # Not strictly needed as object if we use string name in SQL, 
    # but for sa.Column(..., org_role) we need the object or name.

    # 2. Add 'role' to org_memberships
    # We add it as nullable first to populate if needed, but here we set a server_default
    op.add_column('org_memberships', sa.Column('role', org_role, server_default='member', nullable=False))

    # 3. Alter 'status' in org_memberships
    # First drop default because old string default conflicts with new Enum type
    op.execute("ALTER TABLE org_memberships ALTER COLUMN status DROP DEFAULT")
    # Then cast
    op.execute("ALTER TABLE org_memberships ALTER COLUMN status TYPE membershipstatus USING status::membershipstatus")
    # Then set new default
    op.execute("ALTER TABLE org_memberships ALTER COLUMN status SET DEFAULT 'active'::membershipstatus")

    # 4. Create org_invites table
    op.create_table('org_invites',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('role', org_role, nullable=False),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token')
    )
    op.create_index(op.f('ix_org_invites_email'), 'org_invites', ['email'], unique=False)


def downgrade() -> None:
    # Drop org_invites
    op.drop_index(op.f('ix_org_invites_email'), table_name='org_invites')
    op.drop_table('org_invites')

    # Revert status to String
    op.alter_column('org_memberships', 'status',
               existing_type=sa.Enum('active', 'pending', 'invited', 'suspended', name='membershipstatus'),
               type_=sa.String(),
               existing_nullable=False)

    # Drop role column
    op.drop_column('org_memberships', 'role')

    # Drop Enums
    sa.Enum(name='membershipstatus').drop(op.get_bind())
    sa.Enum(name='orgrole').drop(op.get_bind())
