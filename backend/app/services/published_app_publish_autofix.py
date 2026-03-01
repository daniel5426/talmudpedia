from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.published_apps import PublishedApp, PublishedAppRevision
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_chat_history_service import PublishedAppCodingChatHistoryService
from app.services.published_app_coding_run_monitor import PublishedAppCodingRunMonitor


def _build_autofix_prompt(*, revision_id: UUID, reason: str) -> str:
    clean_reason = str(reason or "").strip() or "Unknown build failure"
    return (
        "Build failed for selected app version and publish was blocked.\n"
        f"Version ID: {revision_id}\n"
        f"Build failure reason: {clean_reason}\n\n"
        "Please fix the build for this version only. Keep behavior intact unless required to restore build success. "
        "After fixes, ensure the app can produce dist assets successfully."
    )


async def submit_publish_build_failure_autofix(
    *,
    db: AsyncSession,
    app: PublishedApp,
    revision: PublishedAppRevision,
    requested_by: UUID | None,
    failure_reason: str,
) -> dict[str, Any]:
    if requested_by is None:
        return {"status": "skipped", "reason": "publish job has no requesting user"}

    history = PublishedAppCodingChatHistoryService(db)
    sessions = await history.list_sessions(
        app_id=app.id,
        user_id=requested_by,
        limit=1,
    )
    if not sessions:
        return {"status": "skipped", "reason": "no existing coding-agent chat session"}

    target_session = sessions[0]
    runtime = PublishedAppCodingAgentRuntimeService(db)
    active_run = await runtime.get_active_run_for_chat_session(
        app_id=app.id,
        chat_session_id=target_session.id,
    )
    if active_run is not None:
        return {
            "status": "skipped",
            "reason": "latest chat already has an active run",
            "active_run_id": str(active_run.id),
        }

    prompt = _build_autofix_prompt(
        revision_id=revision.id,
        reason=failure_reason,
    )
    run_messages = await history.build_run_messages(
        session_id=target_session.id,
        current_user_prompt=prompt,
    )
    run = await runtime.create_run(
        app=app,
        base_revision=revision,
        actor_id=requested_by,
        user_prompt=prompt,
        messages=run_messages,
        requested_model_id=None,
        chat_session_id=target_session.id,
    )
    await history.persist_user_message(
        session_id=target_session.id,
        run_id=run.id,
        content=prompt,
    )
    await PublishedAppCodingRunMonitor(db).ensure_monitor(app_id=app.id, run_id=run.id)
    return {
        "status": "submitted",
        "run_id": str(run.id),
        "chat_session_id": str(target_session.id),
    }
