"""remove workload security system

Revision ID: a9c8e7f6d5b4
Revises: b2f4c6d8e9a1, d4e5f6a7b8c9, ff1e2d3c4b5a
Create Date: 2026-03-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9c8e7f6d5b4"
down_revision: Union[str, Sequence[str], None] = ("b2f4c6d8e9a1", "d4e5f6a7b8c9", "ff1e2d3c4b5a")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return set(inspector.get_table_names())


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    try:
        return {column["name"] for column in inspector.get_columns(table_name)}
    except Exception:
        return set()


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    try:
        return {index["name"] for index in inspector.get_indexes(table_name)}
    except Exception:
        return set()


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    if table_name in _table_names() and index_name in _index_names(table_name):
        op.drop_index(index_name, table_name=table_name)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if table_name in _table_names() and column_name in _column_names(table_name):
        op.drop_column(table_name, column_name)


def _drop_constraint_if_exists(table_name: str, constraint_name: str) -> None:
    inspector = sa.inspect(op.get_bind())
    try:
        foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys(table_name)}
    except Exception:
        foreign_keys = set()
    if constraint_name in foreign_keys:
        op.drop_constraint(constraint_name, table_name, type_="foreignkey")


def upgrade() -> None:
    tables = _table_names()

    _drop_constraint_if_exists("agent_runs", "fk_agent_runs_workload_principal_id")
    _drop_constraint_if_exists("agent_runs", "fk_agent_runs_delegation_grant_id")

    _drop_index_if_exists("agent_runs", "ix_agent_runs_workload_principal_id")
    _drop_index_if_exists("agent_runs", "ix_agent_runs_delegation_grant_id")
    _drop_column_if_exists("agent_runs", "workload_principal_id")
    _drop_column_if_exists("agent_runs", "delegation_grant_id")

    _drop_index_if_exists("audit_logs", "ix_audit_logs_workload_principal_id")
    _drop_index_if_exists("audit_logs", "ix_audit_logs_delegation_grant_id")
    _drop_column_if_exists("audit_logs", "workload_principal_id")
    _drop_column_if_exists("audit_logs", "delegation_grant_id")

    _drop_column_if_exists("agents", "workload_scope_profile")
    _drop_column_if_exists("agents", "workload_scope_overrides")

    for table_name in (
        "token_jti_registry",
        "delegation_grants",
        "workload_scope_policies",
        "workload_principal_bindings",
        "workload_principals",
        "approval_decisions",
    ):
        if table_name in tables:
            op.drop_table(table_name)

    for enum_name in (
        "delegationgrantstatus",
        "workloadpolicystatus",
        "workloadresourcetype",
        "workloadprincipaltype",
        "approvalstatus",
    ):
        op.execute(sa.text(f"DROP TYPE IF EXISTS {enum_name}"))


def downgrade() -> None:
    raise RuntimeError("Workload security removal is a clean cut and cannot be downgraded.")
