from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.engine import sessionmaker as get_session
from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.artifact_runtime import Artifact, ArtifactCodingSession, ArtifactCodingSharedDraft, ArtifactKind
from app.db.postgres.models.registry import IntegrationCredential, IntegrationCredentialCategory
from app.db.postgres.models.registry import (
    ToolDefinitionScope,
    ToolImplementationType,
    ToolRegistry,
    ToolStatus,
    set_tool_management_metadata,
)
from app.services.artifact_coding_shared_draft_service import ArtifactCodingSharedDraftService
from app.services.artifact_runtime.registry_service import ArtifactRegistryService
from app.services.tool_function_registry import register_tool_function

ARTIFACT_CODING_AGENT_SURFACE = "artifact_coding_agent"
ARTIFACT_CODING_TOOL_NAMESPACE = "artifact-coding-agent"

DEFAULT_CAPABILITIES = {
    "network_access": False,
    "allowed_hosts": [],
    "secret_refs": [],
    "storage_access": [],
    "side_effects": [],
}
DEFAULT_CONFIG_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": True}
DEFAULT_AGENT_CONTRACT = {
    "state_reads": [],
    "state_writes": [],
    "input_schema": {"type": "object", "properties": {"items": {"type": "array"}}, "additionalProperties": True},
    "output_schema": {"type": "object", "additionalProperties": True},
    "node_ui": {"title": "Agent Node"},
}
DEFAULT_RAG_CONTRACT = {
    "operator_category": "transform",
    "pipeline_role": "processor",
    "input_schema": {"type": "object", "additionalProperties": True},
    "output_schema": {"type": "object", "additionalProperties": True},
    "execution_mode": "background",
}
DEFAULT_TOOL_CONTRACT = {
    "input_schema": {"type": "object", "additionalProperties": True},
    "output_schema": {"type": "object", "additionalProperties": True},
    "side_effects": [],
    "execution_mode": "interactive",
    "tool_ui": {"title": "Tool"},
}
DEFAULT_SOURCE = """async def execute(inputs, config, context):
    items = inputs.get("items") if isinstance(inputs, dict) else inputs
    return {
        "items": items,
        "config": config,
        "tenant_id": context.get("tenant_id"),
    }
"""

DEFAULT_JS_SOURCE = """export async function execute(inputs, config, context) {
  const items = inputs?.items ?? inputs;
  return {
    items,
    config,
    tenant_id: context?.tenant_id ?? null,
  };
}
"""


def _normalize_language(language: str | None) -> str:
    raw = str(language or "python").strip().lower()
    if raw not in {"python", "javascript"}:
        raise ValueError("Unsupported artifact language")
    return raw


def _default_entry_module_for_language(language: str) -> str:
    return "main.js" if language == "javascript" else "main.py"


def _default_source_for_language(language: str) -> str:
    return DEFAULT_JS_SOURCE if language == "javascript" else DEFAULT_SOURCE


def _entry_module_extension_for_language(language: str) -> str:
    return ".js" if language == "javascript" else ".py"


def _validate_entry_module_language_compatibility(*, language: str, entry_module_path: str) -> None:
    normalized_language = _normalize_language(language)
    normalized_path = _normalize_path(entry_module_path)
    required_suffix = _entry_module_extension_for_language(normalized_language)
    if not normalized_path.endswith(required_suffix):
        raise ValueError(
            f"Entry module {normalized_path!r} is not compatible with artifact language {normalized_language!r}; "
            f"expected a path ending in {required_suffix}"
        )


def _initial_snapshot_for_kind(kind: str, *, language: str = "python") -> dict[str, Any]:
    normalized_kind = _normalize_kind(kind)
    normalized_language = _normalize_language(language)
    entry_module_path = _default_entry_module_for_language(normalized_language)
    return {
        "display_name": "",
        "description": "",
        "kind": normalized_kind,
        "language": normalized_language,
        "source_files": [{"path": entry_module_path, "content": _default_source_for_language(normalized_language)}],
        "entry_module_path": entry_module_path,
        "dependencies": "",
        "runtime_target": "cloudflare_workers",
        "capabilities": json.dumps(DEFAULT_CAPABILITIES, indent=2),
        "config_schema": json.dumps(DEFAULT_CONFIG_SCHEMA, indent=2),
        "agent_contract": json.dumps(DEFAULT_AGENT_CONTRACT, indent=2),
        "rag_contract": json.dumps(DEFAULT_RAG_CONTRACT, indent=2),
        "tool_contract": json.dumps(DEFAULT_TOOL_CONTRACT, indent=2),
    }


def _normalize_kind(kind: str | None) -> str:
    raw = str(kind or ArtifactKind.AGENT_NODE.value).strip().lower()
    if raw not in {item.value for item in ArtifactKind}:
        raise ValueError("Unsupported artifact kind")
    return raw


