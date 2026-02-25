"""normalize tool enum labels to uppercase

Revision ID: d9f3a7b1c2e4
Revises: b7e2c1d9a4f3
Create Date: 2026-02-25 23:35:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d9f3a7b1c2e4"
down_revision: Union[str, Sequence[str], None] = "b7e2c1d9a4f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rename_enum_label_if_present(enum_name: str, old: str, new: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_type t
                JOIN pg_enum e ON e.enumtypid = t.oid
                WHERE t.typname = '{enum_name}' AND e.enumlabel = '{old}'
            )
            AND NOT EXISTS (
                SELECT 1
                FROM pg_type t
                JOIN pg_enum e ON e.enumtypid = t.oid
                WHERE t.typname = '{enum_name}' AND e.enumlabel = '{new}'
            ) THEN
                ALTER TYPE {enum_name} RENAME VALUE '{old}' TO '{new}';
            END IF;
        END$$;
        """
    )


def upgrade() -> None:
    # toolstatus
    _rename_enum_label_if_present("toolstatus", "draft", "DRAFT")
    _rename_enum_label_if_present("toolstatus", "published", "PUBLISHED")
    _rename_enum_label_if_present("toolstatus", "deprecated", "DEPRECATED")
    _rename_enum_label_if_present("toolstatus", "disabled", "DISABLED")

    # toolimplementationtype
    _rename_enum_label_if_present("toolimplementationtype", "internal", "INTERNAL")
    _rename_enum_label_if_present("toolimplementationtype", "http", "HTTP")
    _rename_enum_label_if_present("toolimplementationtype", "rag_retrieval", "RAG_RETRIEVAL")
    _rename_enum_label_if_present("toolimplementationtype", "agent_call", "AGENT_CALL")
    _rename_enum_label_if_present("toolimplementationtype", "function", "FUNCTION")
    _rename_enum_label_if_present("toolimplementationtype", "custom", "CUSTOM")
    _rename_enum_label_if_present("toolimplementationtype", "artifact", "ARTIFACT")
    _rename_enum_label_if_present("toolimplementationtype", "mcp", "MCP")


def downgrade() -> None:
    # toolstatus
    _rename_enum_label_if_present("toolstatus", "DRAFT", "draft")
    _rename_enum_label_if_present("toolstatus", "PUBLISHED", "published")
    _rename_enum_label_if_present("toolstatus", "DEPRECATED", "deprecated")
    _rename_enum_label_if_present("toolstatus", "DISABLED", "disabled")

    # toolimplementationtype
    _rename_enum_label_if_present("toolimplementationtype", "INTERNAL", "internal")
    _rename_enum_label_if_present("toolimplementationtype", "HTTP", "http")
    _rename_enum_label_if_present("toolimplementationtype", "RAG_RETRIEVAL", "rag_retrieval")
    _rename_enum_label_if_present("toolimplementationtype", "AGENT_CALL", "agent_call")
    _rename_enum_label_if_present("toolimplementationtype", "FUNCTION", "function")
    _rename_enum_label_if_present("toolimplementationtype", "CUSTOM", "custom")
    _rename_enum_label_if_present("toolimplementationtype", "ARTIFACT", "artifact")
    _rename_enum_label_if_present("toolimplementationtype", "MCP", "mcp")
