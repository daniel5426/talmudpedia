"""update_agent_slug_uniqueness

Revision ID: 494b4ffe4e52
Revises: fad169b1b128
Create Date: 2026-01-18 22:39:46.906821

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '494b4ffe4e52'
down_revision: Union[str, None] = 'fad169b1b128'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = {index["name"]: index for index in inspector.get_indexes("agents")}
    unique_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("agents")}

    # Handle deploy drift safely: some databases already have the tenant-scoped
    # constraint even when Alembic still needs to apply this revision.
    slug_index = indexes.get("ix_agents_slug")
    if slug_index and slug_index.get("unique"):
        op.drop_index("ix_agents_slug", table_name="agents")

    if "uq_agent_tenant_slug" not in unique_constraints:
        op.create_unique_constraint("uq_agent_tenant_slug", "agents", ["tenant_id", "slug"])

    indexes = {index["name"]: index for index in inspect(bind).get_indexes("agents")}
    slug_index = indexes.get("ix_agents_slug")
    if not slug_index:
        op.create_index("ix_agents_slug", "agents", ["slug"], unique=False)
    elif slug_index.get("unique"):
        op.drop_index("ix_agents_slug", table_name="agents")
        op.create_index("ix_agents_slug", "agents", ["slug"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = {index["name"]: index for index in inspector.get_indexes("agents")}
    unique_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("agents")}

    slug_index = indexes.get("ix_agents_slug")
    if slug_index:
        op.drop_index("ix_agents_slug", table_name="agents")

    if "uq_agent_tenant_slug" in unique_constraints:
        op.drop_constraint("uq_agent_tenant_slug", "agents", type_="unique")

    indexes = {index["name"]: index for index in inspect(bind).get_indexes("agents")}
    slug_index = indexes.get("ix_agents_slug")
    if not slug_index:
        op.create_index("ix_agents_slug", "agents", ["slug"], unique=True)
    elif not slug_index.get("unique"):
        op.drop_index("ix_agents_slug", table_name="agents")
        op.create_index("ix_agents_slug", "agents", ["slug"], unique=True)
