from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionMode
from app.db.postgres.engine import sessionmaker as get_session
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.artifact_runtime import ArtifactRun
from app.db.postgres.models.registry import ToolDefinitionScope, ToolImplementationType, ToolRegistry, ToolStatus
from app.services.artifact_coding_runtime_service import ArtifactCodingRuntimeService
from app.services.artifact_coding_agent_profile import (
    ARTIFACT_CODING_AGENT_PROFILE_SLUG,
    ensure_artifact_coding_agent_profile,
)
from app.services.tool_function_registry import register_tool_function


ARCHITECT_ARTIFACT_DELEGATION_NAMESPACE = "platform-architect-artifact-delegation"


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


_UUID_FIELD_RE_TEMPLATE = r'"{field}"\s*:\s*"([^"]+)"'


def _parse_json_object_loose(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    candidates = [text]
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            candidates.append(parts[1].replace("json", "", 1).strip())
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    return None


def _extract_uuid_field_from_wrapped_text(raw: Any, field: str) -> str | None:
    if not isinstance(raw, str):
        return None
    match = re.search(_UUID_FIELD_RE_TEMPLATE.format(field=re.escape(field)), raw)
    if not match:
        return None
    value = str(match.group(1) or "").strip()
    return value or None


def _normalize_artifact_coding_call_payload(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    normalized = dict(tool_payload)

    nested_context = dict(normalized.get("context")) if isinstance(normalized.get("context"), dict) else {}
    for wrapper_key in ("value", "query", "text"):
        parsed = _parse_json_object_loose(normalized.get(wrapper_key))
        if isinstance(parsed, dict):
            for key, value in parsed.items():
                if key == "context" and isinstance(value, dict):
                    nested_context = {**value, **nested_context}
                    continue
                if key not in normalized:
                    normalized[key] = value
        elif "chat_session_id" not in normalized and "chat_session_id" not in nested_context:
            extracted_session_id = _extract_uuid_field_from_wrapped_text(normalized.get(wrapper_key), "chat_session_id")
            if extracted_session_id:
                normalized["chat_session_id"] = extracted_session_id

    if nested_context:
        normalized["context"] = nested_context
    return normalized


def _context_uuid(payload: dict[str, Any], field: str, *, required: bool) -> UUID | None:
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    raw = payload.get(field) or context.get(field)
    if raw in (None, ""):
        if required:
            raise ValueError(f"{field} is required")
        return None
    try:
        return UUID(str(raw))
    except Exception as exc:
        raise ValueError(f"Invalid {field}") from exc


def _context_text(payload: dict[str, Any], field: str) -> str | None:
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    raw = payload.get(field) or context.get(field)
    text = str(raw or "").strip()
    return text or None


async def _resolve_latest_session_id_for_user(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
) -> UUID | None:
    from app.db.postgres.models.agent_threads import AgentThread
    from app.db.postgres.models.artifact_runtime import ArtifactCodingSession

    result = await db.execute(
        select(ArtifactCodingSession.id)
        .join(AgentThread, ArtifactCodingSession.agent_thread_id == AgentThread.id)
        .where(
            and_(
                ArtifactCodingSession.tenant_id == tenant_id,
                AgentThread.user_id == user_id,
            )
        )
        .order_by(ArtifactCodingSession.last_message_at.desc(), ArtifactCodingSession.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _serialize_prepare_result(
    *,
    runtime_state: dict[str, Any],
    active_run_id: str | None,
    active_run_status: str | None,
) -> dict[str, Any]:
    return {
        **runtime_state,
        "active_run_id": active_run_id,
        "active_run_status": active_run_status,
        "has_active_run": bool(
            active_run_id
            and active_run_status not in {
                RunStatus.completed.value,
                RunStatus.failed.value,
                RunStatus.cancelled.value,
            }
        ),
    }


def _compose_architect_artifact_coding_prompt(payload: dict[str, Any]) -> str:
    raw_input = payload.get("input")
    if isinstance(raw_input, str) and raw_input.strip():
        return raw_input.strip()

    messages = payload.get("messages")
    if isinstance(messages, list):
        parts: list[str] = []
        for item in messages:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            if role == "system":
                parts.append(f"System instructions:\n{content}")
            elif role == "user":
                parts.append(f"User request:\n{content}")
            else:
                parts.append(content)
        prompt = "\n\n".join(part for part in parts if part.strip())
        if prompt:
            return prompt

    raise ValueError("artifact coding prompt input is required")


@register_tool_function("artifact_coding_session_prepare")
async def artifact_coding_session_prepare(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    tenant_id = _context_uuid(tool_payload, "tenant_id", required=True)
    user_id = _context_uuid(tool_payload, "user_id", required=True)
    chat_session_id = _context_uuid(tool_payload, "chat_session_id", required=False)
    artifact_id = _context_uuid(tool_payload, "artifact_id", required=False)
    draft_key = _context_text(tool_payload, "draft_key")
    title_prompt = _context_text(tool_payload, "title_prompt") or "Platform Architect artifact work session"
    draft_snapshot = tool_payload.get("draft_snapshot") if isinstance(tool_payload.get("draft_snapshot"), dict) else None
    replace_snapshot = bool(tool_payload.get("replace_snapshot"))

    async with get_session() as db:
        artifact_agent = await ensure_artifact_coding_agent_profile(db, tenant_id, actor_user_id=user_id)
        runtime = ArtifactCodingRuntimeService(db)
        prepared = await runtime.prepare_session(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=artifact_agent.id,
            title_prompt=title_prompt,
            artifact_id=artifact_id,
            draft_key=draft_key,
            chat_session_id=chat_session_id,
            draft_snapshot=draft_snapshot,
            replace_snapshot=replace_snapshot,
        )
        active_run = await db.get(AgentRun, prepared.session.active_run_id) if prepared.session.active_run_id else None
        artifact = None
        if prepared.shared_draft.artifact_id or prepared.shared_draft.linked_artifact_id or prepared.session.artifact_id or prepared.session.linked_artifact_id:
            artifact = await runtime.registry.get_tenant_artifact(
                artifact_id=prepared.shared_draft.artifact_id or prepared.shared_draft.linked_artifact_id or prepared.session.artifact_id or prepared.session.linked_artifact_id,
                tenant_id=tenant_id,
            )
        last_run = await db.get(AgentRun, prepared.session.last_run_id) if prepared.session.last_run_id else None
        last_test_run = await db.get(ArtifactRun, prepared.shared_draft.last_test_run_id) if prepared.shared_draft.last_test_run_id else None
        runtime_state = runtime.serialize_runtime_state(
            session=prepared.session,
            shared_draft=prepared.shared_draft,
            artifact=artifact,
            run=last_run,
            last_test_run=last_test_run,
        )
        return _serialize_prepare_result(
            runtime_state=runtime_state,
            active_run_id=str(active_run.id) if active_run else None,
            active_run_status=str(getattr(active_run.status, "value", active_run.status)) if active_run else None,
        )


@register_tool_function("artifact_coding_session_get_state")
async def artifact_coding_session_get_state(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    tenant_id = _context_uuid(tool_payload, "tenant_id", required=True)
    user_id = _context_uuid(tool_payload, "user_id", required=True)
    session_id = _context_uuid(tool_payload, "chat_session_id", required=True)
    reconcile_run_id = _context_uuid(tool_payload, "run_id", required=False)

    async with get_session() as db:
        runtime = ArtifactCodingRuntimeService(db)
        session, shared_draft, artifact, run, last_test_run = await runtime.get_session_state_for_user(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            reconcile_run_id=reconcile_run_id,
        )
        active_run = await db.get(__import__("app.db.postgres.models.agents", fromlist=["AgentRun"]).AgentRun, session.active_run_id) if session.active_run_id else None
        runtime_state = runtime.serialize_runtime_state(
            session=session,
            shared_draft=shared_draft,
            artifact=artifact,
            run=run,
            last_test_run=last_test_run,
        )
        return _serialize_prepare_result(
            runtime_state=runtime_state,
            active_run_id=str(active_run.id) if active_run else None,
            active_run_status=str(getattr(active_run.status, "value", active_run.status)) if active_run else None,
        )


@register_tool_function("artifact_coding_agent_call")
async def artifact_coding_agent_call(payload: Any) -> dict[str, Any]:
    tool_payload = _normalize_artifact_coding_call_payload(payload)
    tenant_id = _context_uuid(tool_payload, "tenant_id", required=True)
    user_id = _context_uuid(tool_payload, "user_id", required=True)
    requested_session_id = _context_uuid(tool_payload, "chat_session_id", required=False)
    artifact_id = _context_uuid(tool_payload, "artifact_id", required=False)
    draft_key = _context_text(tool_payload, "draft_key")
    requested_model_id = _context_text(tool_payload, "model_id")
    user_prompt = _compose_architect_artifact_coding_prompt(tool_payload)

    async with get_session() as db:
        chat_session_id = requested_session_id or await _resolve_latest_session_id_for_user(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if chat_session_id is None:
            raise ValueError("chat_session_id is required")
        runtime = ArtifactCodingRuntimeService(db)
        session, _shared_draft, run = await runtime.start_prompt_run(
            tenant_id=tenant_id,
            user_id=user_id,
            user_prompt=user_prompt,
            artifact_id=artifact_id,
            draft_key=draft_key,
            chat_session_id=chat_session_id,
            draft_snapshot=None,
            model_id=requested_model_id,
        )
        executor = AgentExecutorService(db=db)
        async for _ in executor.run_and_stream(run.id, db, None, mode=ExecutionMode.DEBUG):
            pass

        refreshed_run = await db.get(AgentRun, run.id)
        if refreshed_run is None:
            raise RuntimeError("Artifact coding run was not created")

        await runtime.reconcile_session_run(session=session, run=refreshed_run)
        await db.refresh(session)
        await db.refresh(refreshed_run)

        output_result = refreshed_run.output_result if isinstance(refreshed_run.output_result, dict) else {}
        state = output_result.get("state") if isinstance(output_result.get("state"), dict) else {}
        result: dict[str, Any] = {
            "mode": "sync",
            "run_id": str(refreshed_run.id),
            "status": str(getattr(refreshed_run.status, "value", refreshed_run.status)),
            "chat_session_id": str(session.id),
            "surface": str(refreshed_run.surface or ""),
        }
        if state.get("last_agent_output") is not None:
            result["output"] = state.get("last_agent_output")
        if isinstance(output_result.get("context"), dict):
            result["context"] = output_result.get("context")
        if refreshed_run.error_message:
            result["error"] = refreshed_run.error_message
        return result


ARCHITECT_ARTIFACT_DELEGATION_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "slug": "artifact-coding-session-prepare",
        "name": "Artifact Coding Session Prepare",
        "description": "Create or reuse an artifact-coding session and return the current shared draft state for architect delegation.",
        "implementation_type": ToolImplementationType.FUNCTION,
        "schema": _tool_schema(
            properties={
                "chat_session_id": {"type": "string"},
                "artifact_id": {"type": "string"},
                "draft_key": {"type": "string"},
                "title_prompt": {"type": "string"},
                "draft_snapshot": {"type": "object"},
                "replace_snapshot": {"type": "boolean"},
            },
        ),
        "config_schema": {
            "implementation": {"type": "function", "function_name": "artifact_coding_session_prepare"},
            "execution": {
                "timeout_s": 30,
                "is_pure": False,
                "concurrency_group": ARCHITECT_ARTIFACT_DELEGATION_NAMESPACE,
                "max_concurrency": 1,
            },
        },
    },
    {
        "slug": "artifact-coding-session-get-state",
        "name": "Artifact Coding Session Get State",
        "description": "Fetch the latest shared draft snapshot and canonical export payload for an artifact-coding session.",
        "implementation_type": ToolImplementationType.FUNCTION,
        "schema": _tool_schema(
            properties={
                "chat_session_id": {"type": "string"},
                "run_id": {"type": "string"},
            },
            required=["chat_session_id"],
        ),
        "config_schema": {
            "implementation": {"type": "function", "function_name": "artifact_coding_session_get_state"},
            "execution": {
                "timeout_s": 30,
                "is_pure": True,
                "concurrency_group": ARCHITECT_ARTIFACT_DELEGATION_NAMESPACE,
                "max_concurrency": 1,
            },
        },
    },
    {
        "slug": "artifact-coding-agent-call",
        "name": "Artifact Coding Agent Call",
        "description": "Call the tenant-scoped Artifact Coding Agent as a child run using the prepared artifact-coding session context.",
        "implementation_type": ToolImplementationType.FUNCTION,
        "schema": _tool_schema(
            properties={
                "input": {},
                "messages": {"type": "array", "items": {"type": "object"}},
                "context": {"type": "object"},
            },
        ),
        "config_schema": {
            "implementation": {
                "type": "function",
                "function_name": "artifact_coding_agent_call",
            },
            "execution": {
                "timeout_s": 180,
                "is_pure": False,
                "concurrency_group": ARCHITECT_ARTIFACT_DELEGATION_NAMESPACE,
                "max_concurrency": 1,
            },
        },
    },
]


async def ensure_platform_architect_artifact_delegation_tools(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_user_id: UUID | None = None,
) -> list[str]:
    import app.services.platform_architect_artifact_delegation_tools  # noqa: F401

    await ensure_artifact_coding_agent_profile(db, tenant_id, actor_user_id=actor_user_id)

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

    if not await _has_modern_tool_registry_columns():
        raise RuntimeError("platform architect artifact delegation tools require the current tool_registry schema")

    tool_ids: list[str] = []
    for spec in ARCHITECT_ARTIFACT_DELEGATION_TOOL_SPECS:
        result = await db.execute(
            select(ToolRegistry).where(
                and_(
                    ToolRegistry.tenant_id.is_(None),
                    ToolRegistry.slug == spec["slug"],
                )
            )
        )
        tool = result.scalar_one_or_none()
        if tool is None:
            tool = ToolRegistry(
                tenant_id=None,
                name=spec["name"],
                slug=spec["slug"],
                description=spec["description"],
                scope=ToolDefinitionScope.GLOBAL,
                schema=spec["schema"],
                config_schema=spec["config_schema"],
                status=ToolStatus.PUBLISHED,
                version="1.0.0",
                implementation_type=spec["implementation_type"],
                artifact_id=None,
                artifact_version=None,
                builtin_key=None,
                builtin_template_id=None,
                is_builtin_template=False,
                is_active=True,
                is_system=True,
                published_at=datetime.now(timezone.utc),
            )
            db.add(tool)
            await db.flush()
        else:
            tool.name = spec["name"]
            tool.description = spec["description"]
            tool.scope = ToolDefinitionScope.GLOBAL
            tool.schema = spec["schema"]
            tool.config_schema = spec["config_schema"]
            tool.status = ToolStatus.PUBLISHED
            tool.version = "1.0.0"
            tool.implementation_type = spec["implementation_type"]
            tool.is_active = True
            tool.is_system = True
            tool.published_at = tool.published_at or datetime.now(timezone.utc)
        tool_ids.append(str(tool.id))
    await db.flush()
    return tool_ids
