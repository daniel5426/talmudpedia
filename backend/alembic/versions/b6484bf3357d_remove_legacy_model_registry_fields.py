"""remove_legacy_model_registry_fields

Revision ID: b6484bf3357d
Revises: 577de8d73b46
Create Date: 2026-01-19 21:36:23.555579

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b6484bf3357d'
down_revision: Union[str, None] = '577de8d73b46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    model_registry_columns = {
        column["name"] for column in inspect(op.get_bind()).get_columns("model_registry")
    }

    for column_name in (
        "provider",
        "max_tokens",
        "cost_per_1k_output",
        "context_window",
        "cost_per_1k_input",
    ):
        if column_name in model_registry_columns:
            op.drop_column("model_registry", column_name)


def downgrade() -> None:
    model_registry_columns = {
        column["name"] for column in inspect(op.get_bind()).get_columns("model_registry")
    }

    if "cost_per_1k_input" not in model_registry_columns:
        op.add_column('model_registry', sa.Column('cost_per_1k_input', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True))
    if "context_window" not in model_registry_columns:
        op.add_column('model_registry', sa.Column('context_window', sa.INTEGER(), autoincrement=False, nullable=False))
    if "cost_per_1k_output" not in model_registry_columns:
        op.add_column('model_registry', sa.Column('cost_per_1k_output', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True))
    if "max_tokens" not in model_registry_columns:
        op.add_column('model_registry', sa.Column('max_tokens', sa.INTEGER(), autoincrement=False, nullable=False))
    if "provider" not in model_registry_columns:
        op.add_column('model_registry', sa.Column('provider', postgresql.ENUM('OPENAI', 'ANTHROPIC', 'GOOGLE', 'AZURE', 'CUSTOM', 'GEMINI', 'HUGGINGFACE', 'LOCAL', 'COHERE', 'GROQ', 'MISTRAL', 'TOGETHER', name='modelprovidertype'), autoincrement=False, nullable=True))
