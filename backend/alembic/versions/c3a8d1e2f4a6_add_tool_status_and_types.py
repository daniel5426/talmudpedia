"""add tool status and types

Revision ID: c3a8d1e2f4a6
Revises: bb55ce1e499a
Create Date: 2026-02-03 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'c3a8d1e2f4a6'
down_revision: Union[str, None] = 'bb55ce1e499a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tool_status_enum = sa.Enum('draft', 'published', 'deprecated', 'disabled', name='toolstatus')
    tool_impl_enum = sa.Enum('internal', 'http', 'rag_retrieval', 'function', 'custom', 'artifact', 'mcp', name='toolimplementationtype')

    tool_status_enum.create(op.get_bind(), checkfirst=True)
    tool_impl_enum.create(op.get_bind(), checkfirst=True)

    op.add_column('tool_registry', sa.Column('status', tool_status_enum, server_default='draft', nullable=False))
    op.add_column('tool_registry', sa.Column('version', sa.String(), server_default='1.0.0', nullable=False))
    op.add_column('tool_registry', sa.Column('implementation_type', tool_impl_enum, server_default='custom', nullable=False))
    op.add_column('tool_registry', sa.Column('published_at', sa.DateTime(timezone=True), nullable=True))

    # Backfill status based on is_active
    op.execute(
        """
        UPDATE tool_registry
        SET status = CASE
            WHEN is_active THEN 'published'::toolstatus
            ELSE 'disabled'::toolstatus
        END
        """
    )

    # Backfill implementation_type while supporting schema variants across environments.
    bind = op.get_bind()
    inspector = inspect(bind)
    column_names = {col["name"] for col in inspector.get_columns("tool_registry")}
    has_artifact_id = "artifact_id" in column_names
    has_config_schema = "config_schema" in column_names
    has_is_system = "is_system" in column_names

    when_clauses: list[str] = []
    if has_artifact_id:
        when_clauses.append("WHEN artifact_id IS NOT NULL THEN 'artifact'::toolimplementationtype")
    if has_config_schema:
        when_clauses.append(
            """
            WHEN (config_schema->'implementation'->>'type') IN (
                'internal','http','rag_retrieval','function','custom','artifact','mcp'
            ) THEN ((config_schema->'implementation'->>'type')::toolimplementationtype)
            """.strip()
        )
    if has_is_system:
        when_clauses.append("WHEN is_system THEN 'internal'::toolimplementationtype")

    impl_update_sql = f"""
        UPDATE tool_registry
        SET implementation_type = CASE
            {' '.join(when_clauses)}
            ELSE 'custom'::toolimplementationtype
        END
    """
    op.execute(impl_update_sql)

    # Backfill published_at for active tools
    op.execute(
        """
        UPDATE tool_registry
        SET published_at = COALESCE(published_at, created_at)
        WHERE is_active = TRUE
        """
    )


def downgrade() -> None:
    op.drop_column('tool_registry', 'published_at')
    op.drop_column('tool_registry', 'implementation_type')
    op.drop_column('tool_registry', 'version')
    op.drop_column('tool_registry', 'status')

    sa.Enum(name='toolimplementationtype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='toolstatus').drop(op.get_bind(), checkfirst=True)
