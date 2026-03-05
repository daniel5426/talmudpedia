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


def _target_roles() -> list[str]:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT rolname
            FROM pg_roles
            WHERE rolname IN ('anon', 'authenticated')
            """
        )
    ).fetchall()
    return [str(row[0]) for row in rows]


def upgrade() -> None:
    roles = _target_roles()
    for role in roles:
        op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role};")
        op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {role};")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {role};")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {role};")


def downgrade() -> None:
    roles = _target_roles()
    for role in roles:
        op.execute(f"GRANT ALL ON ALL TABLES IN SCHEMA public TO {role};")
        op.execute(f"GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {role};")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {role};")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {role};")
