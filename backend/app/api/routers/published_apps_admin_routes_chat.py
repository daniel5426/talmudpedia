from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.models.published_apps import (
    BuilderCheckpointType,
    BuilderConversationTurnStatus,
    PublishedAppDraftDevSessionStatus,
    PublishedAppRevision,
)
from app.db.postgres.session import get_db
from app.services.published_app_draft_dev_runtime import (
    PublishedAppDraftDevRuntimeDisabled,
    PublishedAppDraftDevRuntimeService,
)

from .published_apps_admin_access import (
    _assert_can_manage_apps,
    _ensure_current_draft_revision,
    _get_app_for_tenant,
    _resolve_tenant_admin_context,
)
from .published_apps_admin_builder_agentic import _run_builder_agentic_loop
from .published_apps_admin_builder_core import (
    _builder_agentic_loop_enabled,
    _builder_chat_commands_enabled,
    _builder_chat_sandbox_tools_enabled,
    _builder_compile_error,
    _builder_model_patch_generation_enabled,
    _extract_http_error_code,
    _extract_http_error_details,
    _new_builder_request_id,
    _persist_builder_conversation_turn,
    _serialize_patch_ops,
    _stream_event_payload,
    _stream_event_sse,
)
from .published_apps_admin_builder_model import _generate_builder_patch_with_model
from .published_apps_admin_builder_patch import _apply_patch_operations, _build_builder_patch_from_prompt
from .published_apps_admin_builder_tools import (
    _apply_patch_operations_to_sandbox,
    _collect_changed_paths,
    _create_draft_revision_from_files,
    _run_allowlisted_sandbox_command,
    _snapshot_files_from_sandbox,
)
from .published_apps_admin_shared import BuilderChatRequest, BuilderPatchGenerationResult, BuilderPatchOp, router

