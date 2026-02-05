"""normalize_tool_registry_enums

Revision ID: 6206ad312420
Revises: a13fc6223d86
Create Date: 2026-02-04 20:37:33.865606

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6206ad312420'
down_revision: Union[str, None] = 'a13fc6223d86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure enum types exist with uppercase values to match current data/model.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'toolstatus') THEN
                CREATE TYPE toolstatus AS ENUM ('DRAFT','PUBLISHED','DEPRECATED','DISABLED');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'toolimplementationtype') THEN
                CREATE TYPE toolimplementationtype AS ENUM ('INTERNAL','HTTP','RAG_RETRIEVAL','FUNCTION','CUSTOM','ARTIFACT','MCP');
            END IF;
        END$$;
        """
    )

    # Normalize column types if they are currently varchar/text.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'tool_registry'
                  AND column_name = 'status'
                  AND data_type IN ('character varying', 'text')
            ) THEN
                ALTER TABLE tool_registry ALTER COLUMN status DROP DEFAULT;
                ALTER TABLE tool_registry
                    ALTER COLUMN status TYPE toolstatus
                    USING status::toolstatus;
            END IF;

            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'tool_registry'
                  AND column_name = 'implementation_type'
                  AND data_type IN ('character varying', 'text')
            ) THEN
                ALTER TABLE tool_registry ALTER COLUMN implementation_type DROP DEFAULT;
                ALTER TABLE tool_registry
                    ALTER COLUMN implementation_type TYPE toolimplementationtype
                    USING implementation_type::toolimplementationtype;
            END IF;
        END$$;
        """
    )

    # Re-assert defaults to match model.
    op.execute(
        """
        ALTER TABLE tool_registry
            ALTER COLUMN status SET DEFAULT 'DRAFT'::toolstatus,
            ALTER COLUMN implementation_type SET DEFAULT 'CUSTOM'::toolimplementationtype;
        """
    )


def downgrade() -> None:
    # Downgrade back to varchar types if needed.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'tool_registry'
                  AND column_name = 'status'
                  AND udt_name = 'toolstatus'
            ) THEN
                ALTER TABLE tool_registry
                    ALTER COLUMN status TYPE varchar
                    USING status::text;
            END IF;

            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'tool_registry'
                  AND column_name = 'implementation_type'
                  AND udt_name = 'toolimplementationtype'
            ) THEN
                ALTER TABLE tool_registry
                    ALTER COLUMN implementation_type TYPE varchar
                    USING implementation_type::text;
            END IF;
        END$$;
        """
    )
