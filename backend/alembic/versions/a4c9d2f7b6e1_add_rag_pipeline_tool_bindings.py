"""add_rag_pipeline_tool_bindings

Revision ID: a4c9d2f7b6e1
Revises: 6a1d4e9b2c7f
Create Date: 2026-03-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a4c9d2f7b6e1"
down_revision: Union[str, Sequence[str], None] = "6a1d4e9b2c7f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def _uuid_type(bind) -> sa.types.TypeEngine:
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import UUID

        return UUID(as_uuid=True)
    return sa.String(length=36)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
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
                             AND e.enumlabel = 'RAG_PIPELINE'
                       )
                    THEN
                        ALTER TYPE toolimplementationtype ADD VALUE 'RAG_PIPELINE';
                    END IF;
                END$$;
                """
            )

    table_name = "tool_registry"
    if table_name in inspector.get_table_names():
        uuid_type = _uuid_type(bind)

        if not _column_exists(inspector, table_name, "visual_pipeline_id"):
            op.add_column(table_name, sa.Column("visual_pipeline_id", uuid_type, nullable=True))
        if not _column_exists(inspector, table_name, "executable_pipeline_id"):
            op.add_column(table_name, sa.Column("executable_pipeline_id", uuid_type, nullable=True))

        inspector = sa.inspect(bind)
        if _column_exists(inspector, table_name, "visual_pipeline_id") and not _index_exists(inspector, table_name, "ix_tool_registry_visual_pipeline_id"):
            op.create_index("ix_tool_registry_visual_pipeline_id", table_name, ["visual_pipeline_id"], unique=False)
        if _column_exists(inspector, table_name, "executable_pipeline_id") and not _index_exists(inspector, table_name, "ix_tool_registry_executable_pipeline_id"):
            op.create_index("ix_tool_registry_executable_pipeline_id", table_name, ["executable_pipeline_id"], unique=False)

        if bind.dialect.name == "postgresql":
            op.execute(
                """
                UPDATE tool_registry
                SET implementation_type = 'RAG_PIPELINE'
                WHERE implementation_type::text = 'RAG_RETRIEVAL'
                """
            )
            op.execute(
                """
                UPDATE tool_registry
                SET config_schema = REPLACE(config_schema::text, 'rag_retrieval', 'rag_pipeline')::jsonb
                WHERE config_schema::text LIKE '%rag_retrieval%'
                """
            )
            op.execute(
                """
                UPDATE tool_versions
                SET schema_snapshot = REPLACE(schema_snapshot::text, 'rag_retrieval', 'rag_pipeline')::jsonb
                WHERE schema_snapshot::text LIKE '%rag_retrieval%'
                """
            )
        else:
            op.execute(
                """
                UPDATE tool_registry
                SET implementation_type = 'RAG_PIPELINE'
                WHERE lower(implementation_type) = 'rag_retrieval'
                """
            )
            op.execute(
                """
                UPDATE tool_registry
                SET config_schema = replace(config_schema, 'rag_retrieval', 'rag_pipeline')
                WHERE config_schema LIKE '%rag_retrieval%'
                """
            )
            op.execute(
                """
                UPDATE tool_versions
                SET schema_snapshot = replace(schema_snapshot, 'rag_retrieval', 'rag_pipeline')
                WHERE schema_snapshot LIKE '%rag_retrieval%'
                """
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "tool_registry"
    if table_name not in inspector.get_table_names():
        return

    if _index_exists(inspector, table_name, "ix_tool_registry_executable_pipeline_id"):
        op.drop_index("ix_tool_registry_executable_pipeline_id", table_name=table_name)
    if _index_exists(inspector, table_name, "ix_tool_registry_visual_pipeline_id"):
        op.drop_index("ix_tool_registry_visual_pipeline_id", table_name=table_name)

    inspector = sa.inspect(bind)
    if _column_exists(inspector, table_name, "executable_pipeline_id"):
        op.drop_column(table_name, "executable_pipeline_id")
    if _column_exists(inspector, table_name, "visual_pipeline_id"):
        op.drop_column(table_name, "visual_pipeline_id")
