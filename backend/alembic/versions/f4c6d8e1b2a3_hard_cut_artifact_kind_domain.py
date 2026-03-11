"""hard cut artifact domain to explicit kinds

Revision ID: f4c6d8e1b2a3
Revises: f2b3c4d5e6f7
Create Date: 2026-03-11 16:40:00.000000

"""
from __future__ import annotations

from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f4c6d8e1b2a3"
down_revision: Union[str, Sequence[str], None] = "f2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


artifact_scope_enum = postgresql.ENUM("rag", "agent", "both", "tool", name="artifactscope", create_type=False)
artifact_kind_enum = postgresql.ENUM("agent_node", "rag_operator", "tool_impl", name="artifactkind", create_type=False)
artifact_owner_type_enum = postgresql.ENUM("tenant", "system", name="artifactownertype", create_type=False)


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        return {col["name"] for col in inspector.get_columns(table_name)}
    except Exception:
        return set()


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        return {idx["name"] for idx in inspector.get_indexes(table_name) if idx.get("name")}
    except Exception:
        return set()


def _pg_type_exists(type_name: str) -> bool:
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_type
            WHERE typname = :type_name
            LIMIT 1
            """
        ),
        {"type_name": type_name},
    ).first()
    return row is not None


def _normalize_type_name(raw: Any) -> str | None:
    value = str(raw or "").strip().lower()
    if not value:
        return None
    if value in {"str", "string", "text"}:
        return "string"
    if value in {"int", "integer"}:
        return "integer"
    if value in {"float", "number", "decimal"}:
        return "number"
    if value in {"bool", "boolean"}:
        return "boolean"
    if value in {"array", "list"}:
        return "array"
    if value in {"object", "dict", "map"}:
        return "object"
    return None


def _schema_from_legacy_fields(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        if value.get("type") == "object" or "properties" in value:
            schema = dict(value)
            schema.setdefault("type", "object")
            schema.setdefault("properties", {})
            return schema
        return {
            "type": "object",
            "properties": dict(value),
        }

    properties: dict[str, Any] = {}
    required: list[str] = []
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("id") or "").strip()
            if not name:
                continue
            prop_schema: dict[str, Any] = {}
            normalized_type = _normalize_type_name(item.get("type"))
            legacy_type = str(item.get("type") or "").strip()
            if normalized_type:
                prop_schema["type"] = normalized_type
            elif legacy_type:
                prop_schema["x-legacy-type"] = legacy_type
            if item.get("description"):
                prop_schema["description"] = item["description"]
            if "default" in item:
                prop_schema["default"] = item["default"]
            if isinstance(item.get("enum"), list):
                prop_schema["enum"] = list(item["enum"])
            properties[name] = prop_schema
            if bool(item.get("required")):
                required.append(name)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = sorted(set(required))
    return schema


def _schema_to_legacy_fields(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    properties = value.get("properties")
    if not isinstance(properties, dict):
        return []
    required = set(value.get("required") or [])
    fields: list[dict[str, Any]] = []
    for name, prop in properties.items():
        field: dict[str, Any] = {"name": name}
        if isinstance(prop, dict):
            if "type" in prop:
                field["type"] = prop["type"]
            elif "x-legacy-type" in prop:
                field["type"] = prop["x-legacy-type"]
            if "description" in prop:
                field["description"] = prop["description"]
            if "default" in prop:
                field["default"] = prop["default"]
            if "enum" in prop and isinstance(prop["enum"], list):
                field["enum"] = list(prop["enum"])
        field["required"] = name in required
        fields.append(field)
    return fields


def _fallback_schema_from_io_type(raw: Any) -> dict[str, Any]:
    value = str(raw or "").strip()
    if not value:
        return {"type": "object", "properties": {}}
    normalized_type = _normalize_type_name(value)
    if normalized_type:
        return {"type": normalized_type}
    return {
        "type": "object",
        "x-legacy-data-type": value,
        "properties": {},
    }


def _base_capabilities() -> dict[str, Any]:
    return {
        "network_access": False,
        "allowed_hosts": [],
        "secret_refs": [],
        "storage_access": [],
        "side_effects": [],
    }


def _kind_from_legacy(scope: Any, reads: Any, writes: Any) -> str:
    scope_value = str(scope or "").strip().lower()
    read_values = reads if isinstance(reads, list) else []
    write_values = writes if isinstance(writes, list) else []
    if scope_value == "tool":
        return "tool_impl"
    if scope_value == "agent":
        return "agent_node"
    if scope_value == "both" and (read_values or write_values):
        return "agent_node"
    return "rag_operator"


def _scope_from_kind(kind: Any) -> str:
    kind_value = str(kind or "").strip().lower()
    if kind_value == "tool_impl":
        return "tool"
    if kind_value == "agent_node":
        return "agent"
    return "rag"


def _artifact_category_from_contracts(
    *,
    kind: Any,
    agent_contract: Any,
    rag_contract: Any,
    tool_contract: Any,
) -> str:
    kind_value = str(kind or "").strip().lower()
    if kind_value == "agent_node" and isinstance(agent_contract, dict):
        node_ui = agent_contract.get("node_ui")
        if isinstance(node_ui, dict) and node_ui.get("category"):
            return str(node_ui["category"])
        return "control"
    if kind_value == "tool_impl":
        return "tool"
    if isinstance(rag_contract, dict) and rag_contract.get("operator_category"):
        return str(rag_contract["operator_category"])
    return "transform"


def _io_type_from_schema(value: Any, default: str = "any") -> str:
    if not isinstance(value, dict):
        return default
    if value.get("x-legacy-data-type"):
        return str(value["x-legacy-data-type"])
    if value.get("x-legacy-type"):
        return str(value["x-legacy-type"])
    if value.get("type"):
        return str(value["type"])
    return default


def _ensure_artifact_domain_columns() -> None:
    bind = op.get_bind()
    if not _pg_type_exists("artifactkind"):
        artifact_kind_enum.create(bind, checkfirst=False)
    if not _pg_type_exists("artifactownertype"):
        artifact_owner_type_enum.create(bind, checkfirst=False)

    artifact_columns = _column_names("artifacts")
    if "kind" not in artifact_columns:
        op.add_column(
            "artifacts",
            sa.Column("kind", artifact_kind_enum, nullable=True, server_default="rag_operator"),
        )
    if "owner_type" not in artifact_columns:
        op.add_column(
            "artifacts",
            sa.Column("owner_type", artifact_owner_type_enum, nullable=True, server_default="tenant"),
        )
    if "system_key" not in artifact_columns:
        op.add_column("artifacts", sa.Column("system_key", sa.String(), nullable=True))

    revision_columns = _column_names("artifact_revisions")
    if "kind" not in revision_columns:
        op.add_column(
            "artifact_revisions",
            sa.Column("kind", artifact_kind_enum, nullable=True, server_default="rag_operator"),
        )
    if "runtime_target" not in revision_columns:
        op.add_column(
            "artifact_revisions",
            sa.Column("runtime_target", sa.String(), nullable=False, server_default="cloudflare_workers"),
        )
    if "capabilities" not in revision_columns:
        op.add_column(
            "artifact_revisions",
            sa.Column(
                "capabilities",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )
    if "agent_contract" not in revision_columns:
        op.add_column(
            "artifact_revisions",
            sa.Column("agent_contract", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
    if "rag_contract" not in revision_columns:
        op.add_column(
            "artifact_revisions",
            sa.Column("rag_contract", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
    if "tool_contract" not in revision_columns:
        op.add_column(
            "artifact_revisions",
            sa.Column("tool_contract", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def _backfill_revisions_to_kind_model() -> None:
    bind = op.get_bind()
    revision_table = sa.table(
        "artifact_revisions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("kind", artifact_kind_enum),
        sa.column("runtime_target", sa.String()),
        sa.column("capabilities", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("config_schema", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("agent_contract", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("rag_contract", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("tool_contract", postgresql.JSONB(astext_type=sa.Text())),
    )

    rows = bind.execute(
        sa.text(
            """
            SELECT
                id,
                category,
                input_type,
                output_type,
                scope,
                config_schema,
                inputs,
                outputs,
                reads,
                writes
            FROM artifact_revisions
            """
        )
    ).mappings().all()

    for row in rows:
        config_schema = _schema_from_legacy_fields(row.get("config_schema"))
        input_schema = _schema_from_legacy_fields(row.get("inputs"))
        output_schema = _schema_from_legacy_fields(row.get("outputs"))
        if not input_schema.get("properties") and input_schema.get("type") == "object":
            input_schema = _fallback_schema_from_io_type(row.get("input_type"))
        if not output_schema.get("properties") and output_schema.get("type") == "object":
            output_schema = _fallback_schema_from_io_type(row.get("output_type"))

        kind = _kind_from_legacy(row.get("scope"), row.get("reads"), row.get("writes"))
        agent_contract = None
        rag_contract = None
        tool_contract = None

        if kind == "agent_node":
            agent_contract = {
                "state_reads": list(row.get("reads") or []),
                "state_writes": list(row.get("writes") or []),
                "input_schema": input_schema,
                "output_schema": output_schema,
                "node_ui": {"category": str(row.get("category") or "control")},
            }
        elif kind == "tool_impl":
            tool_contract = {
                "input_schema": input_schema,
                "output_schema": output_schema,
                "side_effects": [],
                "execution_mode": "interactive",
                "tool_ui": {"category": str(row.get("category") or "tool")},
            }
        else:
            rag_contract = {
                "operator_category": str(row.get("category") or "transform"),
                "pipeline_role": "processor",
                "input_schema": input_schema,
                "output_schema": output_schema,
                "execution_mode": "background",
            }

        bind.execute(
            revision_table.update()
            .where(revision_table.c.id == row["id"])
            .values(
                kind=kind,
                runtime_target="cloudflare_workers",
                capabilities=_base_capabilities(),
                config_schema=config_schema,
                agent_contract=agent_contract,
                rag_contract=rag_contract,
                tool_contract=tool_contract,
            )
        )


def _backfill_artifacts_to_kind_model() -> None:
    bind = op.get_bind()
    artifact_table = sa.table(
        "artifacts",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("kind", artifact_kind_enum),
        sa.column("owner_type", artifact_owner_type_enum),
        sa.column("system_key", sa.String()),
    )

    rows = bind.execute(
        sa.text(
            """
            SELECT
                a.id,
                a.scope,
                a.latest_draft_revision_id,
                a.latest_published_revision_id,
                COALESCE(d.kind, p.kind) AS resolved_kind
            FROM artifacts AS a
            LEFT JOIN artifact_revisions AS d ON d.id = a.latest_draft_revision_id
            LEFT JOIN artifact_revisions AS p ON p.id = a.latest_published_revision_id
            """
        )
    ).mappings().all()

    for row in rows:
        kind = row.get("resolved_kind") or _kind_from_legacy(row.get("scope"), [], [])
        bind.execute(
            artifact_table.update()
            .where(artifact_table.c.id == row["id"])
            .values(
                kind=kind,
                owner_type="tenant",
                system_key=None,
            )
        )


def _drop_legacy_artifact_columns() -> None:
    artifact_columns = _column_names("artifacts")
    for column_name in ("category", "input_type", "output_type", "scope"):
        if column_name in artifact_columns:
            op.drop_column("artifacts", column_name)

    revision_columns = _column_names("artifact_revisions")
    for column_name in ("category", "input_type", "output_type", "scope", "inputs", "outputs", "reads", "writes"):
        if column_name in revision_columns:
            op.drop_column("artifact_revisions", column_name)


def _restore_legacy_artifact_columns() -> None:
    bind = op.get_bind()
    if not _pg_type_exists("artifactscope"):
        artifact_scope_enum.create(bind, checkfirst=False)

    artifact_columns = _column_names("artifacts")
    if "category" not in artifact_columns:
        op.add_column("artifacts", sa.Column("category", sa.String(), nullable=True))
    if "input_type" not in artifact_columns:
        op.add_column("artifacts", sa.Column("input_type", sa.String(), nullable=True))
    if "output_type" not in artifact_columns:
        op.add_column("artifacts", sa.Column("output_type", sa.String(), nullable=True))
    if "scope" not in artifact_columns:
        op.add_column("artifacts", sa.Column("scope", artifact_scope_enum, nullable=True))

    revision_columns = _column_names("artifact_revisions")
    if "category" not in revision_columns:
        op.add_column("artifact_revisions", sa.Column("category", sa.String(), nullable=True))
    if "input_type" not in revision_columns:
        op.add_column("artifact_revisions", sa.Column("input_type", sa.String(), nullable=True))
    if "output_type" not in revision_columns:
        op.add_column("artifact_revisions", sa.Column("output_type", sa.String(), nullable=True))
    if "scope" not in revision_columns:
        op.add_column("artifact_revisions", sa.Column("scope", artifact_scope_enum, nullable=True))
    if "inputs" not in revision_columns:
        op.add_column(
            "artifact_revisions",
            sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
    if "outputs" not in revision_columns:
        op.add_column(
            "artifact_revisions",
            sa.Column("outputs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
    if "reads" not in revision_columns:
        op.add_column(
            "artifact_revisions",
            sa.Column("reads", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
    if "writes" not in revision_columns:
        op.add_column(
            "artifact_revisions",
            sa.Column("writes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def _backfill_revisions_to_scope_model() -> None:
    bind = op.get_bind()
    revision_table = sa.table(
        "artifact_revisions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("category", sa.String()),
        sa.column("input_type", sa.String()),
        sa.column("output_type", sa.String()),
        sa.column("scope", artifact_scope_enum),
        sa.column("config_schema", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("inputs", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("outputs", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("reads", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("writes", postgresql.JSONB(astext_type=sa.Text())),
    )

    rows = bind.execute(
        sa.text(
            """
            SELECT
                id,
                kind,
                config_schema,
                agent_contract,
                rag_contract,
                tool_contract
            FROM artifact_revisions
            """
        )
    ).mappings().all()

    for row in rows:
        kind = row.get("kind")
        agent_contract = row.get("agent_contract") if isinstance(row.get("agent_contract"), dict) else {}
        rag_contract = row.get("rag_contract") if isinstance(row.get("rag_contract"), dict) else {}
        tool_contract = row.get("tool_contract") if isinstance(row.get("tool_contract"), dict) else {}

        contract_schema = agent_contract.get("input_schema") or rag_contract.get("input_schema") or tool_contract.get("input_schema")
        contract_output_schema = agent_contract.get("output_schema") or rag_contract.get("output_schema") or tool_contract.get("output_schema")
        config_schema = _schema_to_legacy_fields(row.get("config_schema"))
        inputs = _schema_to_legacy_fields(contract_schema)
        outputs = _schema_to_legacy_fields(contract_output_schema)
        reads = list(agent_contract.get("state_reads") or []) if kind == "agent_node" else []
        writes = list(agent_contract.get("state_writes") or []) if kind == "agent_node" else []

        bind.execute(
            revision_table.update()
            .where(revision_table.c.id == row["id"])
            .values(
                category=_artifact_category_from_contracts(
                    kind=kind,
                    agent_contract=agent_contract,
                    rag_contract=rag_contract,
                    tool_contract=tool_contract,
                ),
                input_type=_io_type_from_schema(contract_schema),
                output_type=_io_type_from_schema(contract_output_schema),
                scope=_scope_from_kind(kind),
                config_schema=config_schema,
                inputs=inputs,
                outputs=outputs,
                reads=reads,
                writes=writes,
            )
        )


def _backfill_artifacts_to_scope_model() -> None:
    bind = op.get_bind()
    artifact_table = sa.table(
        "artifacts",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("category", sa.String()),
        sa.column("input_type", sa.String()),
        sa.column("output_type", sa.String()),
        sa.column("scope", artifact_scope_enum),
    )

    rows = bind.execute(
        sa.text(
            """
            SELECT
                a.id,
                a.kind,
                COALESCE(d.agent_contract, p.agent_contract) AS agent_contract,
                COALESCE(d.rag_contract, p.rag_contract) AS rag_contract,
                COALESCE(d.tool_contract, p.tool_contract) AS tool_contract
            FROM artifacts AS a
            LEFT JOIN artifact_revisions AS d ON d.id = a.latest_draft_revision_id
            LEFT JOIN artifact_revisions AS p ON p.id = a.latest_published_revision_id
            """
        )
    ).mappings().all()

    for row in rows:
        agent_contract = row.get("agent_contract") if isinstance(row.get("agent_contract"), dict) else {}
        rag_contract = row.get("rag_contract") if isinstance(row.get("rag_contract"), dict) else {}
        tool_contract = row.get("tool_contract") if isinstance(row.get("tool_contract"), dict) else {}
        contract_schema = agent_contract.get("input_schema") or rag_contract.get("input_schema") or tool_contract.get("input_schema")
        contract_output_schema = agent_contract.get("output_schema") or rag_contract.get("output_schema") or tool_contract.get("output_schema")

        bind.execute(
            artifact_table.update()
            .where(artifact_table.c.id == row["id"])
            .values(
                category=_artifact_category_from_contracts(
                    kind=row.get("kind"),
                    agent_contract=agent_contract,
                    rag_contract=rag_contract,
                    tool_contract=tool_contract,
                ),
                input_type=_io_type_from_schema(contract_schema),
                output_type=_io_type_from_schema(contract_output_schema),
                scope=_scope_from_kind(row.get("kind")),
            )
        )


def upgrade() -> None:
    _ensure_artifact_domain_columns()

    op.alter_column("artifacts", "tenant_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.alter_column("artifact_revisions", "tenant_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)

    _backfill_revisions_to_kind_model()
    _backfill_artifacts_to_kind_model()

    op.alter_column("artifacts", "kind", existing_type=artifact_kind_enum, nullable=False)
    op.alter_column("artifacts", "owner_type", existing_type=artifact_owner_type_enum, nullable=False)
    op.alter_column("artifact_revisions", "kind", existing_type=artifact_kind_enum, nullable=False)
    op.alter_column("artifact_revisions", "runtime_target", existing_type=sa.String(), nullable=False)
    op.alter_column("artifact_revisions", "capabilities", existing_type=postgresql.JSONB(astext_type=sa.Text()), nullable=False)

    op.alter_column("artifacts", "kind", existing_type=artifact_kind_enum, server_default=None)
    op.alter_column("artifacts", "owner_type", existing_type=artifact_owner_type_enum, server_default=None)
    op.alter_column("artifact_revisions", "kind", existing_type=artifact_kind_enum, server_default=None)
    op.alter_column("artifact_revisions", "runtime_target", existing_type=sa.String(), server_default=None)
    op.alter_column("artifact_revisions", "capabilities", existing_type=postgresql.JSONB(astext_type=sa.Text()), server_default=None)

    if "uq_artifacts_system_key" not in _index_names("artifacts"):
        op.create_index("uq_artifacts_system_key", "artifacts", ["system_key"], unique=True)

    _drop_legacy_artifact_columns()

    if _pg_type_exists("artifactscope"):
        artifact_scope_enum.drop(op.get_bind(), checkfirst=False)


def downgrade() -> None:
    _restore_legacy_artifact_columns()
    _backfill_revisions_to_scope_model()
    _backfill_artifacts_to_scope_model()

    op.alter_column("artifacts", "category", existing_type=sa.String(), nullable=False)
    op.alter_column("artifacts", "input_type", existing_type=sa.String(), nullable=False)
    op.alter_column("artifacts", "output_type", existing_type=sa.String(), nullable=False)
    op.alter_column("artifacts", "scope", existing_type=artifact_scope_enum, nullable=False)
    op.alter_column("artifact_revisions", "category", existing_type=sa.String(), nullable=False)
    op.alter_column("artifact_revisions", "input_type", existing_type=sa.String(), nullable=False)
    op.alter_column("artifact_revisions", "output_type", existing_type=sa.String(), nullable=False)
    op.alter_column("artifact_revisions", "scope", existing_type=artifact_scope_enum, nullable=False)
    op.alter_column("artifact_revisions", "inputs", existing_type=postgresql.JSONB(astext_type=sa.Text()), nullable=False)
    op.alter_column("artifact_revisions", "outputs", existing_type=postgresql.JSONB(astext_type=sa.Text()), nullable=False)
    op.alter_column("artifact_revisions", "reads", existing_type=postgresql.JSONB(astext_type=sa.Text()), nullable=False)
    op.alter_column("artifact_revisions", "writes", existing_type=postgresql.JSONB(astext_type=sa.Text()), nullable=False)

    if "uq_artifacts_system_key" in _index_names("artifacts"):
        op.drop_index("uq_artifacts_system_key", table_name="artifacts")

    artifact_columns = _column_names("artifacts")
    for column_name in ("system_key", "owner_type", "kind"):
        if column_name in artifact_columns:
            op.drop_column("artifacts", column_name)

    revision_columns = _column_names("artifact_revisions")
    for column_name in ("tool_contract", "rag_contract", "agent_contract", "capabilities", "runtime_target", "kind"):
        if column_name in revision_columns:
            op.drop_column("artifact_revisions", column_name)

    if _pg_type_exists("artifactownertype"):
        artifact_owner_type_enum.drop(op.get_bind(), checkfirst=False)
    if _pg_type_exists("artifactkind"):
        artifact_kind_enum.drop(op.get_bind(), checkfirst=False)
