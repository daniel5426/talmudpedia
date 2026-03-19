from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.postgres.models.agent_threads import (
    AgentThread,
    AgentThreadStatus,
    AgentThreadSurface,
    AgentThreadTurn,
    AgentThreadTurnStatus,
)
from app.db.postgres.models.runtime_attachments import AgentThreadTurnAttachment, RuntimeAttachment
from app.services.runtime_attachment_storage import RuntimeAttachmentStorage


class ThreadAccessError(Exception):
    pass


@dataclass
class ThreadResolveResult:
    thread: AgentThread
    created: bool


class ThreadService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.attachment_storage = RuntimeAttachmentStorage()

    @staticmethod
    def _turn_sort_key(turn: AgentThreadTurn) -> tuple[int, datetime, datetime, str]:
        created_at = turn.created_at if isinstance(turn.created_at, datetime) else datetime.min.replace(tzinfo=timezone.utc)
        completed_at = turn.completed_at if isinstance(turn.completed_at, datetime) else datetime.min.replace(tzinfo=timezone.utc)
        turn_index = int(turn.turn_index) if turn.turn_index is not None else 0
        return (
            turn_index,
            created_at,
            completed_at,
            str(turn.id),
        )

    @staticmethod
    def _derive_title(*, input_text: Optional[str], fallback: str = "New Thread") -> str:
        text = (input_text or "").strip()
        if not text:
            return fallback
        return text[:120]

    async def resolve_or_create_thread(
        self,
        *,
        tenant_id: UUID,
        user_id: Optional[UUID],
        app_account_id: Optional[UUID] = None,
        tenant_api_key_id: Optional[UUID] = None,
        agent_id: Optional[UUID],
        published_app_id: Optional[UUID],
        external_user_id: Optional[str] = None,
        external_session_id: Optional[str] = None,
        surface: AgentThreadSurface,
        thread_id: Optional[UUID],
        input_text: Optional[str],
    ) -> ThreadResolveResult:
        if thread_id is not None:
            thread = await self.db.get(AgentThread, thread_id)
            if thread is None or thread.tenant_id != tenant_id:
                raise ThreadAccessError("Thread not found")
            if thread.status == AgentThreadStatus.archived:
                raise ThreadAccessError("Thread is archived")
            if surface == AgentThreadSurface.embedded_runtime:
                if thread.agent_id != agent_id:
                    raise ThreadAccessError("Thread scope mismatch")
                if not external_user_id or thread.external_user_id != external_user_id:
                    raise ThreadAccessError("Thread ownership mismatch")
                if external_session_id is not None and thread.external_session_id != external_session_id:
                    raise ThreadAccessError("Thread session mismatch")
            if published_app_id is not None and thread.published_app_id != published_app_id:
                raise ThreadAccessError("Thread scope mismatch")
            if published_app_id is not None:
                if thread.app_account_id is not None and app_account_id is not None and thread.app_account_id != app_account_id:
                    raise ThreadAccessError("Thread ownership mismatch")
            elif thread.user_id is not None and user_id is not None and thread.user_id != user_id:
                raise ThreadAccessError("Thread ownership mismatch")
            return ThreadResolveResult(thread=thread, created=False)

        thread = AgentThread(
            tenant_id=tenant_id,
            user_id=user_id,
            app_account_id=app_account_id,
            tenant_api_key_id=tenant_api_key_id,
            agent_id=agent_id,
            published_app_id=published_app_id,
            external_user_id=external_user_id,
            external_session_id=external_session_id,
            surface=surface,
            status=AgentThreadStatus.active,
            title=self._derive_title(input_text=input_text),
            last_activity_at=datetime.now(timezone.utc),
        )
        self.db.add(thread)
        await self.db.flush()
        return ThreadResolveResult(thread=thread, created=True)

    async def start_turn(
        self,
        *,
        thread_id: UUID,
        run_id: UUID,
        user_input_text: Optional[str],
        attachment_ids: Optional[list[UUID]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AgentThreadTurn:
        existing_result = await self.db.execute(
            select(AgentThreadTurn).where(AgentThreadTurn.run_id == run_id).limit(1)
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return existing

        thread = await self.db.get(AgentThread, thread_id)
        if thread is None:
            raise ThreadAccessError("Thread not found")
        await self.repair_thread_turn_indices(thread_id=thread_id)
        max_index = (
            await self.db.execute(
                select(func.coalesce(func.max(AgentThreadTurn.turn_index), -1)).where(AgentThreadTurn.thread_id == thread_id)
            )
        ).scalar()
        next_index = int(max_index if max_index is not None else -1) + 1
        turn = AgentThreadTurn(
            thread_id=thread_id,
            run_id=run_id,
            turn_index=next_index,
            user_input_text=user_input_text,
            status=AgentThreadTurnStatus.running,
            metadata_=(metadata or {}),
        )
        thread.last_activity_at = datetime.now(timezone.utc)
        thread.last_run_id = run_id
        if user_input_text and (not thread.title or thread.title == "New Thread"):
            thread.title = self._derive_title(input_text=user_input_text)
        self.db.add(turn)
        await self.db.flush()
        for attachment_id in attachment_ids or []:
            self.db.add(
                AgentThreadTurnAttachment(
                    turn_id=turn.id,
                    attachment_id=attachment_id,
                )
            )
        await self.db.flush()
        return turn

    async def complete_turn(
        self,
        *,
        run_id: UUID,
        status: AgentThreadTurnStatus,
        assistant_output_text: Optional[str],
        usage_tokens: int,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[AgentThreadTurn]:
        result = await self.db.execute(
            select(AgentThreadTurn).where(AgentThreadTurn.run_id == run_id).with_for_update().limit(1)
        )
        turn = result.scalar_one_or_none()
        if turn is None:
            return None
        turn.status = status
        turn.assistant_output_text = assistant_output_text
        turn.usage_tokens = max(0, int(usage_tokens or 0))
        turn.completed_at = datetime.now(timezone.utc)
        if metadata:
            current = dict(turn.metadata_ or {})
            current.update(metadata)
            turn.metadata_ = current

        thread = await self.db.get(AgentThread, turn.thread_id)
        if thread is not None:
            thread.last_activity_at = datetime.now(timezone.utc)
            thread.last_run_id = run_id
            if not thread.title:
                thread.title = self._derive_title(input_text=turn.user_input_text)
        return turn

    async def repair_thread_turn_indices(self, *, thread_id: UUID) -> bool:
        result = await self.db.execute(
            select(AgentThreadTurn).where(AgentThreadTurn.thread_id == thread_id)
        )
        turns = list(result.scalars().all())
        if not turns:
            return False

        turns.sort(key=self._turn_sort_key)
        changed = False
        for expected_index, turn in enumerate(turns):
            current_index = int(turn.turn_index) if turn.turn_index is not None else 0
            if current_index == expected_index:
                continue
            turn.turn_index = expected_index
            changed = True
        if changed:
            await self.db.flush()
        return changed

    async def list_threads(
        self,
        *,
        tenant_id: UUID,
        user_id: Optional[UUID] = None,
        app_account_id: Optional[UUID] = None,
        published_app_id: Optional[UUID] = None,
        agent_id: Optional[UUID] = None,
        external_user_id: Optional[str] = None,
        external_session_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[AgentThread], int]:
        base = select(AgentThread).where(AgentThread.tenant_id == tenant_id)
        if user_id is not None:
            base = base.where(AgentThread.user_id == user_id)
        if app_account_id is not None:
            base = base.where(AgentThread.app_account_id == app_account_id)
        if published_app_id is not None:
            base = base.where(AgentThread.published_app_id == published_app_id)
        if agent_id is not None:
            base = base.where(AgentThread.agent_id == agent_id)
        if external_user_id is not None:
            base = base.where(AgentThread.external_user_id == external_user_id)
        if external_session_id is not None:
            base = base.where(AgentThread.external_session_id == external_session_id)
        count = (
            await self.db.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar() or 0
        rows = (
            await self.db.execute(
                base.order_by(AgentThread.last_activity_at.desc().nullslast(), AgentThread.updated_at.desc())
                .offset(max(0, int(skip)))
                .limit(max(1, int(limit)))
            )
        ).scalars().all()
        return list(rows), int(count)

    async def get_thread_with_turns(
        self,
        *,
        tenant_id: Optional[UUID],
        thread_id: UUID,
        user_id: Optional[UUID] = None,
        app_account_id: Optional[UUID] = None,
        published_app_id: Optional[UUID] = None,
        agent_id: Optional[UUID] = None,
        external_user_id: Optional[str] = None,
        external_session_id: Optional[str] = None,
    ) -> Optional[AgentThread]:
        query = select(AgentThread).where(AgentThread.id == thread_id).options(selectinload(AgentThread.turns)).limit(1)
        query = query.options(
            selectinload(AgentThread.turns)
            .selectinload(AgentThreadTurn.attachment_links)
            .selectinload(AgentThreadTurnAttachment.attachment)
        )
        if tenant_id is not None:
            query = query.where(AgentThread.tenant_id == tenant_id)
        thread = (await self.db.execute(query)).scalar_one_or_none()
        if thread is None:
            return None
        if published_app_id is not None and thread.published_app_id != published_app_id:
            return None
        if agent_id is not None and thread.agent_id != agent_id:
            return None
        if app_account_id is not None:
            if thread.app_account_id is not None and thread.app_account_id != app_account_id:
                return None
        elif user_id is not None and thread.user_id is not None and thread.user_id != user_id:
            return None
        if external_user_id is not None and thread.external_user_id != external_user_id:
            return None
        if external_session_id is not None and thread.external_session_id != external_session_id:
            return None
        thread.turns.sort(key=self._turn_sort_key)
        return thread

    async def delete_threads(self, *, tenant_id: UUID, thread_ids: list[UUID]) -> int:
        if not thread_ids:
            return 0
        result = await self.db.execute(
            select(AgentThread)
            .where(
                and_(AgentThread.tenant_id == tenant_id, AgentThread.id.in_(thread_ids))
            )
            .options(selectinload(AgentThread.attachments))
        )
        rows = list(result.scalars().all())
        for row in rows:
            for attachment in row.attachments or []:
                storage_key = str(getattr(attachment, "storage_key", "") or "").strip()
                if storage_key:
                    self.attachment_storage.delete_bytes(storage_key=storage_key)
            await self.db.delete(row)
        await self.db.flush()
        return len(rows)
