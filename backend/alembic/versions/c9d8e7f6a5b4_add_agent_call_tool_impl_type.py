"""add_agent_call_tool_impl_type

Revision ID: c9d8e7f6a5b4
Revises: f1a2b3c4d5e7
Create Date: 2026-02-14 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c9d8e7f6a5b4"
down_revision: Union[str, None] = "f1a2b3c4d5e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'toolimplementationtype')
               AND NOT EXISTS (
                   SELECT 1
                   FROM pg_enum e
                   JOIN pg_type t ON t.oid = e.enumtypid
                   WHERE t.typname = 'toolimplementationtype'
                     AND e.enumlabel = 'AGENT_CALL'
               )
            THEN
                ALTER TYPE toolimplementationtype ADD VALUE 'AGENT_CALL';
            END IF;
        END$$;
        """
    )


def downgrade() -> None:
    # Postgres does not support dropping a single enum label safely in place.
    return
