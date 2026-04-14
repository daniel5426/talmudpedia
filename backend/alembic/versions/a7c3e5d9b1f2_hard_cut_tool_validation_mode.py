"""hard cut tool validation mode

Revision ID: a7c3e5d9b1f2
Revises: 6f8e9d0c1b2a, a1b2c3d4e5f6, a4c9d2f7b6e1, a4c9e2b7d1f3, b8d1e2f3a4b5, d1e2f3a4b5c6, d1f4a8c9e2b7, d4e9f1a2b3c4, d9f3a7b1c2e4, f0e1d2c3b4a5, fb1c2d3e4f5a
Create Date: 2026-04-13 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c3e5d9b1f2"
down_revision: Union[str, Sequence[str], None] = (
    "6f8e9d0c1b2a",
    "a1b2c3d4e5f6",
    "a4c9d2f7b6e1",
    "a4c9e2b7d1f3",
    "b8d1e2f3a4b5",
    "d1e2f3a4b5c6",
    "d1f4a8c9e2b7",
    "d4e9f1a2b3c4",
    "d9f3a7b1c2e4",
    "f0e1d2c3b4a5",
    "fb1c2d3e4f5a",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        return set(inspector.get_table_names())
    except Exception:
        return set()


def _normalize_execution_config(config_schema: dict[str, object] | None) -> dict[str, object]:
    config = dict(config_schema or {})
    execution = config.get("execution")
    execution_dict = dict(execution) if isinstance(execution, dict) else {}
    legacy_strict = execution_dict.pop("strict_input_schema", None)
    validation_mode = str(execution_dict.get("validation_mode") or "").strip().lower()
    if validation_mode not in {"strict", "none"}:
        validation_mode = "none" if legacy_strict is False else "strict"
    execution_dict["validation_mode"] = validation_mode
    config["execution"] = execution_dict
    return config


def _backfill_config_schema(*, downgrade: bool) -> None:
    if "tool_registry" not in _table_names():
        return

    bind = op.get_bind()
    tool_registry = sa.table(
        "tool_registry",
        sa.column("id"),
        sa.column("config_schema", sa.JSON()),
    )
    rows = bind.execute(sa.select(tool_registry.c.id, tool_registry.c.config_schema)).mappings().all()
    for row in rows:
        config = dict(row["config_schema"] or {}) if isinstance(row["config_schema"], dict) else {}
        execution = dict(config.get("execution") or {}) if isinstance(config.get("execution"), dict) else {}
        if downgrade:
            validation_mode = str(execution.pop("validation_mode", "strict")).strip().lower()
            execution["strict_input_schema"] = validation_mode != "none"
        else:
            config = _normalize_execution_config(config)
            execution = dict(config.get("execution") or {})
        config["execution"] = execution
        bind.execute(
            tool_registry.update()
            .where(tool_registry.c.id == row["id"])
            .values(config_schema=config)
        )


def upgrade() -> None:
    _backfill_config_schema(downgrade=False)


def downgrade() -> None:
    _backfill_config_schema(downgrade=True)