@router.post("/{app_id}/builder/chat/stream")
async def builder_chat_stream(
    app_id: UUID,
    payload: BuilderChatRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_scopes("apps.write")),
    principal: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _resolve_tenant_admin_context(request, principal, db)
    _assert_can_manage_apps(ctx)

    app = await _get_app_for_tenant(db, ctx["tenant_id"], app_id)
    actor = ctx.get("user")
    actor_id = actor.id if actor else None
    draft = await _ensure_current_draft_revision(db, app, actor_id)

    if payload.base_revision_id and str(payload.base_revision_id) != str(draft.id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REVISION_CONFLICT",
                "latest_revision_id": str(draft.id),
                "latest_updated_at": draft.created_at.isoformat(),
                "message": "Draft revision is stale",
            },
        )

    user_prompt = payload.input.strip()
    if not user_prompt:
        raise HTTPException(status_code=400, detail="input is required")

    existing_files = dict(draft.files or {})
    request_id = _new_builder_request_id()
    trace_events: List[Dict[str, Any]] = []
    generation_result: Optional[BuilderPatchGenerationResult] = None
    patch_ops_payload: List[Dict[str, Any]] = []
    runtime_service: Optional[PublishedAppDraftDevRuntimeService] = None
    sandbox_id: Optional[str] = None
    final_files = dict(existing_files)
    final_entry = draft.entry_file
    saved_revision: Optional[PublishedAppRevision] = None
    try:
        if actor is not None and _builder_chat_sandbox_tools_enabled():
            runtime_service = PublishedAppDraftDevRuntimeService(db)
            try:
                session = await runtime_service.ensure_session(
                    app=app,
                    revision=draft,
                    user_id=actor.id,
                    files=existing_files,
                    entry_file=draft.entry_file,
                )
            except PublishedAppDraftDevRuntimeDisabled as exc:
                raise HTTPException(status_code=409, detail=str(exc))
            sandbox_id = session.sandbox_id
            if session.status == PublishedAppDraftDevSessionStatus.error:
                raise HTTPException(status_code=409, detail=session.last_error or "Draft dev sandbox failed to start")
            if not sandbox_id:
                raise HTTPException(status_code=409, detail="Draft dev sandbox id is missing")
            final_files = await _snapshot_files_from_sandbox(runtime_service, sandbox_id=sandbox_id)

        if _builder_model_patch_generation_enabled():
            if _builder_agentic_loop_enabled():
                generation_result, trace_events, final_files, final_entry = await _run_builder_agentic_loop(
                    user_prompt=user_prompt,
                    files=final_files,
                    entry_file=draft.entry_file,
                    request_id=request_id,
                    runtime_service=runtime_service,
                    sandbox_id=sandbox_id,
                )
            else:
                generation_result = await _generate_builder_patch_with_model(
                    user_prompt=user_prompt,
                    files=final_files,
                    entry_file=draft.entry_file,
                )
        else:
            patch_ops, patch_summary = _build_builder_patch_from_prompt(user_prompt, final_files)
            generation_result = BuilderPatchGenerationResult(
                operations=[BuilderPatchOp(**op) for op in patch_ops],
                summary=patch_summary,
            )
        patch_ops_payload = _serialize_patch_ops(generation_result.operations)
        final_files, final_entry = _apply_patch_operations(final_files, final_entry, generation_result.operations)
        if runtime_service is not None and sandbox_id:
            await _apply_patch_operations_to_sandbox(
                runtime_service,
                sandbox_id=sandbox_id,
                operations=generation_result.operations,
            )
            if _builder_chat_commands_enabled():
                command_result = await _run_allowlisted_sandbox_command(
                    runtime_service,
                    sandbox_id=sandbox_id,
                    command=["npm", "run", "build"],
                )
                trace_events.append(
                    _stream_event_payload(
                        event="tool_completed" if command_result.get("ok") else "tool_failed",
                        stage="command",
                        request_id=request_id,
                        data={
                            "tool": "run_command",
                            "command": "npm run build",
                            "status": "ok" if command_result.get("ok") else "failed",
                            "result": command_result,
                        },
                        diagnostics=command_result.get("diagnostics") if not command_result.get("ok") else None,
                    )
                )
                if not command_result.get("ok"):
                    raise _builder_compile_error(
                        "Sandbox command failed",
                        diagnostics=command_result.get("diagnostics") or [{"message": str(command_result.get("message") or "sandbox command failed")}],
                    )
            final_files = await _snapshot_files_from_sandbox(runtime_service, sandbox_id=sandbox_id)

        saved_revision = await _create_draft_revision_from_files(
            db,
            app=app,
            current=draft,
            actor_id=actor_id,
            files=final_files,
            entry_file=final_entry,
        )
        if runtime_service is not None and sandbox_id and actor is not None:
            await runtime_service.sync_session(
                app=app,
                revision=saved_revision,
                user_id=actor.id,
                files=final_files,
                entry_file=final_entry,
            )
    except HTTPException as exc:
        loop_trace_events = getattr(exc, "builder_trace_events", None)
        if isinstance(loop_trace_events, list) and loop_trace_events:
            trace_events = [item for item in loop_trace_events if isinstance(item, dict)]
        _, diagnostics = _extract_http_error_details(exc)
        await _persist_builder_conversation_turn(
            db,
            app_id=app.id,
            revision_id=draft.id,
            actor_id=actor_id,
            request_id=request_id,
            user_prompt=user_prompt,
            status=BuilderConversationTurnStatus.failed,
            generation_result=generation_result,
            trace_events=trace_events,
            diagnostics=diagnostics,
            failure_code=_extract_http_error_code(exc) or "BUILDER_REQUEST_FAILED",
        )
        await db.commit()
        raise
    except Exception as exc:
        await _persist_builder_conversation_turn(
            db,
            app_id=app.id,
            revision_id=draft.id,
            actor_id=actor_id,
            request_id=request_id,
            user_prompt=user_prompt,
            status=BuilderConversationTurnStatus.failed,
            generation_result=generation_result,
            trace_events=trace_events,
            diagnostics=[{"message": str(exc)}],
            failure_code="BUILDER_INTERNAL_ERROR",
        )
        await db.commit()
        raise

    await _persist_builder_conversation_turn(
        db,
        app_id=app.id,
        revision_id=draft.id,
        result_revision_id=saved_revision.id if saved_revision else None,
        actor_id=actor_id,
        request_id=request_id,
        user_prompt=user_prompt,
        status=BuilderConversationTurnStatus.succeeded,
        generation_result=generation_result,
        trace_events=trace_events,
        checkpoint_type=BuilderCheckpointType.auto_run,
        checkpoint_label=f"AI run {request_id[:8]}",
    )
    await db.commit()
    if saved_revision is not None:
        await db.refresh(saved_revision)

    async def event_generator():
        yield ": " + (" " * 2048) + "\n\n"
        yield _stream_event_sse(
            _stream_event_payload(
                event="status",
                stage="start",
                request_id=request_id,
                data={"content": "Builder request accepted"},
                )
            )
        for trace_event in trace_events:
            yield _stream_event_sse(trace_event)

        status_text = f"Applied builder patch: {generation_result.summary}."
        for chunk in status_text.split(" "):
            yield _stream_event_sse(
                _stream_event_payload(
                    event="token",
                    stage="assistant_response",
                    request_id=request_id,
                    data={"content": chunk + " "},
                )
            )
        yield _stream_event_sse(
            _stream_event_payload(
                event="file_changes",
                stage="patch_ready",
                request_id=request_id,
                data={
                    "changed_paths": _collect_changed_paths(generation_result.operations),
                    "operations": patch_ops_payload,
                    "base_revision_id": str(draft.id),
                    "result_revision_id": str(saved_revision.id) if saved_revision else None,
                    "summary": generation_result.summary,
                    "rationale": generation_result.rationale,
                    "assumptions": generation_result.assumptions,
                },
            )
        )
        if saved_revision is not None:
            yield _stream_event_sse(
                _stream_event_payload(
                    event="checkpoint_created",
                    stage="checkpoint",
                    request_id=request_id,
                    data={
                        "revision_id": str(saved_revision.id),
                        "source_revision_id": str(saved_revision.source_revision_id) if saved_revision.source_revision_id else None,
                        "checkpoint_type": "auto_run",
                        "checkpoint_label": f"AI run {request_id[:8]}",
                    },
                )
            )
        yield _stream_event_sse(
            _stream_event_payload(
                event="done",
                stage="complete",
                request_id=request_id,
                include_done_type=True,
            )
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
