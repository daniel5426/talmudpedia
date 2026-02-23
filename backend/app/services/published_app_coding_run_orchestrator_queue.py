from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppCodingPromptQueue,
    PublishedAppCodingPromptQueueStatus,
    PublishedAppRevision,
)
from app.services.published_app_coding_agent_runtime import PublishedAppCodingAgentRuntimeService
from app.services.published_app_coding_chat_history_service import PublishedAppCodingChatHistoryService
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeDisabled, PublishedAppDraftDevRuntimeService

logger = logging.getLogger(__name__)

_TERMINAL_RUN_STATUSES = {RunStatus.completed.value, RunStatus.failed.value, RunStatus.cancelled.value, RunStatus.paused.value}


class PublishedAppCodingRunOrchestratorQueueMixin:
    db: AsyncSession

    @staticmethod
    def _now():
        raise NotImplementedError

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
            .limit(120)
        )
        runs = list(result.scalars().all())
        target_session_id = str(chat_session_id)
        for run in runs:
            status = run.status.value if hasattr(run.status, "value") else str(run.status)
            if status in _TERMINAL_RUN_STATUSES:
                continue
            input_params = run.input_params if isinstance(run.input_params, dict) else {}
            context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
            if str(context.get("chat_session_id") or "").strip() == target_session_id:
                return run
        return None

    async def count_queued_prompts(self, *, chat_session_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count(PublishedAppCodingPromptQueue.id)).where(
                PublishedAppCodingPromptQueue.chat_session_id == chat_session_id,
                PublishedAppCodingPromptQueue.status == PublishedAppCodingPromptQueueStatus.queued,
            )
        )
        return int(result.scalar_one() or 0)

    @classmethod
    async def _dispatch_next_queued_prompt_from_terminal_run(cls, *, db: AsyncSession, terminal_run: AgentRun) -> None:
        input_params = terminal_run.input_params if isinstance(terminal_run.input_params, dict) else {}
        context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
        raw_chat_session_id = str(context.get("chat_session_id") or "").strip()
        if not raw_chat_session_id:
            return
        try:
            chat_session_id = UUID(raw_chat_session_id)
        except Exception:
            return

        queue_result = await db.execute(
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
            return

        queue_item.status = PublishedAppCodingPromptQueueStatus.running
        queue_item.started_at = cls._now()
        queue_item.error = None
        await db.commit()

        app = await db.get(PublishedApp, queue_item.published_app_id)
        if app is None:
            queue_item.status = PublishedAppCodingPromptQueueStatus.failed
            queue_item.error = "Published app not found for queued prompt"
            queue_item.finished_at = cls._now()
            await db.commit()
            return

        actor_id = queue_item.user_id
        current_revision_id = app.current_draft_revision_id or terminal_run.base_revision_id
        current_revision = await db.get(PublishedAppRevision, current_revision_id) if current_revision_id else None
        if current_revision is None:
            queue_item.status = PublishedAppCodingPromptQueueStatus.failed
            queue_item.error = "Draft revision unavailable for queued prompt"
            queue_item.finished_at = cls._now()
            await db.commit()
            return

        payload = dict(queue_item.payload or {})
        user_prompt = str(payload.get("input") or "").strip()
        if not user_prompt:
            queue_item.status = PublishedAppCodingPromptQueueStatus.failed
            queue_item.error = "Queued prompt input is empty"
            queue_item.finished_at = cls._now()
            await db.commit()
            return

        requested_model_id = None
        raw_model_id = str(payload.get("model_id") or "").strip()
        if raw_model_id:
            try:
                requested_model_id = UUID(raw_model_id)
            except Exception:
                requested_model_id = None

        runtime = PublishedAppCodingAgentRuntimeService(db)
        try:
            run = await runtime.create_run(
                app=app,
                base_revision=current_revision,
                actor_id=actor_id,
                user_prompt=user_prompt,
                messages=None,
                requested_model_id=requested_model_id,
                execution_engine=str(payload.get("engine") or "").strip() or None,
                chat_session_id=chat_session_id,
            )

            draft_runtime = PublishedAppDraftDevRuntimeService(db)
            try:
                draft_session = await draft_runtime.get_session(app_id=app.id, user_id=actor_id)
            except PublishedAppDraftDevRuntimeDisabled:
                draft_session = None
            if draft_session is not None:
                draft_session.active_coding_run_id = run.id
                draft_session.active_coding_run_locked_at = cls._now()
                client_message_id = str(payload.get("client_message_id") or "").strip() or None
                draft_session.active_coding_run_client_message_id = client_message_id

            history = PublishedAppCodingChatHistoryService(db)
            await history.persist_user_message(
                session_id=chat_session_id,
                run_id=run.id,
                content=user_prompt,
            )

            queue_item.status = PublishedAppCodingPromptQueueStatus.completed
            queue_item.finished_at = cls._now()
            queue_item.error = None
            await db.commit()

            asyncio.create_task(cls._ensure_runner_detached(app_id=app.id, run_id=run.id))
            logger.info(
                "CODING_AGENT_QUEUE_DISPATCH app_id=%s from_run_id=%s next_run_id=%s queue_item_id=%s",
                app.id,
                terminal_run.id,
                run.id,
                queue_item.id,
            )
        except Exception as exc:
            queue_item.status = PublishedAppCodingPromptQueueStatus.failed
            queue_item.error = str(exc)
            queue_item.finished_at = cls._now()
            await db.commit()
            logger.exception(
                "CODING_AGENT_QUEUE_DISPATCH_FAILED app_id=%s from_run_id=%s queue_item_id=%s error=%s",
                app.id,
                terminal_run.id,
                queue_item.id,
                exc,
            )

    @classmethod
    async def _ensure_runner_detached(cls, *, app_id: UUID, run_id: UUID) -> None:
        try:
            async with cls._session_factory() as db:
                orchestrator = cls(db)
                await orchestrator.ensure_runner(app_id=app_id, run_id=run_id)
        except Exception:
            logger.exception("CODING_AGENT_REATTACH detached_ensure_runner_failed run_id=%s app_id=%s", run_id, app_id)
