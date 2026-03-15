from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.engine import sessionmaker as get_session
from app.services.artifact_coding_agent_tools import _resolve_session_context, _tool_schema
from app.services.tool_function_registry import register_tool_function

ARTIFACT_CODING_SCOPE_STANDALONE = "standalone"

def _actor_user_id(run_user_id: UUID | None, run_initiator_user_id: UUID | None) -> UUID | None:
    return run_user_id or run_initiator_user_id


def _serialize_artifact_match(artifact) -> dict[str, Any]:
    return {
        "artifact_id": str(artifact.id),
        "slug": str(artifact.slug or ""),
        "display_name": str(artifact.display_name or ""),
        "description": str(artifact.description or ""),
        "kind": str(getattr(artifact.kind, "value", artifact.kind)),
        "updated_at": artifact.updated_at.isoformat() if getattr(artifact, "updated_at", None) else None,
    }


def _require_standalone_scope(scope_mode: str | None) -> None:
    if str(scope_mode or "").strip().lower() != ARTIFACT_CODING_SCOPE_STANDALONE:
        raise RuntimeError("ARTIFACT_CODING_SCOPE_LOCKED")


@register_tool_function("artifact_coding_search_artifacts")
async def artifact_coding_search_artifacts(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    query = str(tool_payload.get("query") or "").strip()
    limit = max(1, min(int(tool_payload.get("limit") or 10), 25))
    async with get_session() as db:
        session, _shared_draft, run, _artifact = await _resolve_session_context(db, tool_payload)
        _require_standalone_scope(getattr(session, "scope_mode", None))
        from app.services.artifact_coding_runtime_service import ArtifactCodingRuntimeService

        runtime = ArtifactCodingRuntimeService(db)
        results = await runtime.search_accessible_artifacts(
            tenant_id=session.tenant_id,
            query=query,
            limit=limit,
        )
        return {
            "query": query,
            "results": [_serialize_artifact_match(item) for item in results],
            "count": len(results),
        }


@register_tool_function("artifact_coding_list_recent_artifacts")
async def artifact_coding_list_recent_artifacts(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    limit = max(1, min(int(tool_payload.get("limit") or 10), 25))
    async with get_session() as db:
        session, _shared_draft, _run, _artifact = await _resolve_session_context(db, tool_payload)
        _require_standalone_scope(getattr(session, "scope_mode", None))
        from app.services.artifact_coding_runtime_service import ArtifactCodingRuntimeService

        runtime = ArtifactCodingRuntimeService(db)
        results = await runtime.list_recent_accessible_artifacts(
            tenant_id=session.tenant_id,
            limit=limit,
        )
        return {
            "results": [_serialize_artifact_match(item) for item in results],
            "count": len(results),
        }


@register_tool_function("artifact_coding_open_artifact")
async def artifact_coding_open_artifact(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    artifact_id = str(tool_payload.get("artifact_id") or "").strip()
    if not artifact_id:
        raise ValueError("artifact_id is required")
    async with get_session() as db:
        session, shared_draft, run, _artifact = await _resolve_session_context(db, tool_payload)
        _require_standalone_scope(getattr(session, "scope_mode", None))
        actor_user_id = _actor_user_id(run.user_id, run.initiator_user_id)
        if actor_user_id is None:
            raise ValueError("Run user context is missing")
        from app.services.artifact_coding_runtime_service import ArtifactCodingRuntimeService

        runtime = ArtifactCodingRuntimeService(db)
        next_session, _next_shared_draft, artifact = await runtime.open_artifact_for_session(
            tenant_id=session.tenant_id,
            user_id=actor_user_id,
            session_id=session.id,
            artifact_id=UUID(artifact_id),
        )
        _session, shared_draft, artifact, latest_run, last_test_run = await runtime.get_session_state_for_user(
            tenant_id=next_session.tenant_id,
            user_id=actor_user_id,
            session_id=next_session.id,
        )
        session_state = runtime.serialize_runtime_state(
            session=next_session,
            shared_draft=shared_draft,
            artifact=artifact,
            run=latest_run,
            last_test_run=last_test_run,
        )
        return {
            "ok": True,
            "summary": f"Opened artifact {artifact.display_name or artifact.slug}.",
            "artifact": _serialize_artifact_match(artifact),
            "session_state": session_state,
            "draft_snapshot": session_state.get("draft_snapshot"),
        }


@register_tool_function("artifact_coding_start_new_draft")
async def artifact_coding_start_new_draft(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    draft_seed = tool_payload.get("draft_seed") if isinstance(tool_payload.get("draft_seed"), dict) else None
    if not draft_seed:
        raise ValueError("draft_seed is required")
    async with get_session() as db:
        session, _shared_draft, run, _artifact = await _resolve_session_context(db, tool_payload)
        _require_standalone_scope(getattr(session, "scope_mode", None))
        actor_user_id = _actor_user_id(run.user_id, run.initiator_user_id)
        if actor_user_id is None:
            raise ValueError("Run user context is missing")
        from app.services.artifact_coding_runtime_service import ArtifactCodingRuntimeService

        runtime = ArtifactCodingRuntimeService(db)
        next_session, shared_draft = await runtime.start_new_draft_for_session(
            tenant_id=session.tenant_id,
            user_id=actor_user_id,
            session_id=session.id,
            draft_seed=draft_seed,
        )
        _session, shared_draft, artifact, latest_run, last_test_run = await runtime.get_session_state_for_user(
            tenant_id=next_session.tenant_id,
            user_id=actor_user_id,
            session_id=next_session.id,
        )
        session_state = runtime.serialize_runtime_state(
            session=next_session,
            shared_draft=shared_draft,
            artifact=artifact,
            run=latest_run,
            last_test_run=last_test_run,
        )
        return {
            "ok": True,
            "summary": "Started a new artifact draft in the current session.",
            "session_state": session_state,
            "draft_snapshot": session_state.get("draft_snapshot"),
        }


@register_tool_function("artifact_coding_persist_artifact")
async def artifact_coding_persist_artifact(payload: Any) -> dict[str, Any]:
    tool_payload = payload if isinstance(payload, dict) else {}
    mode = str(tool_payload.get("mode") or "auto").strip() or "auto"
    async with get_session() as db:
        session, _shared_draft, run, _artifact = await _resolve_session_context(db, tool_payload)
        actor_user_id = _actor_user_id(run.user_id, run.initiator_user_id)
        if actor_user_id is None:
            raise ValueError("Run user context is missing")
        from app.services.artifact_coding_runtime_service import ArtifactCodingRuntimeService

        runtime = ArtifactCodingRuntimeService(db)
        result = await runtime.persist_session_artifact(
            tenant_id=session.tenant_id,
            user_id=actor_user_id,
            session_id=session.id,
            mode=mode,
        )
        return {
            "ok": True,
            "summary": f"Persisted artifact in {result['persistence_mode']} mode.",
            "draft_snapshot": result.get("session_state", {}).get("draft_snapshot") if isinstance(result.get("session_state"), dict) else None,
            **result,
        }


ARTIFACT_CODING_SCOPE_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "slug": "artifact-coding-search-artifacts",
        "name": "Artifact Coding Search Artifacts",
        "description": "Search accessible artifacts by name, slug, or description.",
        "function_name": "artifact_coding_search_artifacts",
        "timeout_s": 30,
        "is_pure": True,
        "schema": _tool_schema(
            properties={"query": {"type": "string"}, "limit": {"type": "integer"}},
            required=["query"],
        ),
    },
    {
        "slug": "artifact-coding-list-recent-artifacts",
        "name": "Artifact Coding List Recent Artifacts",
        "description": "List the most recently updated accessible artifacts.",
        "function_name": "artifact_coding_list_recent_artifacts",
        "timeout_s": 30,
        "is_pure": True,
        "schema": _tool_schema(properties={"limit": {"type": "integer"}}),
    },
    {
        "slug": "artifact-coding-open-artifact",
        "name": "Artifact Coding Open Artifact",
        "description": "Attach the current standalone session to an existing artifact and load its current draft into the session.",
        "function_name": "artifact_coding_open_artifact",
        "timeout_s": 60,
        "is_pure": False,
        "schema": _tool_schema(properties={"artifact_id": {"type": "string"}}, required=["artifact_id"]),
    },
    {
        "slug": "artifact-coding-start-new-draft",
        "name": "Artifact Coding Start New Draft",
        "description": "Reset the current standalone session into a new artifact draft seeded by kind and optional metadata.",
        "function_name": "artifact_coding_start_new_draft",
        "timeout_s": 60,
        "is_pure": False,
        "schema": _tool_schema(
            properties={
                "draft_seed": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": ["agent_node", "rag_operator", "tool_impl"]},
                        "slug": {"type": "string"},
                        "display_name": {"type": "string"},
                        "description": {"type": "string"},
                        "entry_module_path": {"type": "string"},
                        "runtime_target": {"type": "string"},
                    },
                    "required": ["kind"],
                    "additionalProperties": False,
                }
            },
            required=["draft_seed"],
        ),
    },
    {
        "slug": "artifact-coding-persist-artifact",
        "name": "Artifact Coding Persist Artifact",
        "description": "Persist the current session draft into a canonical artifact create or update.",
        "function_name": "artifact_coding_persist_artifact",
        "timeout_s": 90,
        "is_pure": False,
        "schema": _tool_schema(
            properties={"mode": {"type": "string", "enum": ["auto", "create", "update"]}},
        ),
    },
]