def _parse_uuid(value: Any, field: str) -> UUID:
    try:
        return UUID(str(value))
    except Exception as exc:
        raise ValueError(f"Invalid {field}") from exc


def _parse_json_object(value: Any, *, field: str, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if value is None:
        return deepcopy(fallback or {})
    if isinstance(value, dict):
        return deepcopy(value)
    text = str(value).strip()
    if not text:
        return deepcopy(fallback or {})
    try:
        parsed = json.loads(text)
    except Exception as exc:
        raise ValueError(f"{field} must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{field} must be a JSON object")
    return deepcopy(parsed)


def _format_json_object(value: dict[str, Any]) -> str:
    return json.dumps(value or {}, indent=2, sort_keys=False)


def _require_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _normalize_path(value: Any) -> str:
    path = _require_text(value, "path").replace("\\", "/").strip("/")
    if not path:
        raise ValueError("path is required")
    if path.startswith(".") or ".." in path.split("/"):
        raise ValueError("path is not allowed")
    return path


def _normalize_file_list(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    files = snapshot.get("source_files")
    normalized: list[dict[str, str]] = []
    if not isinstance(files, list):
        return normalized
    for item in files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        normalized.append({"path": _normalize_path(path), "content": str(item.get("content") or "")})
    return normalized


def _snapshot_source_index(snapshot: dict[str, Any]) -> dict[str, str]:
    return {item["path"]: item["content"] for item in _normalize_file_list(snapshot)}


def _replace_snapshot_files(snapshot: dict[str, Any], files_by_path: dict[str, str]) -> None:
    snapshot["source_files"] = [
        {"path": path, "content": files_by_path[path]}
        for path in sorted(files_by_path.keys())
    ]


def _current_contract_field(kind: str) -> str:
    if kind == ArtifactKind.AGENT_NODE.value:
        return "agent_contract"
    if kind == ArtifactKind.RAG_OPERATOR.value:
        return "rag_contract"
    return "tool_contract"


def _default_contract_for_kind(kind: str) -> dict[str, Any]:
    if kind == ArtifactKind.AGENT_NODE.value:
        return deepcopy(DEFAULT_AGENT_CONTRACT)
    if kind == ArtifactKind.RAG_OPERATOR.value:
        return deepcopy(DEFAULT_RAG_CONTRACT)
    return deepcopy(DEFAULT_TOOL_CONTRACT)


def _serialize_form_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    kind = _normalize_kind(snapshot.get("kind"))
    normalized = deepcopy(snapshot)
    normalized.setdefault("display_name", "")
    normalized.setdefault("description", "")
    normalized["kind"] = kind
    normalized["language"] = _normalize_language(normalized.get("language"))
    normalized["source_files"] = _normalize_file_list(normalized)
    default_entry_module = _default_entry_module_for_language(normalized["language"])
    normalized["entry_module_path"] = str(normalized.get("entry_module_path") or default_entry_module).strip() or default_entry_module
    _validate_entry_module_language_compatibility(
        language=normalized["language"],
        entry_module_path=normalized["entry_module_path"],
    )
    normalized["dependencies"] = str(normalized.get("dependencies") or normalized.get("python_dependencies") or "")
    normalized["runtime_target"] = str(normalized.get("runtime_target") or "cloudflare_workers")
    normalized["capabilities"] = _format_json_object(
        _parse_json_object(normalized.get("capabilities"), field="capabilities", fallback=DEFAULT_CAPABILITIES)
    )
    normalized["config_schema"] = _format_json_object(
        _parse_json_object(normalized.get("config_schema"), field="config_schema", fallback=DEFAULT_CONFIG_SCHEMA)
    )
    for field_name, default_value in (
        ("agent_contract", DEFAULT_AGENT_CONTRACT),
        ("rag_contract", DEFAULT_RAG_CONTRACT),
        ("tool_contract", DEFAULT_TOOL_CONTRACT),
    ):
        normalized[field_name] = _format_json_object(
            _parse_json_object(normalized.get(field_name), field=field_name, fallback=default_value)
        )
    return normalized


async def _resolve_session_context(
    db: AsyncSession,
    payload: dict[str, Any],
) -> tuple[ArtifactCodingSession, ArtifactCodingSharedDraft, AgentRun, Artifact | None]:
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    run_id_raw = payload.get("run_id") or context.get("run_id")
    if not run_id_raw:
        raise ValueError("run_id is required in tool context")
    run_id = _parse_uuid(run_id_raw, "run_id")
    run = await db.get(AgentRun, run_id)
    if run is None:
        raise ValueError("Run not found")
    if str(run.surface or "") != ARTIFACT_CODING_AGENT_SURFACE:
        raise PermissionError("Run is not an artifact-coding-agent run")

    input_context = run.input_params.get("context") if isinstance(run.input_params, dict) else {}
    if not isinstance(input_context, dict):
        input_context = {}
    session_id_raw = payload.get("artifact_coding_session_id") or context.get("artifact_coding_session_id") or input_context.get("artifact_coding_session_id")
    if not session_id_raw:
        raise ValueError("artifact_coding_session_id is required")
    session_id = _parse_uuid(session_id_raw, "artifact_coding_session_id")
    session = await db.get(ArtifactCodingSession, session_id)
    if session is None:
        raise ValueError("Artifact coding session not found")
    if session.tenant_id != run.tenant_id:
        raise PermissionError("Artifact coding session tenant mismatch")
    shared_draft_id_raw = (
        payload.get("artifact_coding_shared_draft_id")
        or context.get("artifact_coding_shared_draft_id")
        or input_context.get("artifact_coding_shared_draft_id")
    )
    if shared_draft_id_raw:
        shared_draft_id = _parse_uuid(shared_draft_id_raw, "artifact_coding_shared_draft_id")
        if shared_draft_id != session.shared_draft_id:
            raise PermissionError("Artifact coding shared draft mismatch")

    shared_draft = await ArtifactCodingSharedDraftService(db).resolve_for_session(session=session)

    artifact = None
    resolved_artifact_id = (
        shared_draft.artifact_id
        or shared_draft.linked_artifact_id
        or session.artifact_id
        or session.linked_artifact_id
    )
    if resolved_artifact_id is not None:
        artifact = await ArtifactRegistryService(db).get_tenant_artifact(
            artifact_id=resolved_artifact_id,
            tenant_id=session.tenant_id,
        )
    return session, shared_draft, run, artifact


async def _persist_snapshot_result(
    db: AsyncSession,
    *,
    shared_draft: ArtifactCodingSharedDraft,
    snapshot: dict[str, Any],
    changed_fields: list[str],
    summary: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    shared_draft.working_draft_snapshot = _serialize_form_state(snapshot)
    shared_draft.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {
        "ok": True,
        "summary": summary,
        "changed_fields": changed_fields,
        "draft_snapshot": deepcopy(shared_draft.working_draft_snapshot),
        **dict(extra or {}),
    }


@register_tool_function("artifact_coding_get_context")
async def artifact_coding_get_context(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        session, shared_draft, run, artifact = await _resolve_session_context(db, tool_payload)
        snapshot = _serialize_form_state(shared_draft.working_draft_snapshot or _initial_snapshot_for_kind("agent_node"))
        files = _normalize_file_list(snapshot)
        return {
            "artifact_id": str(artifact.id) if artifact else None,
            "has_persisted_artifact": artifact is not None,
            "is_create_mode": artifact is None,
            "session_id": str(session.id),
            "run_id": str(run.id),
            "draft_key": session.draft_key,
            "metadata": {
                "display_name": snapshot["display_name"],
                "description": snapshot["description"],
                "kind": snapshot["kind"],
                "language": snapshot["language"],
            },
            "runtime": {
                "entry_module_path": snapshot["entry_module_path"],
                "dependencies": snapshot["dependencies"],
                "runtime_target": snapshot["runtime_target"],
            },
            "file_count": len(files),
            "files": [{"path": item["path"], "bytes": len(item["content"].encode("utf-8"))} for item in files],
            "active_contract_field": _current_contract_field(snapshot["kind"]),
            "last_test_run_id": str(shared_draft.last_test_run_id) if shared_draft.last_test_run_id else None,
        }


@register_tool_function("artifact_coding_list_credentials")
async def artifact_coding_list_credentials(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        _session, _shared_draft, run, _artifact = await _resolve_session_context(db, tool_payload)
        stmt = (
            select(IntegrationCredential)
            .where(
                IntegrationCredential.tenant_id == run.tenant_id,
                IntegrationCredential.is_enabled == True,
                IntegrationCredential.category.in_(
                    [
                        IntegrationCredentialCategory.LLM_PROVIDER,
                        IntegrationCredentialCategory.VECTOR_STORE,
                        IntegrationCredentialCategory.TOOL_PROVIDER,
                        IntegrationCredentialCategory.CUSTOM,
                    ]
                ),
            )
            .order_by(
                IntegrationCredential.category.asc(),
                IntegrationCredential.provider_key.asc(),
                IntegrationCredential.display_name.asc(),
            )
        )
        credentials = (await db.execute(stmt)).scalars().all()
        return {
            "credentials": [
                {
                    "id": str(item.id),
                    "name": item.display_name,
                    "category": str(getattr(item.category, "value", item.category)),
                }
                for item in credentials
            ]
        }


@register_tool_function("artifact_coding_get_form_state")
async def artifact_coding_get_form_state(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        snapshot = _serialize_form_state(shared_draft.working_draft_snapshot or _initial_snapshot_for_kind("agent_node"))
        return {"draft_snapshot": snapshot}


@register_tool_function("artifact_coding_list_files")
async def artifact_coding_list_files(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        snapshot = _serialize_form_state(shared_draft.working_draft_snapshot or _initial_snapshot_for_kind("agent_node"))
        files = _normalize_file_list(snapshot)
        return {
            "files": [{"path": item["path"], "bytes": len(item["content"].encode("utf-8"))} for item in files],
            "entry_module_path": snapshot["entry_module_path"],
            "file_count": len(files),
        }


@register_tool_function("artifact_coding_read_file")
async def artifact_coding_read_file(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    path = _normalize_path(tool_payload.get("path"))
    async with get_session() as db:
        session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        files_by_path = _snapshot_source_index(_serialize_form_state(shared_draft.working_draft_snapshot))
        if path not in files_by_path:
            raise ValueError("File not found")
        return {"path": path, "content": files_by_path[path]}


@register_tool_function("artifact_coding_search_in_files")
async def artifact_coding_search_in_files(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    query = _require_text(tool_payload.get("query") or tool_payload.get("text"), "query")
    max_results = max(1, min(int(tool_payload.get("max_results") or 20), 100))
    async with get_session() as db:
        session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        snapshot = _serialize_form_state(shared_draft.working_draft_snapshot)
        matches: list[dict[str, Any]] = []
        for file in _normalize_file_list(snapshot):
            for index, line in enumerate(str(file["content"]).splitlines(), start=1):
                if query.lower() not in line.lower():
                    continue
                matches.append({"path": file["path"], "line": index, "content": line})
                if len(matches) >= max_results:
                    return {"query": query, "matches": matches}
        return {"query": query, "matches": matches}


@register_tool_function("artifact_coding_replace_file")
async def artifact_coding_replace_file(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    path = _normalize_path(tool_payload.get("path"))
    content = str(tool_payload.get("content") or "")
    async with get_session() as db:
        session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        snapshot = _serialize_form_state(shared_draft.working_draft_snapshot)
        files_by_path = _snapshot_source_index(snapshot)
        if path not in files_by_path:
            raise ValueError("File not found")
        files_by_path[path] = content
        _replace_snapshot_files(snapshot, files_by_path)
        return await _persist_snapshot_result(
            db,
            shared_draft=shared_draft,
            snapshot=snapshot,
            changed_fields=["source_files"],
            summary=f"Replaced {path}.",
            extra={"path": path},
        )


@register_tool_function("artifact_coding_update_file_range")
async def artifact_coding_update_file_range(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    path = _normalize_path(tool_payload.get("path"))
    start_line = int(tool_payload.get("start_line") or tool_payload.get("startLine") or 0)
    end_line = int(tool_payload.get("end_line") or tool_payload.get("endLine") or 0)
    if start_line < 1 or end_line < start_line:
        raise ValueError("start_line and end_line must define a valid inclusive range")
    new_text = str(tool_payload.get("new_text") or tool_payload.get("newText") or "")
    expected_old_text = tool_payload.get("expected_old_text") or tool_payload.get("expectedOldText")
    async with get_session() as db:
        session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        snapshot = _serialize_form_state(shared_draft.working_draft_snapshot)
        files_by_path = _snapshot_source_index(snapshot)
        if path not in files_by_path:
            raise ValueError("File not found")
        lines = files_by_path[path].splitlines()
        current_slice = "\n".join(lines[start_line - 1 : end_line])
        if expected_old_text is not None and str(expected_old_text) != current_slice:
            raise ValueError("expected_old_text does not match the current file content in the selected range")
        replacement_lines = new_text.splitlines()
        next_lines = lines[: start_line - 1] + replacement_lines + lines[end_line:]
        files_by_path[path] = "\n".join(next_lines)
        if files_by_path[path] and not files_by_path[path].endswith("\n"):
            files_by_path[path] += "\n"
        _replace_snapshot_files(snapshot, files_by_path)
        return await _persist_snapshot_result(
            db,
            shared_draft=shared_draft,
            snapshot=snapshot,
            changed_fields=["source_files"],
            summary=f"Updated lines {start_line}-{end_line} in {path}.",
            extra={"path": path, "start_line": start_line, "end_line": end_line},
        )


@register_tool_function("artifact_coding_create_file")
async def artifact_coding_create_file(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    path = _normalize_path(tool_payload.get("path"))
    content = str(tool_payload.get("content") or "")
    async with get_session() as db:
        session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        snapshot = _serialize_form_state(shared_draft.working_draft_snapshot)
        files_by_path = _snapshot_source_index(snapshot)
        if path in files_by_path:
            raise ValueError("File already exists")
        files_by_path[path] = content
        _replace_snapshot_files(snapshot, files_by_path)
        if not str(snapshot.get("entry_module_path") or "").strip():
            snapshot["entry_module_path"] = path
        return await _persist_snapshot_result(
            db,
            shared_draft=shared_draft,
            snapshot=snapshot,
            changed_fields=["source_files", "entry_module_path"] if snapshot["entry_module_path"] == path else ["source_files"],
            summary=f"Created {path}.",
            extra={"path": path},
        )


@register_tool_function("artifact_coding_delete_file")
async def artifact_coding_delete_file(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    path = _normalize_path(tool_payload.get("path"))
    async with get_session() as db:
        session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        snapshot = _serialize_form_state(shared_draft.working_draft_snapshot)
        files_by_path = _snapshot_source_index(snapshot)
        if path not in files_by_path:
            raise ValueError("File not found")
        if len(files_by_path) <= 1:
            raise ValueError("Cannot delete the last source file")
        del files_by_path[path]
        _replace_snapshot_files(snapshot, files_by_path)
        changed_fields = ["source_files"]
        if snapshot.get("entry_module_path") == path:
            snapshot["entry_module_path"] = next(iter(sorted(files_by_path.keys())))
            changed_fields.append("entry_module_path")
        return await _persist_snapshot_result(
            db,
            shared_draft=shared_draft,
            snapshot=snapshot,
            changed_fields=changed_fields,
            summary=f"Deleted {path}.",
            extra={"path": path},
        )


@register_tool_function("artifact_coding_rename_file")
async def artifact_coding_rename_file(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    from_path = _normalize_path(tool_payload.get("from_path") or tool_payload.get("fromPath"))
    to_path = _normalize_path(tool_payload.get("to_path") or tool_payload.get("toPath"))
    async with get_session() as db:
        session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        snapshot = _serialize_form_state(shared_draft.working_draft_snapshot)
        files_by_path = _snapshot_source_index(snapshot)
        if from_path not in files_by_path:
            raise ValueError("Source file not found")
        if to_path in files_by_path:
            raise ValueError("Destination file already exists")
        files_by_path[to_path] = files_by_path.pop(from_path)
        _replace_snapshot_files(snapshot, files_by_path)
        changed_fields = ["source_files"]
        if snapshot.get("entry_module_path") == from_path:
            snapshot["entry_module_path"] = to_path
            changed_fields.append("entry_module_path")
        return await _persist_snapshot_result(
            db,
            shared_draft=shared_draft,
            snapshot=snapshot,
            changed_fields=changed_fields,
            summary=f"Renamed {from_path} to {to_path}.",
            extra={"from_path": from_path, "to_path": to_path},
        )


@register_tool_function("artifact_coding_set_entry_module")
async def artifact_coding_set_entry_module(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    path = _normalize_path(tool_payload.get("path") or tool_payload.get("entry_module_path"))
    async with get_session() as db:
        session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        snapshot = _serialize_form_state(shared_draft.working_draft_snapshot)
        files_by_path = _snapshot_source_index(snapshot)
        if path not in files_by_path:
            raise ValueError("Entry module must reference an existing file")
        snapshot["entry_module_path"] = path
        return await _persist_snapshot_result(
            db,
            shared_draft=shared_draft,
            snapshot=snapshot,
            changed_fields=["entry_module_path"],
            summary=f"Set entry module to {path}.",
            extra={"path": path},
        )


@register_tool_function("artifact_coding_set_dependencies")
async def artifact_coding_set_dependencies(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    raw_dependencies = tool_payload.get("dependencies")
    if isinstance(raw_dependencies, str):
        dependencies = [item.strip() for item in raw_dependencies.split(",") if item.strip()]
    elif isinstance(raw_dependencies, list):
        dependencies = [str(item).strip() for item in raw_dependencies if str(item).strip()]
    else:
        dependencies = []
    async with get_session() as db:
        session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        snapshot = _serialize_form_state(shared_draft.working_draft_snapshot)
        snapshot["dependencies"] = ", ".join(dependencies)
        return await _persist_snapshot_result(
            db,
            shared_draft=shared_draft,
            snapshot=snapshot,
            changed_fields=["dependencies"],
            summary="Updated artifact dependencies.",
            extra={"dependencies": dependencies},
        )


@register_tool_function("artifact_coding_set_metadata")
async def artifact_coding_set_metadata(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    async with get_session() as db:
        session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        snapshot = _serialize_form_state(shared_draft.working_draft_snapshot)
        changed_fields: list[str] = []
        for field_name in ("display_name", "description"):
            if field_name not in tool_payload:
                continue
            snapshot[field_name] = str(tool_payload.get(field_name) or "")
            changed_fields.append(field_name)
        if not changed_fields:
            raise ValueError("At least one metadata field is required")
        return await _persist_snapshot_result(
            db,
            shared_draft=shared_draft,
            snapshot=snapshot,
            changed_fields=changed_fields,
            summary="Updated artifact metadata.",
        )


@register_tool_function("artifact_coding_set_kind")
async def artifact_coding_set_kind(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    target_kind = _normalize_kind(tool_payload.get("kind"))
    contract_payload = tool_payload.get("contract_payload") or tool_payload.get("contract")
    async with get_session() as db:
        session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        snapshot = _serialize_form_state(shared_draft.working_draft_snapshot)
        snapshot["kind"] = target_kind
        target_contract_field = _current_contract_field(target_kind)
        target_contract_value = (
            _parse_json_object(contract_payload, field=target_contract_field, fallback=_default_contract_for_kind(target_kind))
            if contract_payload is not None
            else _default_contract_for_kind(target_kind)
        )
        snapshot["agent_contract"] = _format_json_object(DEFAULT_AGENT_CONTRACT)
        snapshot["rag_contract"] = _format_json_object(DEFAULT_RAG_CONTRACT)
        snapshot["tool_contract"] = _format_json_object(DEFAULT_TOOL_CONTRACT)
        snapshot[target_contract_field] = _format_json_object(target_contract_value)
        return await _persist_snapshot_result(
            db,
            shared_draft=shared_draft,
            snapshot=snapshot,
            changed_fields=["kind", "agent_contract", "rag_contract", "tool_contract"],
            summary=f"Set artifact kind to {target_kind}.",
        )


@register_tool_function("artifact_coding_set_config_schema")
async def artifact_coding_set_config_schema(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    config_schema = _parse_json_object(
        tool_payload.get("config_schema") or tool_payload.get("value"),
        field="config_schema",
        fallback=DEFAULT_CONFIG_SCHEMA,
    )
    async with get_session() as db:
        session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        snapshot = _serialize_form_state(shared_draft.working_draft_snapshot)
        snapshot["config_schema"] = _format_json_object(config_schema)
        return await _persist_snapshot_result(
            db,
            shared_draft=shared_draft,
            snapshot=snapshot,
            changed_fields=["config_schema"],
            summary="Updated config schema.",
        )


@register_tool_function("artifact_coding_set_capabilities")
async def artifact_coding_set_capabilities(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    capabilities = _parse_json_object(
        tool_payload.get("capabilities") or tool_payload.get("value"),
        field="capabilities",
        fallback=DEFAULT_CAPABILITIES,
    )
    async with get_session() as db:
        session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        snapshot = _serialize_form_state(shared_draft.working_draft_snapshot)
        snapshot["capabilities"] = _format_json_object(capabilities)
        return await _persist_snapshot_result(
            db,
            shared_draft=shared_draft,
            snapshot=snapshot,
            changed_fields=["capabilities"],
            summary="Updated artifact capabilities.",
        )


@register_tool_function("artifact_coding_set_contract_payload")
async def artifact_coding_set_contract_payload(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    contract_field = str(tool_payload.get("contract_field") or "").strip()
    async with get_session() as db:
        session, shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        snapshot = _serialize_form_state(shared_draft.working_draft_snapshot)
        if not contract_field:
            contract_field = _current_contract_field(snapshot["kind"])
        if contract_field not in {"agent_contract", "rag_contract", "tool_contract"}:
            raise ValueError("Unsupported contract field")
        contract_value = _parse_json_object(
            tool_payload.get("contract_payload") or tool_payload.get("value"),
            field=contract_field,
            fallback=_default_contract_for_kind(snapshot["kind"]),
        )
        snapshot[contract_field] = _format_json_object(contract_value)
        return await _persist_snapshot_result(
            db,
            shared_draft=shared_draft,
            snapshot=snapshot,
            changed_fields=[contract_field],
            summary=f"Updated {contract_field}.",
        )


def _tool_schema(
    *,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "input": {
            "type": "object",
            "properties": properties,
            "required": list(required or []),
            "additionalProperties": True,
        },
        "output": {"type": "object", "additionalProperties": True},
    }


ARTIFACT_CODING_TOOL_SPECS: list[dict[str, Any]] = [
    {"slug": "artifact-coding-get-context", "name": "Artifact Coding Get Context", "description": "Get a compact summary of the current artifact coding session and draft.", "function_name": "artifact_coding_get_context", "timeout_s": 30, "is_pure": True, "schema": _tool_schema(properties={})},
    {"slug": "artifact-coding-get-form-state", "name": "Artifact Coding Get Form State", "description": "Read the full artifact draft form state.", "function_name": "artifact_coding_get_form_state", "timeout_s": 30, "is_pure": True, "schema": _tool_schema(properties={})},
    {"slug": "artifact-coding-list-files", "name": "Artifact Coding List Files", "description": "List files in the current artifact draft.", "function_name": "artifact_coding_list_files", "timeout_s": 30, "is_pure": True, "schema": _tool_schema(properties={})},
    {"slug": "artifact-coding-read-file", "name": "Artifact Coding Read File", "description": "Read one artifact draft file.", "function_name": "artifact_coding_read_file", "timeout_s": 30, "is_pure": True, "schema": _tool_schema(properties={"path": {"type": "string"}}, required=["path"])},
    {"slug": "artifact-coding-search-in-files", "name": "Artifact Coding Search In Files", "description": "Search text across artifact draft files.", "function_name": "artifact_coding_search_in_files", "timeout_s": 30, "is_pure": True, "schema": _tool_schema(properties={"query": {"type": "string"}, "max_results": {"type": "integer"}}, required=["query"])},
    {"slug": "artifact-coding-replace-file", "name": "Artifact Coding Replace File", "description": "Replace the full content of a draft file.", "function_name": "artifact_coding_replace_file", "timeout_s": 60, "is_pure": False, "schema": _tool_schema(properties={"path": {"type": "string"}, "content": {"type": "string"}}, required=["path", "content"])},
    {"slug": "artifact-coding-update-file-range", "name": "Artifact Coding Update File Range", "description": "Replace a line range in a draft file.", "function_name": "artifact_coding_update_file_range", "timeout_s": 60, "is_pure": False, "schema": _tool_schema(properties={"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}, "expected_old_text": {"type": "string"}, "new_text": {"type": "string"}}, required=["path", "start_line", "end_line", "new_text"])},
    {"slug": "artifact-coding-create-file", "name": "Artifact Coding Create File", "description": "Create a new draft file.", "function_name": "artifact_coding_create_file", "timeout_s": 60, "is_pure": False, "schema": _tool_schema(properties={"path": {"type": "string"}, "content": {"type": "string"}}, required=["path", "content"])},
    {"slug": "artifact-coding-delete-file", "name": "Artifact Coding Delete File", "description": "Delete a draft file.", "function_name": "artifact_coding_delete_file", "timeout_s": 60, "is_pure": False, "schema": _tool_schema(properties={"path": {"type": "string"}}, required=["path"])},
    {"slug": "artifact-coding-rename-file", "name": "Artifact Coding Rename File", "description": "Rename a draft file.", "function_name": "artifact_coding_rename_file", "timeout_s": 60, "is_pure": False, "schema": _tool_schema(properties={"from_path": {"type": "string"}, "to_path": {"type": "string"}}, required=["from_path", "to_path"])},
    {"slug": "artifact-coding-set-entry-module", "name": "Artifact Coding Set Entry Module", "description": "Set the entry module path.", "function_name": "artifact_coding_set_entry_module", "timeout_s": 30, "is_pure": False, "schema": _tool_schema(properties={"path": {"type": "string"}}, required=["path"])},
    {"slug": "artifact-coding-list-credentials", "name": "Artifact Coding List Credentials", "description": "List available credential references for the current tenant scope using safe metadata only.", "function_name": "artifact_coding_list_credentials", "timeout_s": 30, "is_pure": True, "schema": _tool_schema(properties={})},
    {"slug": "artifact-coding-set-dependencies", "name": "Artifact Coding Set Dependencies", "description": "Set artifact dependencies for the draft.", "function_name": "artifact_coding_set_dependencies", "timeout_s": 30, "is_pure": False, "schema": _tool_schema(properties={"dependencies": {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "string"}]}})},
    {"slug": "artifact-coding-set-metadata", "name": "Artifact Coding Set Metadata", "description": "Update artifact metadata fields.", "function_name": "artifact_coding_set_metadata", "timeout_s": 30, "is_pure": False, "schema": _tool_schema(properties={"display_name": {"type": "string"}, "description": {"type": "string"}})},
    {"slug": "artifact-coding-set-kind", "name": "Artifact Coding Set Kind", "description": "Change the artifact kind and contract shape.", "function_name": "artifact_coding_set_kind", "timeout_s": 30, "is_pure": False, "schema": _tool_schema(properties={"kind": {"type": "string", "enum": [item.value for item in ArtifactKind]}, "contract_payload": {"type": "object"}}, required=["kind"])},
    {"slug": "artifact-coding-set-config-schema", "name": "Artifact Coding Set Config Schema", "description": "Update the artifact config schema JSON.", "function_name": "artifact_coding_set_config_schema", "timeout_s": 30, "is_pure": False, "schema": _tool_schema(properties={"config_schema": {"type": "object"}}, required=["config_schema"])},
    {"slug": "artifact-coding-set-capabilities", "name": "Artifact Coding Set Capabilities", "description": "Update the artifact capabilities JSON.", "function_name": "artifact_coding_set_capabilities", "timeout_s": 30, "is_pure": False, "schema": _tool_schema(properties={"capabilities": {"type": "object"}}, required=["capabilities"])},
    {"slug": "artifact-coding-set-contract-payload", "name": "Artifact Coding Set Contract Payload", "description": "Update the active artifact contract JSON.", "function_name": "artifact_coding_set_contract_payload", "timeout_s": 30, "is_pure": False, "schema": _tool_schema(properties={"contract_field": {"type": "string", "enum": ["agent_contract", "rag_contract", "tool_contract"]}, "contract_payload": {"type": "object"}}, required=["contract_payload"])},
    {"slug": "artifact-coding-run-test", "name": "Artifact Coding Run Test", "description": "Run the artifact through the canonical artifact test runtime.", "function_name": "artifact_coding_run_test", "timeout_s": 60, "is_pure": False, "schema": _tool_schema(properties={"input_data": {}, "config": {"type": "object"}}, required=[])},
    {"slug": "artifact-coding-await-last-test-result", "name": "Artifact Coding Await Last Test Result", "description": "Wait server-side for the latest artifact test run to reach a terminal state.", "function_name": "artifact_coding_await_last_test_result", "timeout_s": 150, "is_pure": True, "schema": _tool_schema(properties={"timeout_seconds": {"type": "number"}}, required=[])},
    {"slug": "artifact-coding-get-last-test-result", "name": "Artifact Coding Get Last Test Result", "description": "Get the latest artifact test result for this session.", "function_name": "artifact_coding_get_last_test_result", "timeout_s": 30, "is_pure": True, "schema": _tool_schema(properties={})},
]
async def ensure_artifact_coding_tools(db: AsyncSession) -> list[str]:
    async def _has_modern_tool_registry_columns() -> bool:
        try:
            result = await db.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'tool_registry'
                      AND column_name IN ('artifact_id', 'artifact_version', 'artifact_revision_id')
                    """
                )
            )
            cols = {row[0] for row in result.all()}
            return {"artifact_id", "artifact_version", "artifact_revision_id"}.issubset(cols)
        except Exception:
            try:
                result = await db.execute(text("PRAGMA table_info(tool_registry)"))
                cols = {row[1] for row in result.all()}
                return {"artifact_id", "artifact_version", "artifact_revision_id"}.issubset(cols)
            except Exception:
                return False

    has_modern_columns = await _has_modern_tool_registry_columns()
    if not has_modern_columns:
        raise RuntimeError(
            "artifact coding tools require the current tool_registry schema; "
            "run the latest backend migrations before sending artifact coding prompts"
        )
    tool_ids: list[str] = []
    for spec in ARTIFACT_CODING_TOOL_SPECS:
        result = await db.execute(
            select(ToolRegistry).where(
                and_(
                    ToolRegistry.tenant_id.is_(None),
                    ToolRegistry.slug == spec["slug"],
                )
            )
        )
        tool = result.scalar_one_or_none()
        config_schema = {
            "implementation": {"type": "function", "function_name": spec["function_name"]},
            "execution": {
                "timeout_s": int(spec["timeout_s"]),
                "is_pure": bool(spec["is_pure"]),
                "concurrency_group": ARTIFACT_CODING_TOOL_NAMESPACE,
                "max_concurrency": 1,
            },
        }
        if tool is None:
            tool = ToolRegistry(
                tenant_id=None,
                name=spec["name"],
                slug=spec["slug"],
                description=spec["description"],
                scope=ToolDefinitionScope.GLOBAL,
                schema=spec["schema"],
                config_schema=config_schema,
                status=ToolStatus.PUBLISHED,
                version="1.0.0",
                implementation_type=ToolImplementationType.FUNCTION,
                artifact_id=None,
                artifact_version=None,
                builtin_key=None,
                builtin_template_id=None,
                is_builtin_template=False,
                is_active=True,
                is_system=True,
                published_at=datetime.now(timezone.utc),
            )
            set_tool_management_metadata(tool, ownership="system")
            db.add(tool)
            await db.flush()
        else:
            tool.name = spec["name"]
            tool.description = spec["description"]
            tool.scope = ToolDefinitionScope.GLOBAL
            tool.schema = spec["schema"]
            tool.config_schema = config_schema
            tool.status = ToolStatus.PUBLISHED
            tool.version = "1.0.0"
            tool.implementation_type = ToolImplementationType.FUNCTION
            tool.is_active = True
            tool.is_system = True
            tool.published_at = tool.published_at or datetime.now(timezone.utc)
            set_tool_management_metadata(tool, ownership="system")
        tool_ids.append(str(tool.id))
    await db.flush()
    return tool_ids
