from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, delete, desc, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.agent_threads import AgentThread
from app.db.postgres.models.artifact_runtime import ArtifactCodingMessage, ArtifactCodingSession


TERMINAL_RUN_STATUSES = {
    RunStatus.completed.value,
    RunStatus.failed.value,
    RunStatus.cancelled.value,
}


class ArtifactCodingChatHistoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _session_title_from_prompt(prompt: str) -> str:
        collapsed = " ".join(str(prompt or "").strip().split())
        if not collapsed:
            return "New Chat"
        if len(collapsed) <= 80:
            return collapsed
        return collapsed[:77].rstrip() + "..."

    @staticmethod
    def _extract_assistant_output_text(run: AgentRun | None) -> str | None:
        if run is None:
            return None
        output_result = run.output_result if isinstance(run.output_result, dict) else {}
        messages = output_result.get("messages")
        if isinstance(messages, list):
            last_assistant: str | None = None
            for item in messages:
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role") or item.get("type") or "").strip().lower()
                if role not in {"assistant", "ai"}:
                    continue
                content = str(item.get("content") or "").strip()
                if content:
                    last_assistant = content
            if last_assistant:
                return last_assistant
        final_output = output_result.get("final_output")
        if isinstance(final_output, str) and final_output.strip():
            return final_output.strip()
        state = output_result.get("state")
        if isinstance(state, dict):
            last_output = state.get("last_agent_output")
            if isinstance(last_output, str) and last_output.strip():
                return last_output.strip()
        return None

    def serialize_session(self, session: ArtifactCodingSession) -> dict[str, Any]:
        return {
            "id": str(session.id),
            "title": session.title,
            "artifact_id": str(session.artifact_id) if session.artifact_id else None,
            "draft_key": session.draft_key,
            "agent_thread_id": str(session.agent_thread_id),
            "active_run_id": str(session.active_run_id) if session.active_run_id else None,
            "last_run_id": str(session.last_run_id) if session.last_run_id else None,
            "linked_artifact_id": str(session.linked_artifact_id) if session.linked_artifact_id else None,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "last_message_at": session.last_message_at,
        }

    @staticmethod
    def serialize_message(message: ArtifactCodingMessage) -> dict[str, Any]:
        return {
            "id": str(message.id),
            "run_id": str(message.run_id),
            "role": str(message.role),
            "content": message.content,
            "created_at": message.created_at,
        }

    async def get_session_for_user(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID | None,
        session_id: UUID,
    ) -> ArtifactCodingSession | None:
        result = await self.db.execute(
            select(ArtifactCodingSession)
            .join(AgentThread, ArtifactCodingSession.agent_thread_id == AgentThread.id)
            .where(
                and_(
                    ArtifactCodingSession.id == session_id,
                    ArtifactCodingSession.tenant_id == tenant_id,
                    AgentThread.user_id == user_id,
                )
            )
        )
        session = result.scalar_one_or_none()
        return session

    async def create_session(
        self,
        *,
        tenant_id: UUID,
        artifact_id: UUID | None,
        draft_key: str | None,
        agent_thread_id: UUID,
        title_prompt: str,
    ) -> ArtifactCodingSession:
        session = ArtifactCodingSession(
            tenant_id=tenant_id,
            artifact_id=artifact_id,
            draft_key=draft_key,
            agent_thread_id=agent_thread_id,
            title=self._session_title_from_prompt(title_prompt),
            last_message_at=datetime.now(timezone.utc),
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def list_sessions(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID | None,
        artifact_id: UUID | None,
        draft_key: str | None,
        limit: int = 25,
    ) -> list[ArtifactCodingSession]:
        stmt = (
            select(ArtifactCodingSession)
            .join(AgentThread, ArtifactCodingSession.agent_thread_id == AgentThread.id)
            .where(ArtifactCodingSession.tenant_id == tenant_id)
        )
        if user_id is not None:
            stmt = stmt.where(AgentThread.user_id == user_id)
        if artifact_id is not None:
            stmt = stmt.where(
                or_(
                    ArtifactCodingSession.artifact_id == artifact_id,
                    ArtifactCodingSession.linked_artifact_id == artifact_id,
                )
            )
        elif draft_key:
            stmt = stmt.where(ArtifactCodingSession.draft_key == draft_key)
        else:
            return []
        result = await self.db.execute(
            stmt.order_by(ArtifactCodingSession.last_message_at.desc(), ArtifactCodingSession.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def link_sessions_to_artifact(
        self,
        *,
        tenant_id: UUID,
        draft_key: str,
        artifact_id: UUID,
    ) -> int:
        if not draft_key:
            return 0
        result = await self.db.execute(
            update(ArtifactCodingSession)
            .where(
                and_(
                    ArtifactCodingSession.tenant_id == tenant_id,
                    ArtifactCodingSession.draft_key == draft_key,
                )
            )
            .values(
                artifact_id=artifact_id,
                linked_artifact_id=artifact_id,
                linked_at=datetime.now(timezone.utc),
            )
        )
        return int(result.rowcount or 0)

    async def update_session_scope(
        self,
        *,
        session: ArtifactCodingSession,
        artifact_id: UUID | None,
        draft_key: str | None,
    ) -> ArtifactCodingSession:
        if artifact_id is not None:
            session.artifact_id = artifact_id
            session.linked_artifact_id = artifact_id
            session.linked_at = session.linked_at or datetime.now(timezone.utc)
        if draft_key:
            session.draft_key = draft_key
        session.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return session

    async def mark_run_started(
        self,
        *,
        session: ArtifactCodingSession,
        run_id: UUID,
    ) -> None:
        session.active_run_id = run_id
        session.last_run_id = run_id
        session.last_message_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def list_messages_page(
        self,
        *,
        session_id: UUID,
        limit: int = 10,
        before_message_id: UUID | None = None,
    ) -> tuple[list[ArtifactCodingMessage], bool, UUID | None]:
        query = select(ArtifactCodingMessage).where(ArtifactCodingMessage.session_id == session_id)
        if before_message_id is not None:
            cursor_message = await self.db.get(ArtifactCodingMessage, before_message_id)
            if cursor_message is None or cursor_message.session_id != session_id:
                raise HTTPException(status_code=404, detail="Paging cursor message not found for this chat session")
            query = query.where(
                or_(
                    ArtifactCodingMessage.created_at < cursor_message.created_at,
                    and_(
                        ArtifactCodingMessage.created_at == cursor_message.created_at,
                        ArtifactCodingMessage.id < cursor_message.id,
                    ),
                )
            )

        result = await self.db.execute(
            query.order_by(desc(ArtifactCodingMessage.created_at), desc(ArtifactCodingMessage.id)).limit(limit + 1)
        )
        newest_first = list(result.scalars().all())
        has_more = len(newest_first) > limit
        if has_more:
            newest_first = newest_first[:limit]
        chronological = list(reversed(newest_first))
        next_before_message_id = chronological[0].id if chronological and has_more else None
        return chronological, has_more, next_before_message_id

    async def build_run_messages(
        self,
        *,
        session_id: UUID,
        current_user_prompt: str,
        limit: int = 120,
    ) -> list[dict[str, str]]:
        result = await self.db.execute(
            select(ArtifactCodingMessage)
            .where(ArtifactCodingMessage.session_id == session_id)
            .order_by(ArtifactCodingMessage.created_at.desc())
            .limit(limit)
        )
        messages = list(reversed(list(result.scalars().all())))
        payload: list[dict[str, str]] = []
        for message in messages:
            role = str(message.role or "").strip().lower()
            if role not in {"user", "assistant"}:
                continue
            content = str(message.content or "").strip()
            if not content:
                continue
            payload.append({"role": role, "content": content})

        prompt = str(current_user_prompt or "").strip()
        if prompt and (not payload or payload[-1].get("role") != "user" or payload[-1].get("content") != prompt):
            payload.append({"role": "user", "content": prompt})
        return payload

    async def persist_user_message(
        self,
        *,
        session_id: UUID,
        run_id: UUID,
        content: str,
    ) -> ArtifactCodingMessage | None:
        return await self._persist_message(session_id=session_id, run_id=run_id, role="user", content=content)

    async def persist_assistant_message(
        self,
        *,
        session_id: UUID,
        run_id: UUID,
        content: str,
    ) -> ArtifactCodingMessage | None:
        return await self._persist_message(session_id=session_id, run_id=run_id, role="assistant", content=content)

    async def _persist_message(
        self,
        *,
        session_id: UUID,
        run_id: UUID,
        role: str,
        content: str,
    ) -> ArtifactCodingMessage | None:
        message_content = str(content or "").strip()
        if not message_content:
            return None
        stmt = (
            insert(ArtifactCodingMessage)
            .values(
                session_id=session_id,
                run_id=run_id,
                role=role,
                content=message_content,
            )
            .on_conflict_do_nothing(
                index_elements=[ArtifactCodingMessage.run_id, ArtifactCodingMessage.role]
            )
            .returning(ArtifactCodingMessage.id, ArtifactCodingMessage.created_at)
        )
        result = await self.db.execute(stmt)
        row = result.first()
        inserted_id: UUID | None = None
        created_at: datetime | None = None
        if row is not None:
            inserted_id = row[0]
            created_at = row[1]
        else:
            existing = (
                await self.db.execute(
                    select(ArtifactCodingMessage).where(
                        and_(
                            ArtifactCodingMessage.run_id == run_id,
                            ArtifactCodingMessage.role == role,
                        )
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                inserted_id = existing.id
                created_at = existing.created_at

        await self.db.execute(
            update(ArtifactCodingSession)
            .where(ArtifactCodingSession.id == session_id)
            .values(last_message_at=created_at or datetime.now(timezone.utc))
        )
        if inserted_id is None:
            return None
        return await self.db.get(ArtifactCodingMessage, inserted_id)

    async def reconcile_session_run(self, *, session: ArtifactCodingSession, run: AgentRun) -> ArtifactCodingSession:
        status = str(getattr(run.status, "value", run.status) or "").strip().lower()
        if status in TERMINAL_RUN_STATUSES:
            if session.active_run_id == run.id:
                session.active_run_id = None
            assistant_text = self._extract_assistant_output_text(run)
            if assistant_text:
                await self.persist_assistant_message(
                    session_id=session.id,
                    run_id=run.id,
                    content=assistant_text,
                )
        else:
            session.active_run_id = run.id
        session.last_run_id = run.id
        session.last_message_at = datetime.now(timezone.utc)
        await self.db.flush()
        return session

    async def truncate_session_after_run(
        self,
        *,
        session: ArtifactCodingSession,
        run_id: UUID,
    ) -> ArtifactCodingMessage:
        anchor_message = (
            await self.db.execute(
                select(ArtifactCodingMessage)
                .where(
                    and_(
                        ArtifactCodingMessage.session_id == session.id,
                        ArtifactCodingMessage.run_id == run_id,
                        ArtifactCodingMessage.role == "user",
                    )
                )
                .order_by(ArtifactCodingMessage.created_at.asc(), ArtifactCodingMessage.id.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if anchor_message is None:
            raise HTTPException(status_code=404, detail="Artifact coding user message not found for this run")

        await self.db.execute(
            delete(ArtifactCodingMessage).where(
                and_(
                    ArtifactCodingMessage.session_id == session.id,
                    or_(
                        ArtifactCodingMessage.created_at > anchor_message.created_at,
                        and_(
                            ArtifactCodingMessage.created_at == anchor_message.created_at,
                            ArtifactCodingMessage.id > anchor_message.id,
                        ),
                    ),
                )
            )
        )

        session.active_run_id = None
        session.last_run_id = run_id
        session.last_message_at = anchor_message.created_at or datetime.now(timezone.utc)
        session.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return anchor_message
