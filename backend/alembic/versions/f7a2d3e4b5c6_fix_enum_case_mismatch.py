"""fix enum case mismatch

Revision ID: f7a2d3e4b5c6
Revises: e1a2b3c4d5e6
Create Date: 2026-02-01 22:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f7a2d3e4b5c6'
down_revision: Union[str, None] = 'e1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Fix pipelinetype
    op.execute("ALTER TYPE pipelinetype RENAME VALUE 'INGESTION' TO 'ingestion'")
    op.execute("ALTER TYPE pipelinetype RENAME VALUE 'RETRIEVAL' TO 'retrieval'")

    # 2. Fix operatorcategory
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'SOURCE' TO 'source'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'NORMALIZATION' TO 'normalization'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'ENRICHMENT' TO 'enrichment'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'CHUNKING' TO 'chunking'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'EMBEDDING' TO 'embedding'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'STORAGE' TO 'storage'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'RETRIEVAL' TO 'retrieval'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'RERANKING' TO 'reranking'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'CUSTOM' TO 'custom'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'TRANSFORM' TO 'transform'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'LLM' TO 'llm'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'OUTPUT' TO 'output'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'CONTROL' TO 'control'")

    # 3. Fix pipelinestepstatus
    op.execute("ALTER TYPE pipelinestepstatus RENAME VALUE 'PENDING' TO 'pending'")
    op.execute("ALTER TYPE pipelinestepstatus RENAME VALUE 'RUNNING' TO 'running'")
    op.execute("ALTER TYPE pipelinestepstatus RENAME VALUE 'COMPLETED' TO 'completed'")
    op.execute("ALTER TYPE pipelinestepstatus RENAME VALUE 'FAILED' TO 'failed'")
    op.execute("ALTER TYPE pipelinestepstatus RENAME VALUE 'SKIPPED' TO 'skipped'")


def downgrade() -> None:
    # 1. Reverse pipelinetype
    op.execute("ALTER TYPE pipelinetype RENAME VALUE 'ingestion' TO 'INGESTION'")
    op.execute("ALTER TYPE pipelinetype RENAME VALUE 'retrieval' TO 'RETRIEVAL'")

    # 2. Reverse operatorcategory
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'source' TO 'SOURCE'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'normalization' TO 'NORMALIZATION'")
    # ... and so on. Given this is a fix, downgrade is less critical but good to have.
    # For brevity in this task, I'll just do the main ones or provide a way back.
    # Actually, I should probably do all for completeness.
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'enrichment' TO 'ENRICHMENT'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'chunking' TO 'CHUNKING'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'embedding' TO 'EMBEDDING'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'storage' TO 'STORAGE'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'retrieval' TO 'RETRIEVAL'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'reranking' TO 'RERANKING'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'custom' TO 'CUSTOM'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'transform' TO 'TRANSFORM'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'llm' TO 'LLM'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'output' TO 'OUTPUT'")
    op.execute("ALTER TYPE operatorcategory RENAME VALUE 'control' TO 'CONTROL'")

    # 3. Reverse pipelinestepstatus
    op.execute("ALTER TYPE pipelinestepstatus RENAME VALUE 'pending' TO 'PENDING'")
    op.execute("ALTER TYPE pipelinestepstatus RENAME VALUE 'running' TO 'RUNNING'")
    op.execute("ALTER TYPE pipelinestepstatus RENAME VALUE 'completed' TO 'COMPLETED'")
    op.execute("ALTER TYPE pipelinestepstatus RENAME VALUE 'failed' TO 'FAILED'")
    op.execute("ALTER TYPE pipelinestepstatus RENAME VALUE 'skipped' TO 'SKIPPED'")
