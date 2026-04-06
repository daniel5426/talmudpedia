from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.orm import joinedload, selectinload

from app.db.postgres.models.agent_threads import (
    AgentThread,
    AgentThreadStatus,
    AgentThreadSurface,
    AgentThreadTurn,
    AgentThreadTurnStatus,
)
from app.db.postgres.models.agents import AgentRun
from app.db.postgres.models.runtime_attachments import AgentThreadTurnAttachment, RuntimeAttachment
from app.services.runtime_attachment_storage import RuntimeAttachmentStorage


class ThreadAccessError(Exception):
    pass


@dataclass
class ThreadResolveResult:
    thread: AgentThread
    created: bool


@dataclass
class ThreadTurnPage:
    turns: list[AgentThreadTurn]
    has_more: bool
    next_before_turn_index: int | None


@dataclass
class ThreadTurnPageResult:
    thread: AgentThread
    page: ThreadTurnPage


@dataclass
class ThreadLineageResolveContext:
    root_thread_id: UUID
    parent_thread_id: UUID
    parent_thread_turn_id: UUID | None
    spawned_by_run_id: UUID
    lineage_depth: int


@dataclass
class ThreadSubtreeNode:
    thread: AgentThread
    page: ThreadTurnPage
    children: list["ThreadSubtreeNode"]
    has_children: bool


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
        parent_run_id: Optional[UUID] = None,
    ) -> ThreadResolveResult:
        lineage_context = await self._build_lineage_context(
            tenant_id=tenant_id,
            parent_run_id=parent_run_id,
        )
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
            await self._ensure_thread_lineage(thread)
            self._assert_lineage_compatible(thread=thread, lineage_context=lineage_context)
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
            root_thread_id=lineage_context.root_thread_id if lineage_context else None,
            parent_thread_id=lineage_context.parent_thread_id if lineage_context else None,
            parent_thread_turn_id=lineage_context.parent_thread_turn_id if lineage_context else None,
            spawned_by_run_id=lineage_context.spawned_by_run_id if lineage_context else None,
            lineage_depth=lineage_context.lineage_depth if lineage_context else 0,
        )
        self.db.add(thread)
        await self.db.flush()
        await self._ensure_thread_lineage(thread)
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
        thread = await self._get_accessible_thread(
            tenant_id=tenant_id,
            thread_id=thread_id,
            user_id=user_id,
            app_account_id=app_account_id,
            published_app_id=published_app_id,
            agent_id=agent_id,
            external_user_id=external_user_id,
            external_session_id=external_session_id,
            include_turns=True,
        )
        if thread is None:
            return None
        await self._ensure_thread_lineage(thread)
        thread.turns.sort(key=self._turn_sort_key)
        return thread

    async def _get_accessible_thread(
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
        include_turns: bool = False,
    ) -> Optional[AgentThread]:
        query = select(AgentThread).where(AgentThread.id == thread_id).limit(1)
        if include_turns:
            query = query.options(
                selectinload(AgentThread.turns).joinedload(AgentThreadTurn.run),
                selectinload(AgentThread.turns)
                .selectinload(AgentThreadTurn.attachment_links)
                .selectinload(AgentThreadTurnAttachment.attachment),
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
        await self._ensure_thread_lineage(thread)
        return thread

    async def get_thread_turn_page(
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
        before_turn_index: int | None = None,
        limit: int = 20,
    ) -> Optional[ThreadTurnPageResult]:
        thread = await self._get_accessible_thread(
            tenant_id=tenant_id,
            thread_id=thread_id,
            user_id=user_id,
            app_account_id=app_account_id,
            published_app_id=published_app_id,
            agent_id=agent_id,
            external_user_id=external_user_id,
            external_session_id=external_session_id,
            include_turns=False,
        )
        if thread is None:
            return None

        safe_limit = max(1, int(limit))
        turn_query = (
            select(AgentThreadTurn)
            .where(AgentThreadTurn.thread_id == thread_id)
            .options(
                joinedload(AgentThreadTurn.run),
                selectinload(AgentThreadTurn.attachment_links).selectinload(AgentThreadTurnAttachment.attachment),
            )
        )
        if before_turn_index is not None:
            turn_query = turn_query.where(AgentThreadTurn.turn_index < int(before_turn_index))
        turn_query = turn_query.order_by(
            desc(AgentThreadTurn.turn_index),
            desc(AgentThreadTurn.created_at),
            desc(AgentThreadTurn.completed_at),
            desc(AgentThreadTurn.id),
        ).limit(safe_limit + 1)

        turn_rows = list((await self.db.execute(turn_query)).scalars().all())
        has_more = len(turn_rows) > safe_limit
        paged_turns = turn_rows[:safe_limit]
        paged_turns.sort(key=self._turn_sort_key)
        next_before_turn_index = None
        if has_more and paged_turns:
            next_before_turn_index = int(paged_turns[0].turn_index or 0)

        set_committed_value(thread, "turns", paged_turns)
        return ThreadTurnPageResult(
            thread=thread,
            page=ThreadTurnPage(
                turns=paged_turns,
                has_more=has_more,
                next_before_turn_index=next_before_turn_index,
            ),
        )

    async def build_subthread_tree(
        self,
        *,
        root_thread: AgentThread,
        root_page: ThreadTurnPage,
        depth: int,
        turn_limit: int,
        child_limit: int,
    ) -> ThreadSubtreeNode:
        await self._ensure_thread_lineage(root_thread)
        return await self._build_subtree_node(
            thread=root_thread,
            page=root_page,
            remaining_depth=max(0, int(depth)),
            turn_limit=max(1, int(turn_limit)),
            child_limit=max(1, int(child_limit)),
        )

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
        all_thread_ids = {row.id for row in rows}
        if all_thread_ids:
            descendants = await self._collect_descendant_thread_ids(
                tenant_id=tenant_id,
                parent_thread_ids=all_thread_ids,
            )
            all_thread_ids.update(descendants)
        if all_thread_ids:
            result = await self.db.execute(
                select(AgentThread)
                .where(
                    and_(AgentThread.tenant_id == tenant_id, AgentThread.id.in_(all_thread_ids))
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

    @staticmethod
    def serialize_thread_lineage(thread: AgentThread) -> dict[str, Any]:
        root_thread_id = thread.root_thread_id or thread.id
        return {
            "root_thread_id": str(root_thread_id) if root_thread_id else None,
            "parent_thread_id": str(thread.parent_thread_id) if thread.parent_thread_id else None,
            "parent_thread_turn_id": str(thread.parent_thread_turn_id) if thread.parent_thread_turn_id else None,
            "spawned_by_run_id": str(thread.spawned_by_run_id) if thread.spawned_by_run_id else None,
            "depth": int(thread.lineage_depth or 0),
            "is_root": str(root_thread_id) == str(thread.id),
        }

    async def _build_lineage_context(
        self,
        *,
        tenant_id: UUID,
        parent_run_id: UUID | None,
    ) -> ThreadLineageResolveContext | None:
        if parent_run_id is None:
            return None
        parent_run = await self.db.get(AgentRun, parent_run_id)
        if parent_run is None or parent_run.tenant_id != tenant_id or parent_run.thread_id is None:
            raise ThreadAccessError("Parent run thread not found")
        parent_thread = await self.db.get(AgentThread, parent_run.thread_id)
        if parent_thread is None or parent_thread.tenant_id != tenant_id:
            raise ThreadAccessError("Parent run thread not found")
        await self._ensure_thread_lineage(parent_thread)
        parent_turn_id = await self.db.scalar(
            select(AgentThreadTurn.id).where(AgentThreadTurn.run_id == parent_run.id).limit(1)
        )
        return ThreadLineageResolveContext(
            root_thread_id=parent_thread.root_thread_id or parent_thread.id,
            parent_thread_id=parent_thread.id,
            parent_thread_turn_id=parent_turn_id,
            spawned_by_run_id=parent_run.id,
            lineage_depth=int(parent_thread.lineage_depth or 0) + 1,
        )

    async def _ensure_thread_lineage(self, thread: AgentThread) -> None:
        changed = False
        if thread.root_thread_id is None:
            thread.root_thread_id = thread.id
            changed = True
        if thread.lineage_depth is None:
            thread.lineage_depth = 0
            changed = True
        if changed:
            await self.db.flush()

    @staticmethod
    def _assert_lineage_compatible(
        *,
        thread: AgentThread,
        lineage_context: ThreadLineageResolveContext | None,
    ) -> None:
        if lineage_context is None:
            return
        thread_root_id = thread.root_thread_id or thread.id
        if str(thread_root_id) != str(lineage_context.root_thread_id):
            raise ThreadAccessError("Thread lineage mismatch")

    async def _build_subtree_node(
        self,
        *,
        thread: AgentThread,
        page: ThreadTurnPage,
        remaining_depth: int,
        turn_limit: int,
        child_limit: int,
    ) -> ThreadSubtreeNode:
        child_threads = await self._load_direct_child_threads(
            tenant_id=thread.tenant_id,
            parent_thread_id=thread.id,
            child_limit=child_limit,
        )
        children: list[ThreadSubtreeNode] = []
        if remaining_depth > 0:
            for child_thread in child_threads:
                child_page = await self._get_thread_turn_page_for_thread(
                    thread=child_thread,
                    limit=turn_limit,
                )
                children.append(
                    await self._build_subtree_node(
                        thread=child_thread,
                        page=child_page,
                        remaining_depth=remaining_depth - 1,
                        turn_limit=turn_limit,
                        child_limit=child_limit,
                    )
                )
        return ThreadSubtreeNode(
            thread=thread,
            page=page,
            children=children,
            has_children=bool(child_threads),
        )

    async def _load_direct_child_threads(
        self,
        *,
        tenant_id: UUID,
        parent_thread_id: UUID,
        child_limit: int,
    ) -> list[AgentThread]:
        rows = (
            await self.db.execute(
                select(AgentThread)
                .where(
                    AgentThread.tenant_id == tenant_id,
                    AgentThread.parent_thread_id == parent_thread_id,
                )
                .options(selectinload(AgentThread.agent))
                .order_by(
                    AgentThread.last_activity_at.desc().nullslast(),
                    AgentThread.updated_at.desc(),
                    AgentThread.created_at.desc(),
                )
                .limit(max(1, int(child_limit)))
            )
        ).scalars().all()
        items = list(rows)
        for item in items:
            await self._ensure_thread_lineage(item)
        return items

    async def _get_thread_turn_page_for_thread(
        self,
        *,
        thread: AgentThread,
        limit: int,
        before_turn_index: int | None = None,
    ) -> ThreadTurnPage:
        safe_limit = max(1, int(limit))
        turn_query = (
            select(AgentThreadTurn)
            .where(AgentThreadTurn.thread_id == thread.id)
            .options(
                joinedload(AgentThreadTurn.run),
                selectinload(AgentThreadTurn.attachment_links).selectinload(AgentThreadTurnAttachment.attachment),
            )
        )
        if before_turn_index is not None:
            turn_query = turn_query.where(AgentThreadTurn.turn_index < int(before_turn_index))
        turn_query = turn_query.order_by(
            desc(AgentThreadTurn.turn_index),
            desc(AgentThreadTurn.created_at),
            desc(AgentThreadTurn.completed_at),
            desc(AgentThreadTurn.id),
        ).limit(safe_limit + 1)
        turn_rows = list((await self.db.execute(turn_query)).scalars().all())
        has_more = len(turn_rows) > safe_limit
        paged_turns = turn_rows[:safe_limit]
        paged_turns.sort(key=self._turn_sort_key)
        next_before_turn_index = None
        if has_more and paged_turns:
            next_before_turn_index = int(paged_turns[0].turn_index or 0)
        return ThreadTurnPage(
            turns=paged_turns,
            has_more=has_more,
            next_before_turn_index=next_before_turn_index,
        )

    async def _collect_descendant_thread_ids(
        self,
        *,
        tenant_id: UUID,
        parent_thread_ids: set[UUID],
    ) -> set[UUID]:
        collected: set[UUID] = set()
        frontier = set(parent_thread_ids)
        while frontier:
            rows = (
                await self.db.execute(
                    select(AgentThread.id)
                    .where(
                        AgentThread.tenant_id == tenant_id,
                        AgentThread.parent_thread_id.in_(frontier),
                    )
                )
            ).scalars().all()
            next_frontier = {UUID(str(item)) for item in rows if UUID(str(item)) not in collected}
            collected.update(next_frontier)
            frontier = next_frontier
        return collected
