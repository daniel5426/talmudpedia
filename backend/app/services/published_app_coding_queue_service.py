from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppCodingPromptQueue,
    PublishedAppCodingPromptQueueStatus,
    PublishedAppDraftDevSession,
    PublishedAppRevision,
)
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_chat_history_service import PublishedAppCodingChatHistoryService

_TERMINAL_RUN_STATUSES = {
    RunStatus.completed.value,
    RunStatus.failed.value,
    RunStatus.cancelled.value,
    RunStatus.paused.value,
}


@dataclass
class CodingPromptSubmissionResult:
    status: Literal["started", "queued"]
    run: AgentRun | None
    active_run: AgentRun | None
    queue_item: PublishedAppCodingPromptQueue | None
    chat_session_id: UUID | None


class PublishedAppCodingQueueService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def serialize_queue_item(item: PublishedAppCodingPromptQueue) -> dict[str, Any]:
        payload = dict(item.payload or {})
        return {
            "id": str(item.id),
            "chat_session_id": str(item.chat_session_id),
            "position": int(item.position or 0),
            "status": item.status.value if hasattr(item.status, "value") else str(item.status),
            "input": str(payload.get("input") or ""),
            "client_message_id": str(payload.get("client_message_id") or "").strip() or None,
            "created_at": item.created_at,
            "started_at": item.started_at,
            "finished_at": item.finished_at,
            "error": item.error,
        }

    async def get_active_run_for_chat_session(
        self,
        *,
        app_id: UUID,
        chat_session_id: UUID,
    ) -> AgentRun | None:
        result = await self.db.execute(
            select(AgentRun)
            .where(
                AgentRun.published_app_id == app_id,
                AgentRun.surface == "published_app_coding_agent",
            )
            .order_by(AgentRun.created_at.desc())
            .limit(200)
        )
        runs = list(result.scalars().all())
        target_chat_session_id = str(chat_session_id)
        for run in runs:
            status = run.status.value if hasattr(run.status, "value") else str(run.status)
            if status in _TERMINAL_RUN_STATUSES:
                continue
            input_params = run.input_params if isinstance(run.input_params, dict) else {}
            context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
            if str(context.get("chat_session_id") or "").strip() == target_chat_session_id:
                return run
        return None

    async def enqueue_prompt(
        self,
        *,
        app_id: UUID,
        user_id: UUID,
        chat_session_id: UUID,
        payload: dict[str, Any],
    ) -> PublishedAppCodingPromptQueue:
        max_position_result = await self.db.execute(
            select(func.max(PublishedAppCodingPromptQueue.position)).where(
                PublishedAppCodingPromptQueue.chat_session_id == chat_session_id,
            )
        )
        max_position = int(max_position_result.scalar_one_or_none() or 0)
        item = PublishedAppCodingPromptQueue(
            published_app_id=app_id,
            user_id=user_id,
            chat_session_id=chat_session_id,
            position=max_position + 1,
            status=PublishedAppCodingPromptQueueStatus.queued,
            payload=dict(payload or {}),
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def list_queue_items(
        self,
        *,
        app_id: UUID,
        user_id: UUID,
        chat_session_id: UUID,
    ) -> list[PublishedAppCodingPromptQueue]:
        result = await self.db.execute(
            select(PublishedAppCodingPromptQueue)
            .where(
                PublishedAppCodingPromptQueue.published_app_id == app_id,
                PublishedAppCodingPromptQueue.user_id == user_id,
                PublishedAppCodingPromptQueue.chat_session_id == chat_session_id,
                PublishedAppCodingPromptQueue.status.in_(
                    [
                        PublishedAppCodingPromptQueueStatus.queued,
                        PublishedAppCodingPromptQueueStatus.running,
                    ]
                ),
            )
            .order_by(PublishedAppCodingPromptQueue.position.asc())
        )
        return list(result.scalars().all())

    async def remove_queue_item(
        self,
        *,
        app_id: UUID,
        user_id: UUID,
        chat_session_id: UUID,
        queue_item_id: UUID,
    ) -> bool:
        item = await self.db.get(PublishedAppCodingPromptQueue, queue_item_id)
        if item is None:
            return False
        if (
            item.published_app_id != app_id
            or item.user_id != user_id
            or item.chat_session_id != chat_session_id
        ):
            return False
        if item.status != PublishedAppCodingPromptQueueStatus.queued:
            return False
        item.status = PublishedAppCodingPromptQueueStatus.cancelled
        item.finished_at = self._now()
        await self.db.commit()
        return True

    async def count_queued_prompts(self, *, chat_session_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count(PublishedAppCodingPromptQueue.id)).where(
                PublishedAppCodingPromptQueue.chat_session_id == chat_session_id,
                PublishedAppCodingPromptQueue.status == PublishedAppCodingPromptQueueStatus.queued,
            )
        )
        return int(result.scalar_one() or 0)

    async def submit_prompt(
        self,
        *,
        app: PublishedApp,
        base_revision: PublishedAppRevision,
        actor_id: UUID | None,
        user_prompt: str,
        model_id: UUID | None,
        chat_session_id: UUID | None,
        client_message_id: str | None,
    ) -> CodingPromptSubmissionResult:
        runtime = PublishedAppCodingAgentRuntimeService(self.db)
        history = PublishedAppCodingChatHistoryService(self.db)

        resolved_session_id: UUID | None = None
        run_messages: list[dict[str, str]] | None = None
        if actor_id is not None:
            session = await history.resolve_or_create_session(
                app_id=app.id,
                user_id=actor_id,
                user_prompt=user_prompt,
                session_id=chat_session_id,
            )
            resolved_session_id = session.id
            run_messages = await history.build_run_messages(
                session_id=session.id,
                current_user_prompt=user_prompt,
            )
            active_run = await self.get_active_run_for_chat_session(
                app_id=app.id,
                chat_session_id=session.id,
            )
            if active_run is not None:
                queue_item = await self.enqueue_prompt(
                    app_id=app.id,
                    user_id=actor_id,
                    chat_session_id=session.id,
                    payload={
                        "input": user_prompt,
                        "model_id": str(model_id) if model_id else None,
                        "client_message_id": client_message_id,
                    },
                )
                return CodingPromptSubmissionResult(
                    status="queued",
                    run=None,
                    active_run=active_run,
                    queue_item=queue_item,
                    chat_session_id=session.id,
                )

        run = await runtime.create_run(
            app=app,
            base_revision=base_revision,
            actor_id=actor_id,
            user_prompt=user_prompt,
            messages=run_messages,
            requested_model_id=model_id,
            chat_session_id=resolved_session_id,
        )

        if resolved_session_id is not None:
            await history.persist_user_message(
                session_id=resolved_session_id,
                run_id=run.id,
                content=user_prompt,
            )
        else:
            await self.db.commit()

        if actor_id is not None:
            draft_session_result = await self.db.execute(
                select(PublishedAppDraftDevSession).where(
                    and_(
                        PublishedAppDraftDevSession.published_app_id == app.id,
                        PublishedAppDraftDevSession.user_id == actor_id,
                    )
                )
            )
            draft_session = draft_session_result.scalar_one_or_none()
            if draft_session is not None:
                draft_session.active_coding_run_id = run.id
                draft_session.active_coding_run_locked_at = self._now()
                await self.db.commit()

        return CodingPromptSubmissionResult(
            status="started",
            run=run,
            active_run=None,
            queue_item=None,
            chat_session_id=resolved_session_id,
        )

    async def dispatch_next_for_terminal_run(self, *, terminal_run: AgentRun) -> AgentRun | None:
        input_params = terminal_run.input_params if isinstance(terminal_run.input_params, dict) else {}
        context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
        raw_chat_session_id = str(context.get("chat_session_id") or "").strip()
        if not raw_chat_session_id:
            return None
        try:
            chat_session_id = UUID(raw_chat_session_id)
        except Exception:
            return None

        queue_result = await self.db.execute(
            select(PublishedAppCodingPromptQueue)
            .where(
                PublishedAppCodingPromptQueue.chat_session_id == chat_session_id,
                PublishedAppCodingPromptQueue.status == PublishedAppCodingPromptQueueStatus.queued,
            )
            .order_by(PublishedAppCodingPromptQueue.position.asc())
            .limit(1)
        )
        queue_item = queue_result.scalar_one_or_none()
        if queue_item is None:
            return None

        queue_item.status = PublishedAppCodingPromptQueueStatus.running
        queue_item.started_at = self._now()
        queue_item.error = None
        await self.db.commit()

        app = await self.db.get(PublishedApp, queue_item.published_app_id)
        if app is None:
            queue_item.status = PublishedAppCodingPromptQueueStatus.failed
            queue_item.error = "Published app not found for queued prompt"
            queue_item.finished_at = self._now()
            await self.db.commit()
            return None

        actor_id = queue_item.user_id
        current_revision_id = app.current_draft_revision_id or terminal_run.base_revision_id
        current_revision = await self.db.get(PublishedAppRevision, current_revision_id) if current_revision_id else None
        if current_revision is None:
            queue_item.status = PublishedAppCodingPromptQueueStatus.failed
            queue_item.error = "Draft revision unavailable for queued prompt"
            queue_item.finished_at = self._now()
            await self.db.commit()
            return None

        payload = dict(queue_item.payload or {})
        user_prompt = str(payload.get("input") or "").strip()
        if not user_prompt:
            queue_item.status = PublishedAppCodingPromptQueueStatus.failed
            queue_item.error = "Queued prompt input is empty"
            queue_item.finished_at = self._now()
            await self.db.commit()
            return None

        requested_model_id = None
        raw_model_id = str(payload.get("model_id") or "").strip()
        if raw_model_id:
            try:
                requested_model_id = UUID(raw_model_id)
            except Exception:
                requested_model_id = None

        result = await self.submit_prompt(
            app=app,
            base_revision=current_revision,
            actor_id=actor_id,
            user_prompt=user_prompt,
            model_id=requested_model_id,
            chat_session_id=chat_session_id,
            client_message_id=str(payload.get("client_message_id") or "").strip() or None,
        )
        if result.status != "started" or result.run is None:
            queue_item.status = PublishedAppCodingPromptQueueStatus.failed
            queue_item.error = "Queued prompt dispatch returned non-started status"
            queue_item.finished_at = self._now()
            await self.db.commit()
            return None

        queue_item.status = PublishedAppCodingPromptQueueStatus.completed
        queue_item.finished_at = self._now()
        queue_item.error = None
        await self.db.commit()
        return result.run
