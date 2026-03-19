"""add tool ownership persistence

Revision ID: b7c8d9e0f1a2
Revises: 1f2e3d4c5b6a, a4c9d2f7b6e1, c3f4e5a6b7d8, fb9a1c2d3e4f
Create Date: 2026-03-19 18:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = (
    "1f2e3d4c5b6a",
    "a4c9d2f7b6e1",
    "c3f4e5a6b7d8",
    "fb9a1c2d3e4f",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "tool_registry"
    if table_name not in inspector.get_table_names():
        return

    for column_name in ("ownership", "managed_by", "source_object_type", "source_object_id"):
        if not _column_exists(inspector, table_name, column_name):
            op.add_column(table_name, sa.Column(column_name, sa.String(), nullable=True))

    inspector = sa.inspect(bind)
    for index_name, columns in (
        ("ix_tool_registry_ownership", ["ownership"]),
        ("ix_tool_registry_managed_by", ["managed_by"]),
        ("ix_tool_registry_source_object_type", ["source_object_type"]),
        ("ix_tool_registry_source_object_id", ["source_object_id"]),
    ):
        if not _index_exists(inspector, table_name, index_name):
            op.create_index(index_name, table_name, columns, unique=False)

    if bind.dialect.name == "postgresql":
        op.execute(
            """
            UPDATE tool_registry
            SET ownership = CASE
                WHEN is_system THEN 'system'
                WHEN COALESCE(config_schema->'agent_binding'->>'owned_by_source', '') = 'true'
                     AND COALESCE(config_schema->'agent_binding'->>'agent_id', '') <> '' THEN 'agent_bound'
                WHEN artifact_id IS NOT NULL OR implementation_type::text = 'ARTIFACT' THEN 'artifact_bound'
                WHEN visual_pipeline_id IS NOT NULL
                     OR executable_pipeline_id IS NOT NULL
                     OR implementation_type::text = 'RAG_PIPELINE' THEN 'pipeline_bound'
                ELSE 'manual'
            END
            WHERE ownership IS NULL
            """
        )
        op.execute(
            """
            UPDATE tool_registry
            SET managed_by = CASE ownership
                WHEN 'agent_bound' THEN 'agents'
                WHEN 'artifact_bound' THEN 'artifacts'
                WHEN 'pipeline_bound' THEN 'pipelines'
                WHEN 'system' THEN 'system'
                ELSE 'tools'
            END
            WHERE managed_by IS NULL
            """
        )
        op.execute(
            """
            UPDATE tool_registry
            SET source_object_type = CASE ownership
                WHEN 'agent_bound' THEN 'agent'
                WHEN 'artifact_bound' THEN 'artifact'
                WHEN 'pipeline_bound' THEN 'pipeline'
                ELSE NULL
            END
            WHERE source_object_type IS NULL
            """
        )
        op.execute(
            """
            UPDATE tool_registry
            SET source_object_id = CASE ownership
                WHEN 'agent_bound' THEN NULLIF(config_schema->'agent_binding'->>'agent_id', '')
                WHEN 'artifact_bound' THEN artifact_id
                WHEN 'pipeline_bound' THEN COALESCE(visual_pipeline_id::text, executable_pipeline_id::text)
                ELSE NULL
            END
            WHERE source_object_id IS NULL
            """
        )
    else:
        op.execute(
            """
            UPDATE tool_registry
            SET ownership = CASE
                WHEN is_system = 1 THEN 'system'
                WHEN COALESCE(json_extract(config_schema, '$.agent_binding.owned_by_source'), 0) IN (1, 'true')
                     AND COALESCE(json_extract(config_schema, '$.agent_binding.agent_id'), '') <> '' THEN 'agent_bound'
                WHEN artifact_id IS NOT NULL OR lower(COALESCE(implementation_type, '')) = 'artifact' THEN 'artifact_bound'
                WHEN visual_pipeline_id IS NOT NULL
                     OR executable_pipeline_id IS NOT NULL
                     OR lower(COALESCE(implementation_type, '')) = 'rag_pipeline' THEN 'pipeline_bound'
                ELSE 'manual'
            END
            WHERE ownership IS NULL
            """
        )
        op.execute(
            """
            UPDATE tool_registry
            SET managed_by = CASE ownership
                WHEN 'agent_bound' THEN 'agents'
                WHEN 'artifact_bound' THEN 'artifacts'
                WHEN 'pipeline_bound' THEN 'pipelines'
                WHEN 'system' THEN 'system'
                ELSE 'tools'
            END
            WHERE managed_by IS NULL
            """
        )
        op.execute(
            """
            UPDATE tool_registry
            SET source_object_type = CASE ownership
                WHEN 'agent_bound' THEN 'agent'
                WHEN 'artifact_bound' THEN 'artifact'
                WHEN 'pipeline_bound' THEN 'pipeline'
                ELSE NULL
            END
            WHERE source_object_type IS NULL
            """
        )
        op.execute(
            """
            UPDATE tool_registry
            SET source_object_id = CASE ownership
                WHEN 'agent_bound' THEN NULLIF(json_extract(config_schema, '$.agent_binding.agent_id'), '')
                WHEN 'artifact_bound' THEN artifact_id
                WHEN 'pipeline_bound' THEN COALESCE(visual_pipeline_id, executable_pipeline_id)
                ELSE NULL
            END
            WHERE source_object_id IS NULL
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "tool_registry"
    if table_name not in inspector.get_table_names():
        return

    for index_name in (
        "ix_tool_registry_source_object_id",
        "ix_tool_registry_source_object_type",
        "ix_tool_registry_managed_by",
        "ix_tool_registry_ownership",
    ):
        if _index_exists(inspector, table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

    inspector = sa.inspect(bind)
    for column_name in ("source_object_id", "source_object_type", "managed_by", "ownership"):
        if _column_exists(inspector, table_name, column_name):
            op.drop_column(table_name, column_name)
