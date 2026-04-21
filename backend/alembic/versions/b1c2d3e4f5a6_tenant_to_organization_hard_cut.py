"""tenant to organization hard cut

Revision ID: e1f2a3b4c5d6
Revises: ac91de42bf67
Create Date: 2026-04-21
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "ac91de42bf67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_RENAMES: tuple[tuple[str, str], ...] = (
    ("tenants", "organizations"),
    ("tenant_api_keys", "organization_api_keys"),
    ("artifact_tenant_runtime_policies", "artifact_organization_runtime_policies"),
)

COLUMN_RENAMES: tuple[tuple[str, str], ...] = (
    ("tenant_id", "organization_id"),
    ("tenant_api_key_id", "organization_api_key_id"),
    ("reserved_tokens_tenant", "reserved_tokens_organization"),
)


def _table_names(bind: sa.Connection) -> set[str]:
    return set(inspect(bind).get_table_names())


def _column_names(bind: sa.Connection, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(bind).get_columns(table_name)}


def _rename_tables(bind: sa.Connection, *, reverse: bool) -> None:
    table_names = _table_names(bind)
    renames = reversed(TABLE_RENAMES) if reverse else TABLE_RENAMES
    for source, target in renames:
        old_name, new_name = (target, source) if reverse else (source, target)
        if old_name in table_names and new_name not in table_names:
            op.rename_table(old_name, new_name)
            table_names.remove(old_name)
            table_names.add(new_name)


def _rename_columns(bind: sa.Connection, *, reverse: bool) -> None:
    for table_name in sorted(_table_names(bind)):
        columns = _column_names(bind, table_name)
        for source, target in COLUMN_RENAMES:
            old_name, new_name = (target, source) if reverse else (source, target)
            if old_name in columns and new_name not in columns:
                op.alter_column(table_name, old_name, new_column_name=new_name)
                columns.remove(old_name)
                columns.add(new_name)


def upgrade() -> None:
    bind = op.get_bind()
    _rename_tables(bind, reverse=False)
    _rename_columns(bind, reverse=False)
    bind.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'usagequotascopetype') THEN
                    ALTER TYPE usagequotascopetype RENAME VALUE 'tenant' TO 'organization';
                END IF;
            END
            $$;
            """
        )
    )
    bind.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'resourcepolicyprincipaltype') THEN
                    ALTER TYPE resourcepolicyprincipaltype RENAME VALUE 'tenant_user' TO 'organization_user';
                END IF;
            END
            $$;
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'resourcepolicyprincipaltype') THEN
                    ALTER TYPE resourcepolicyprincipaltype RENAME VALUE 'organization_user' TO 'tenant_user';
                END IF;
            END
            $$;
            """
        )
    )
    bind.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'usagequotascopetype') THEN
                    ALTER TYPE usagequotascopetype RENAME VALUE 'organization' TO 'tenant';
                END IF;
            END
            $$;
            """
        )
    )
    _rename_columns(bind, reverse=True)
    _rename_tables(bind, reverse=True)
