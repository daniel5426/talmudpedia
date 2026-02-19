from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.published_apps import (
    PublishedAppCodingChatMessage,
    PublishedAppCodingChatMessageRole,
    PublishedAppCodingChatSession,
)


class PublishedAppCodingChatHistoryService:
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

    async def get_session_for_user(
        self,
        *,
        app_id: UUID,
        user_id: UUID,
        session_id: UUID,
    ) -> PublishedAppCodingChatSession | None:
        result = await self.db.execute(
            select(PublishedAppCodingChatSession).where(
                and_(
                    PublishedAppCodingChatSession.id == session_id,
                    PublishedAppCodingChatSession.published_app_id == app_id,
                    PublishedAppCodingChatSession.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def resolve_or_create_session(
        self,
        *,
        app_id: UUID,
        user_id: UUID,
        user_prompt: str,
        session_id: UUID | None,
    ) -> PublishedAppCodingChatSession:
        if session_id is not None:
            existing = await self.get_session_for_user(
                app_id=app_id,
                user_id=user_id,
                session_id=session_id,
            )
            if existing is None:
                raise HTTPException(status_code=404, detail="Coding-agent chat session not found")
            return existing

        session = PublishedAppCodingChatSession(
            published_app_id=app_id,
            user_id=user_id,
            title=self._session_title_from_prompt(user_prompt),
            last_message_at=datetime.now(timezone.utc),
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def list_sessions(
        self,
        *,
        app_id: UUID,
        user_id: UUID,
        limit: int = 25,
    ) -> list[PublishedAppCodingChatSession]:
        result = await self.db.execute(
            select(PublishedAppCodingChatSession)
            .where(
                and_(
                    PublishedAppCodingChatSession.published_app_id == app_id,
                    PublishedAppCodingChatSession.user_id == user_id,
                )
            )
            .order_by(PublishedAppCodingChatSession.last_message_at.desc(), PublishedAppCodingChatSession.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_messages(
        self,
        *,
        session_id: UUID,
        limit: int = 200,
    ) -> list[PublishedAppCodingChatMessage]:
        # Fetch newest first for index efficiency, then present oldest->newest.
        result = await self.db.execute(
            select(PublishedAppCodingChatMessage)
            .where(PublishedAppCodingChatMessage.session_id == session_id)
            .order_by(PublishedAppCodingChatMessage.created_at.desc())
            .limit(limit)
        )
        return list(reversed(list(result.scalars().all())))

    async def build_run_messages(
        self,
        *,
        session_id: UUID,
        current_user_prompt: str,
        limit: int = 120,
    ) -> list[dict[str, str]]:
        messages = await self.list_messages(session_id=session_id, limit=limit)
        payload: list[dict[str, str]] = []
        for message in messages:
            role = str(message.role.value if hasattr(message.role, "value") else message.role or "").strip().lower()
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
    ) -> PublishedAppCodingChatMessage | None:
        return await self._persist_message(
            session_id=session_id,
            run_id=run_id,
            role=PublishedAppCodingChatMessageRole.user,
            content=content,
        )

    async def persist_assistant_message(
        self,
        *,
        session_id: UUID,
        run_id: UUID,
        content: str,
    ) -> PublishedAppCodingChatMessage | None:
        return await self._persist_message(
            session_id=session_id,
            run_id=run_id,
            role=PublishedAppCodingChatMessageRole.assistant,
            content=content,
        )

    async def _persist_message(
        self,
        *,
        session_id: UUID,
        run_id: UUID,
        role: PublishedAppCodingChatMessageRole,
        content: str,
    ) -> PublishedAppCodingChatMessage | None:
        message_content = str(content or "").strip()
        if not message_content:
            return None

        stmt = (
            insert(PublishedAppCodingChatMessage)
            .values(
                session_id=session_id,
                run_id=run_id,
                role=role,
                content=message_content,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    PublishedAppCodingChatMessage.run_id,
                    PublishedAppCodingChatMessage.role,
                ],
            )
            .returning(
                PublishedAppCodingChatMessage.id,
                PublishedAppCodingChatMessage.created_at,
            )
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
                    select(PublishedAppCodingChatMessage).where(
                        and_(
                            PublishedAppCodingChatMessage.run_id == run_id,
                            PublishedAppCodingChatMessage.role == role,
                        )
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                inserted_id = existing.id
                created_at = existing.created_at

        await self.db.execute(
            update(PublishedAppCodingChatSession)
            .where(PublishedAppCodingChatSession.id == session_id)
            .values(
                last_message_at=created_at or func.now(),
                updated_at=func.now(),
            )
        )
        await self.db.commit()

        if inserted_id is None:
            return None
        return await self.db.get(PublishedAppCodingChatMessage, inserted_id)

    @staticmethod
    def serialize_session(session: PublishedAppCodingChatSession) -> dict[str, Any]:
        return {
            "id": str(session.id),
            "title": str(session.title or "").strip() or "New Chat",
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "last_message_at": session.last_message_at,
        }

    @staticmethod
    def serialize_message(message: PublishedAppCodingChatMessage) -> dict[str, Any]:
        role = str(message.role.value if hasattr(message.role, "value") else message.role or "").strip().lower()
        return {
            "id": str(message.id),
            "run_id": str(message.run_id),
            "role": role,
            "content": str(message.content or ""),
            "created_at": message.created_at,
        }
