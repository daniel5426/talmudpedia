"""model registry uuid identity hard cut

Revision ID: 6f8e9d0c1b2a
Revises: fd1a2b3c4d5e
Create Date: 2026-03-20 16:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6f8e9d0c1b2a"
down_revision: Union[str, Sequence[str], None] = "fd1a2b3c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("model_registry", sa.Column("system_key", sa.String(), nullable=True))
    op.create_index(op.f("ix_model_registry_system_key"), "model_registry", ["system_key"], unique=False)

    op.execute("UPDATE model_registry SET system_key = slug WHERE system_key IS NULL AND slug IS NOT NULL")

    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY COALESCE(CAST(tenant_id AS TEXT), '__global__'), capability_type
                       ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
                   ) AS row_num
            FROM model_registry
            WHERE is_default = true
        )
        UPDATE model_registry
        SET is_default = false
        WHERE id IN (
            SELECT id
            FROM ranked
            WHERE row_num > 1
        )
        """
    )

    op.create_index(
        "uq_model_registry_system_key_global",
        "model_registry",
        ["system_key"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL AND system_key IS NOT NULL"),
    )
    op.create_index(
        "uq_model_registry_default_tenant_capability",
        "model_registry",
        ["tenant_id", "capability_type"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL AND is_default = true"),
    )
    op.create_index(
        "uq_model_registry_default_global_capability",
        "model_registry",
        ["capability_type"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL AND is_default = true"),
    )

    op.drop_index("uq_model_registry_slug_tenant", table_name="model_registry")
    op.drop_index("uq_model_registry_slug_global", table_name="model_registry")
    op.drop_index("ix_model_registry_slug", table_name="model_registry")
    op.drop_column("model_registry", "slug")


def downgrade() -> None:
    op.add_column("model_registry", sa.Column("slug", sa.String(), nullable=True))
    op.execute("UPDATE model_registry SET slug = system_key WHERE system_key IS NOT NULL")
    op.execute("UPDATE model_registry SET slug = CAST(id AS TEXT) WHERE slug IS NULL")
    op.alter_column("model_registry", "slug", nullable=False)
    op.create_index(op.f("ix_model_registry_slug"), "model_registry", ["slug"], unique=False)
    op.create_index(
        "uq_model_registry_slug_tenant",
        "model_registry",
        ["slug", "tenant_id"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL"),
    )
    op.create_index(
        "uq_model_registry_slug_global",
        "model_registry",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )

    op.drop_index("uq_model_registry_default_global_capability", table_name="model_registry")
    op.drop_index("uq_model_registry_default_tenant_capability", table_name="model_registry")
    op.drop_index("uq_model_registry_system_key_global", table_name="model_registry")
    op.drop_index(op.f("ix_model_registry_system_key"), table_name="model_registry")
    op.drop_column("model_registry", "system_key")
