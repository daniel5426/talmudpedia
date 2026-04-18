from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppCodingChatSession,
    PublishedAppDraftDevSessionStatus,
    PublishedAppRevision,
)
from app.services.opencode_server_client import OpenCodeServerClient
from app.services.published_app_agent_integration_contract import build_published_app_agent_integration_contract
from app.services.published_app_coding_chat_history_service import PublishedAppCodingChatHistoryService
from app.services.published_app_draft_dev_runtime import (
    PublishedAppDraftDevRuntimeDisabled,
    PublishedAppDraftDevRuntimeService,
)

CODING_AGENT_OPENCODE_AUTO_MODEL_ID = "opencode/big-pickle"


class PublishedAppCodingChatSessionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.history = PublishedAppCodingChatHistoryService(db)
        self.client = OpenCodeServerClient.from_env()

    @staticmethod
    def _normalize_model_id(raw_model_id: str | None) -> str | None:
        raw = str(raw_model_id or "").strip()
        if not raw:
            return None
        if "/" not in raw:
            raw = f"opencode/{raw}"
        provider, model = raw.split("/", 1)
        provider = provider.strip().lower()
        model = model.strip()
        if provider != "opencode" or not model:
            return None
        return f"{provider}/{model}"

    def _resolve_requested_model_id(self, requested_model_id: str | None) -> str:
        requested = self._normalize_model_id(requested_model_id)
        if requested_model_id and not requested:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "CODING_AGENT_MODEL_UNAVAILABLE",
                    "field": "model_id",
                    "message": "Selected model must be an OpenCode model id.",
                },
            )
        return requested or CODING_AGENT_OPENCODE_AUTO_MODEL_ID

    @staticmethod
    def _include_agent_contract() -> bool:
        raw = str(os.getenv("APPS_CODING_AGENT_INCLUDE_AGENT_CONTRACT", "1") or "1").strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _is_invalid_session_error(exc: Exception) -> bool:
        message = str(exc or "").strip().lower()
        return any(
            token in message
            for token in (
                "session not found",
                "invalid session",
                "unknown session",
                "missing session",
                "session does not exist",
            )
        )

    @staticmethod
    def _session_matches_runtime(
        session: PublishedAppCodingChatSession,
        *,
        sandbox_id: str,
        workspace_path: str,
    ) -> bool:
        return (
            str(session.opencode_session_id or "").strip()
            and str(session.opencode_sandbox_id or "").strip() == str(sandbox_id or "").strip()
            and str(session.opencode_workspace_path or "").strip() == str(workspace_path or "").strip()
        )

    @staticmethod
    def _text_from_parts(parts: list[dict[str, Any]]) -> str:
        chunks: list[str] = []
        for part in parts or []:
            if not isinstance(part, dict):
                continue
            part_type = str(part.get("type") or "").strip().lower()
            if part_type not in {"text", "reasoning"}:
                continue
            text = str(part.get("text") or "").strip()
            if text:
                chunks.append(text)
        return "\n".join(chunks).strip()

    @staticmethod
    def _message_created_at(info: dict[str, Any]) -> datetime:
        time_payload = info.get("time") if isinstance(info.get("time"), dict) else {}
        created_raw = time_payload.get("created")
        try:
            created_ms = int(created_raw)
        except Exception:
            return datetime.now(timezone.utc)
        return datetime.fromtimestamp(created_ms / 1000.0, tz=timezone.utc)

    @staticmethod
    def _serialize_part(part: dict[str, Any]) -> dict[str, Any]:
        part_type = str(part.get("type") or "").strip().lower()
        payload: dict[str, Any] = {
            "id": str(part.get("id") or "").strip(),
            "message_id": str(part.get("messageID") or part.get("messageId") or "").strip(),
            "type": part_type,
        }
        if part_type in {"text", "reasoning"}:
            payload["text"] = str(part.get("text") or "")
            return payload
        if part_type == "tool":
            state = part.get("state") if isinstance(part.get("state"), dict) else {}
            payload.update(
                {
                    "call_id": str(part.get("callID") or part.get("callId") or "").strip() or None,
                    "tool": str(part.get("tool") or "").strip() or None,
                    "state": {
                        "status": str(state.get("status") or "").strip() or None,
                        "title": str(state.get("title") or "").strip() or None,
                        "input": state.get("input"),
                        "output": state.get("output"),
                        "error": str(state.get("error") or "").strip() or None,
                        "metadata": state.get("metadata") if isinstance(state.get("metadata"), dict) else None,
                    },
                }
            )
            return payload
        return payload

    def _serialize_remote_message(self, item: dict[str, Any]) -> dict[str, Any] | None:
        info = item.get("info") if isinstance(item.get("info"), dict) else {}
        role = str(info.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            return None
        message_id = str(info.get("id") or "").strip()
        if not message_id:
            return None
        parts = item.get("parts") if isinstance(item.get("parts"), list) else []
        normalized_parts = [self._serialize_part(part) for part in parts if isinstance(part, dict)]
        return {
            "id": message_id,
            "role": role,
            "content": self._text_from_parts(normalized_parts),
            "parts": normalized_parts,
            "created_at": self._message_created_at(info),
        }

    async def create_chat_session(
        self,
        *,
        app: PublishedApp,
        actor_id: UUID,
        title: str | None = None,
    ) -> PublishedAppCodingChatSession:
        return await self.history.create_session(
            app_id=app.id,
            user_id=actor_id,
            title=title,
        )

    async def get_chat_session_for_user(
        self,
        *,
        app: PublishedApp,
        actor_id: UUID,
        session_id: UUID,
    ) -> PublishedAppCodingChatSession:
        session = await self.history.get_session_for_user(
            app_id=app.id,
            user_id=actor_id,
            session_id=session_id,
        )
        if session is None:
            raise HTTPException(status_code=404, detail="Coding-agent chat session not found")
        return session

    async def _selected_agent_contract(self, *, app: PublishedApp) -> dict[str, Any] | None:
        if not self._include_agent_contract():
            return None
        try:
            return await build_published_app_agent_integration_contract(db=self.db, app=app)
        except Exception as exc:
            return {"error": str(exc) or "Failed to resolve selected agent contract"}

    async def _ensure_remote_session(
        self,
        *,
        app: PublishedApp,
        base_revision: PublishedAppRevision,
        actor_id: UUID,
        chat_session: PublishedAppCodingChatSession,
        requested_model_id: str | None,
    ) -> dict[str, Any]:
        await self.client.ensure_healthy()
        resolved_model_id = self._resolve_requested_model_id(requested_model_id)
        selected_agent_contract = await self._selected_agent_contract(app=app)
        runtime_service = PublishedAppDraftDevRuntimeService(self.db)
        try:
            draft_session = await runtime_service.ensure_active_session(
                app=app,
                revision=base_revision,
                user_id=actor_id,
                prefer_live_workspace=True,
                trace_source="coding_agent.chat",
            )
        except PublishedAppDraftDevRuntimeDisabled as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "CODING_AGENT_ENGINE_UNSUPPORTED_RUNTIME",
                    "field": "engine",
                    "message": str(exc),
                },
            ) from exc
        if draft_session.status == PublishedAppDraftDevSessionStatus.error or not draft_session.sandbox_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "CODING_AGENT_ENGINE_UNSUPPORTED_RUNTIME",
                    "field": "engine",
                    "message": f"Failed to initialize preview sandbox session: {draft_session.last_error or 'unknown error'}",
                },
            )
        sandbox_id = str(draft_session.sandbox_id)
        workspace_path = str(
            await runtime_service.client.resolve_local_workspace_path(sandbox_id=sandbox_id) or ""
        ).strip() or "/workspace"
        remote_session_id = str(chat_session.opencode_session_id or "").strip()
        if not self._session_matches_runtime(chat_session, sandbox_id=sandbox_id, workspace_path=workspace_path):
            remote_session_id = await self.client.create_session(
                run_id=f"chat-{chat_session.id}",
                app_id=str(app.id),
                sandbox_id=sandbox_id,
                workspace_path=workspace_path,
                model_id=resolved_model_id,
                selected_agent_contract=selected_agent_contract,
            )
            chat_session.opencode_session_id = remote_session_id
            chat_session.opencode_sandbox_id = sandbox_id
            chat_session.opencode_workspace_path = workspace_path
            chat_session.opencode_session_opened_at = datetime.now(timezone.utc)
            chat_session.opencode_session_closed_at = None
            await self.db.commit()
            await self.db.refresh(chat_session)
        return {
            "session_id": remote_session_id,
            "sandbox_id": sandbox_id,
            "workspace_path": workspace_path,
            "model_id": resolved_model_id,
            "selected_agent_contract": selected_agent_contract,
        }

    async def submit_message(
        self,
        *,
        app: PublishedApp,
        base_revision: PublishedAppRevision,
        actor_id: UUID,
        chat_session: PublishedAppCodingChatSession,
        message_id: str,
        parts: list[dict[str, Any]],
        requested_model_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_message_id = OpenCodeServerClient.normalize_message_id(message_id)
        normalized_parts = OpenCodeServerClient.normalize_request_parts(parts)
        context = await self._ensure_remote_session(
            app=app,
            base_revision=base_revision,
            actor_id=actor_id,
            chat_session=chat_session,
            requested_model_id=requested_model_id,
        )
        try:
            await self.client.prompt_async(
                session_id=context["session_id"],
                app_id=str(app.id),
                message_id=normalized_message_id,
                parts=normalized_parts,
                model_id=context["model_id"],
                sandbox_id=context["sandbox_id"],
                workspace_path=context["workspace_path"],
                selected_agent_contract=context["selected_agent_contract"],
            )
        except Exception as exc:
            if not self._is_invalid_session_error(exc):
                raise
            chat_session.opencode_session_id = None
            chat_session.opencode_sandbox_id = None
            chat_session.opencode_workspace_path = None
            chat_session.opencode_session_closed_at = datetime.now(timezone.utc)
            await self.db.commit()
            context = await self._ensure_remote_session(
                app=app,
                base_revision=base_revision,
                actor_id=actor_id,
                chat_session=chat_session,
                requested_model_id=requested_model_id,
            )
            await self.client.prompt_async(
                session_id=context["session_id"],
                app_id=str(app.id),
                message_id=normalized_message_id,
                parts=normalized_parts,
                model_id=context["model_id"],
                sandbox_id=context["sandbox_id"],
                workspace_path=context["workspace_path"],
                selected_agent_contract=context["selected_agent_contract"],
            )
        await self.history.touch_session(session_id=chat_session.id)
        return {
            "submission_status": "accepted",
            "chat_session_id": str(chat_session.id),
            "message": {
                "id": str(normalized_message_id),
                "role": "user",
                "content": self._text_from_parts(normalized_parts),
                "parts": [self._serialize_part(part) for part in normalized_parts if isinstance(part, dict)],
                "created_at": datetime.now(timezone.utc),
            },
        }

    async def list_remote_messages(
        self,
        *,
        chat_session: PublishedAppCodingChatSession,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        remote_session_id = str(chat_session.opencode_session_id or "").strip()
        if not remote_session_id:
            return []
        try:
            items = await self.client.list_messages(
                session_id=remote_session_id,
                sandbox_id=str(chat_session.opencode_sandbox_id or "").strip() or None,
                workspace_path=str(chat_session.opencode_workspace_path or "").strip() or None,
                limit=limit,
            )
        except Exception as exc:
            if not self._is_invalid_session_error(exc):
                raise
            chat_session.opencode_session_closed_at = datetime.now(timezone.utc)
            chat_session.opencode_session_id = None
            chat_session.opencode_sandbox_id = None
            chat_session.opencode_workspace_path = None
            await self.db.commit()
            return []
        messages = [item for item in (self._serialize_remote_message(raw) for raw in items) if item is not None]
        if messages:
            latest = max(message["created_at"] for message in messages if isinstance(message.get("created_at"), datetime))
            await self.history.touch_session(session_id=chat_session.id, at=latest)
        return messages

    async def abort_chat_session(self, *, chat_session: PublishedAppCodingChatSession) -> bool:
        remote_session_id = str(chat_session.opencode_session_id or "").strip()
        if not remote_session_id:
            return False
        return await self.client.abort_session(
            session_id=remote_session_id,
            sandbox_id=str(chat_session.opencode_sandbox_id or "").strip() or None,
            workspace_path=str(chat_session.opencode_workspace_path or "").strip() or None,
        )

    async def reply_request(
        self,
        *,
        chat_session: PublishedAppCodingChatSession,
        request_id: str,
        answers: list[list[str]],
    ) -> bool:
        remote_session_id = str(chat_session.opencode_session_id or "").strip()
        if not remote_session_id:
            raise HTTPException(status_code=409, detail="OpenCode session is not initialized for this chat.")
        return await self.client.reply_request(
            session_id=remote_session_id,
            request_id=request_id,
            answers=answers,
            sandbox_id=str(chat_session.opencode_sandbox_id or "").strip() or None,
            workspace_path=str(chat_session.opencode_workspace_path or "").strip() or None,
        )
