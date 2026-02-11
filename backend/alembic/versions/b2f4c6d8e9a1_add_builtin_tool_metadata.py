"""add builtin tool metadata

Revision ID: b2f4c6d8e9a1
Revises: 9a4c7e21b3d5
Create Date: 2026-02-10 22:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2f4c6d8e9a1"
down_revision: Union[str, None] = "9a4c7e21b3d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tool_registry", sa.Column("builtin_key", sa.String(), nullable=True))
    op.add_column("tool_registry", sa.Column("builtin_template_id", sa.UUID(), nullable=True))
    op.add_column(
        "tool_registry",
        sa.Column("is_builtin_template", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.create_index("ix_tool_registry_builtin_key", "tool_registry", ["builtin_key"], unique=False)
    op.create_index("ix_tool_registry_builtin_template_id", "tool_registry", ["builtin_template_id"], unique=False)
    op.create_foreign_key(
        "fk_tool_registry_builtin_template_id",
        "tool_registry",
        "tool_registry",
        ["builtin_template_id"],
        ["id"],
        ondelete="SET NULL",
    )

    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.create_index(
            "uq_tool_registry_global_builtin_key",
            "tool_registry",
            ["builtin_key"],
            unique=True,
            postgresql_where=sa.text(
                "tenant_id IS NULL AND is_builtin_template = TRUE AND builtin_key IS NOT NULL"
            ),
        )

    op.execute(
        """
        UPDATE tool_registry
        SET builtin_key = 'platform_sdk', is_builtin_template = TRUE
        WHERE tenant_id IS NULL AND slug = 'platform-sdk'
        """
    )


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.drop_index("uq_tool_registry_global_builtin_key", table_name="tool_registry")

    op.drop_constraint("fk_tool_registry_builtin_template_id", "tool_registry", type_="foreignkey")
    op.drop_index("ix_tool_registry_builtin_template_id", table_name="tool_registry")
    op.drop_index("ix_tool_registry_builtin_key", table_name="tool_registry")

    op.drop_column("tool_registry", "is_builtin_template")
    op.drop_column("tool_registry", "builtin_template_id")
    op.drop_column("tool_registry", "builtin_key")
