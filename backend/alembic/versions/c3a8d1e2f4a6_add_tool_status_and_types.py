"""add tool status and types

Revision ID: c3a8d1e2f4a6
Revises: bb55ce1e499a
Create Date: 2026-02-03 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


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
            WHEN is_active THEN 'published'
            ELSE 'disabled'
        END
        """
    )

    # Backfill implementation_type based on artifact_id, config_schema, or is_system
    op.execute(
        """
        UPDATE tool_registry
        SET implementation_type = CASE
            WHEN artifact_id IS NOT NULL THEN 'artifact'
            WHEN (config_schema->'implementation'->>'type') IN (
                'internal','http','rag_retrieval','function','custom','artifact','mcp'
            ) THEN (config_schema->'implementation'->>'type')
            WHEN is_system THEN 'internal'
            ELSE 'custom'
        END
        """
    )

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
