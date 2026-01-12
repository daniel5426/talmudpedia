"""harden_security_revoking_grants

Revision ID: 104ae692d66d
Revises: 2b63d49ec891
Create Date: 2026-01-12 23:40:07.277414

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '104ae692d66d'
down_revision: Union[str, None] = '2b63d49ec891'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Revoke all privileges from anon and authenticated roles for existing tables
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;")
    # Revoke all privileges from anon and authenticated roles for existing sequences
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;")
    # Revoke usage on public schema itself
    # op.execute("REVOKE USAGE ON SCHEMA public FROM anon, authenticated;")
    
    # Update default privileges for future tables
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;")


def downgrade() -> None:
    # Grant back basic privileges (Supabase defaults)
    op.execute("GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated;")
    op.execute("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;")
    
    # Restore default privileges
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated;")
