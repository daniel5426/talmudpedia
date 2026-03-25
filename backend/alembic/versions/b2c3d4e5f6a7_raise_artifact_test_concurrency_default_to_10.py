"""raise artifact test concurrency default to 10

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f7
Create Date: 2026-03-25
"""

from alembic import op
import sqlalchemy as sa


revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "artifact_tenant_runtime_policies",
        "test_concurrency_limit",
        existing_type=sa.Integer(),
        server_default="10",
        existing_nullable=False,
    )
    op.execute(
        sa.text(
            """
            UPDATE artifact_tenant_runtime_policies
            SET test_concurrency_limit = 10
            WHERE test_concurrency_limit = 2
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE artifact_tenant_runtime_policies
            SET test_concurrency_limit = 2
            WHERE test_concurrency_limit = 10
            """
        )
    )
    op.alter_column(
        "artifact_tenant_runtime_policies",
        "test_concurrency_limit",
        existing_type=sa.Integer(),
        server_default="2",
        existing_nullable=False,
    )
