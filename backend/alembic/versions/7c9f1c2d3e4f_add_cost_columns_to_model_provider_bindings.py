"""add_cost_columns_to_model_provider_bindings

Revision ID: 7c9f1c2d3e4f
Revises: 6206ad312420
Create Date: 2026-02-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c9f1c2d3e4f'
down_revision: Union[str, None] = '6206ad312420'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'model_provider_bindings',
        sa.Column('cost_per_1k_input_tokens', sa.Float(), nullable=True),
    )
    op.add_column(
        'model_provider_bindings',
        sa.Column('cost_per_1k_output_tokens', sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('model_provider_bindings', 'cost_per_1k_output_tokens')
    op.drop_column('model_provider_bindings', 'cost_per_1k_input_tokens')
