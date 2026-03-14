from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionMode
from app.db.postgres.models.agent_threads import AgentThreadSurface
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.artifact_runtime import Artifact, ArtifactCodingSession, ArtifactCodingSharedDraft, ArtifactRun
from app.services.artifact_coding_agent_profile import ensure_artifact_coding_agent_profile
from app.services.artifact_coding_agent_tools import (
    ARTIFACT_CODING_AGENT_SURFACE,
    DEFAULT_AGENT_CONTRACT,
    DEFAULT_CAPABILITIES,
    DEFAULT_CONFIG_SCHEMA,
    DEFAULT_RAG_CONTRACT,
    DEFAULT_TOOL_CONTRACT,
    _initial_snapshot_for_kind,
    _normalize_file_list,
    _parse_json_object,
    _serialize_form_state,
)
from app.services.artifact_coding_chat_history_service import ArtifactCodingChatHistoryService
from app.services.artifact_coding_shared_draft_service import ArtifactCodingSharedDraftService
from app.services.artifact_runtime.registry_service import ArtifactRegistryService
from app.services.thread_service import ThreadService


@dataclass
class PreparedArtifactCodingSession:
    session: ArtifactCodingSession
    shared_draft: ArtifactCodingSharedDraft
    agent_thread_id: UUID


class ArtifactCodingRuntimeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.history = ArtifactCodingChatHistoryService(db)
        self.shared_drafts = ArtifactCodingSharedDraftService(db)
        self.registry = ArtifactRegistryService(db)

    @staticmethod
    def _normalize_draft_key(value: str | None) -> str | None:
        text = str(value or "").strip()
        return text or None

    async def _get_session_for_user(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        session_id: UUID,
    ) -> ArtifactCodingSession:
        session = await self.history.get_session_for_user(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        if session is None:
            raise ValueError("Artifact coding chat session not found")
        return session

    @staticmethod
    def _snapshot_from_artifact(artifact: Artifact | None) -> dict[str, Any]:
        if artifact is None:
            return _initial_snapshot_for_kind("agent_node")
        revision = artifact.latest_draft_revision or artifact.latest_published_revision
        if revision is None:
            return _initial_snapshot_for_kind(getattr(artifact.kind, "value", artifact.kind))
        kind = getattr(artifact.kind, "value", artifact.kind)
        return _serialize_form_state(
            {
                "slug": artifact.slug,
                "display_name": artifact.display_name,
                "description": artifact.description or "",
                "kind": kind,
                "source_files": list(revision.source_files or []),
                "entry_module_path": revision.entry_module_path,
                "python_dependencies": ", ".join(list(revision.python_dependencies or [])),
                "runtime_target": revision.runtime_target,
                "capabilities": deepcopy(revision.capabilities or DEFAULT_CAPABILITIES),
                "config_schema": deepcopy(revision.config_schema or DEFAULT_CONFIG_SCHEMA),
                "agent_contract": deepcopy(revision.agent_contract or DEFAULT_AGENT_CONTRACT),
                "rag_contract": deepcopy(revision.rag_contract or DEFAULT_RAG_CONTRACT),
                "tool_contract": deepcopy(revision.tool_contract or DEFAULT_TOOL_CONTRACT),
            }
        )

    async def _resolve_initial_snapshot(
        self,
        *,
        tenant_id: UUID,
        artifact_id: UUID | None,
        draft_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if isinstance(draft_snapshot, dict) and draft_snapshot:
            return _serialize_form_state(draft_snapshot)
        if artifact_id is not None:
            artifact = await self.registry.get_tenant_artifact(
                artifact_id=artifact_id,
                tenant_id=tenant_id,
            )
            return self._snapshot_from_artifact(artifact)
        return _initial_snapshot_for_kind("agent_node")

    async def prepare_session(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        agent_id: UUID,
        title_prompt: str,
        artifact_id: UUID | None,
        draft_key: str | None,
        chat_session_id: UUID | None,
        draft_snapshot: dict[str, Any] | None,
        replace_snapshot: bool,
    ) -> PreparedArtifactCodingSession:
        draft_key = self._normalize_draft_key(draft_key)
        initial_snapshot = await self._resolve_initial_snapshot(
            tenant_id=tenant_id,
            artifact_id=artifact_id,
            draft_snapshot=draft_snapshot,
        )
        if chat_session_id is not None:
            session = await self._get_session_for_user(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=chat_session_id,
            )
            shared_draft = await self.shared_drafts.resolve_for_session(session=session)
            await self.history.update_session_scope(
                session=session,
                artifact_id=artifact_id,
                draft_key=draft_key,
            )
        else:
            thread = (
                await ThreadService(self.db).resolve_or_create_thread(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    app_account_id=None,
                    agent_id=agent_id,
                    published_app_id=None,
                    surface=AgentThreadSurface.artifact_admin,
                    thread_id=None,
                    input_text=title_prompt,
                )
            ).thread
            session = await self.history.create_session(
                tenant_id=tenant_id,
                artifact_id=artifact_id,
                draft_key=draft_key,
                agent_thread_id=thread.id,
                title_prompt=title_prompt,
            )
            shared_draft = await self.shared_drafts.get_or_create_for_scope(
                tenant_id=tenant_id,
                artifact_id=artifact_id,
                draft_key=draft_key,
                initial_snapshot=initial_snapshot,
            )

        if replace_snapshot:
            await self.shared_drafts.update_snapshot(
                shared_draft=shared_draft,
                draft_snapshot=initial_snapshot,
                artifact_id=artifact_id,
                draft_key=draft_key,
            )
        elif artifact_id is not None or draft_key:
            await self.shared_drafts.update_snapshot(
                shared_draft=shared_draft,
                draft_snapshot=shared_draft.working_draft_snapshot or initial_snapshot,
                artifact_id=artifact_id,
                draft_key=draft_key,
            )

        if artifact_id is not None and draft_key:
            await self.history.link_sessions_to_artifact(
                tenant_id=tenant_id,
                draft_key=draft_key,
                artifact_id=artifact_id,
            )
            await self.shared_drafts.link_scope_to_artifact(
                tenant_id=tenant_id,
                draft_key=draft_key,
                artifact_id=artifact_id,
            )

        return PreparedArtifactCodingSession(
            session=session,
            shared_draft=shared_draft,
            agent_thread_id=session.agent_thread_id,
        )

    async def start_prompt_run(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        user_prompt: str,
        artifact_id: UUID | None,
        draft_key: str | None,
        chat_session_id: UUID | None,
        draft_snapshot: dict[str, Any] | None,
        model_id: str | None,
    ) -> tuple[ArtifactCodingSession, ArtifactCodingSharedDraft, AgentRun]:
        agent = await ensure_artifact_coding_agent_profile(self.db, tenant_id, actor_user_id=user_id)
        prepared = await self.prepare_session(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent.id,
            title_prompt=user_prompt,
            artifact_id=artifact_id,
            draft_key=draft_key,
            chat_session_id=chat_session_id,
            draft_snapshot=draft_snapshot,
            replace_snapshot=True,
        )
        session = prepared.session
        shared_draft = prepared.shared_draft

        if session.active_run_id is not None:
            active_run = await self.db.get(AgentRun, session.active_run_id)
            if active_run is not None and str(getattr(active_run.status, "value", active_run.status)) not in {
                RunStatus.completed.value,
                RunStatus.failed.value,
                RunStatus.cancelled.value,
            }:
                raise RuntimeError("CODING_AGENT_RUN_ACTIVE")

        run_messages = await self.history.build_run_messages(
            session_id=session.id,
            current_user_prompt=user_prompt,
        )
        request_context = {
            "surface": ARTIFACT_CODING_AGENT_SURFACE,
            "artifact_coding_session_id": str(session.id),
            "artifact_id": str(artifact_id) if artifact_id else None,
            "draft_key": self._normalize_draft_key(draft_key),
            "requested_model_id": model_id,
            "thread_id": str(prepared.agent_thread_id),
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
            "initiator_user_id": str(user_id),
        }
        input_params = {
            "messages": run_messages,
            "input": user_prompt,
            "thread_id": str(prepared.agent_thread_id),
            "context": request_context,
        }
        executor = AgentExecutorService(db=self.db)
        run_id = await executor.start_run(
            agent_id=agent.id,
            input_params=input_params,
            user_id=user_id,
            background=False,
            mode=ExecutionMode.DEBUG,
            requested_scopes=[],
            thread_id=prepared.agent_thread_id,
        )
        run = await self.db.get(AgentRun, run_id)
        if run is None:
            raise RuntimeError("Artifact coding run was not created")
        run.surface = ARTIFACT_CODING_AGENT_SURFACE
        await self.history.mark_run_started(session=session, run_id=run.id)
        await self.shared_drafts.set_last_run(shared_draft=shared_draft, run_id=run.id)
        await self.shared_drafts.create_run_snapshot(
            shared_draft=shared_draft,
            run_id=run.id,
            session_id=session.id,
        )
        await self.history.persist_user_message(
            session_id=session.id,
            run_id=run.id,
            content=user_prompt,
        )
        await self.db.commit()
        await self.db.refresh(session)
        await self.db.refresh(run)
        return session, shared_draft, run

    async def reconcile_session_run(
        self,
        *,
        session: ArtifactCodingSession,
        run: AgentRun,
    ) -> None:
        await self.history.reconcile_session_run(session=session, run=run)
        await self.db.commit()

    async def register_spawned_run(
        self,
        *,
        session: ArtifactCodingSession,
        shared_draft: ArtifactCodingSharedDraft,
        run: AgentRun,
        user_prompt: str,
    ) -> None:
        await self.history.mark_run_started(session=session, run_id=run.id)
        await self.shared_drafts.set_last_run(shared_draft=shared_draft, run_id=run.id)
        await self.shared_drafts.create_run_snapshot(
            shared_draft=shared_draft,
            run_id=run.id,
            session_id=session.id,
        )
        await self.history.persist_user_message(
            session_id=session.id,
            run_id=run.id,
            content=user_prompt,
        )
        run.surface = ARTIFACT_CODING_AGENT_SURFACE
        await self.db.commit()

    async def get_session_state_for_user(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        session_id: UUID,
        reconcile_run_id: UUID | None = None,
    ) -> tuple[ArtifactCodingSession, ArtifactCodingSharedDraft, Artifact | None, AgentRun | None, ArtifactRun | None]:
        session = await self._get_session_for_user(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        run_id = reconcile_run_id or session.last_run_id
        run = await self.db.get(AgentRun, run_id) if run_id is not None else None
        if run is not None and run.tenant_id == tenant_id:
            run_status = str(getattr(run.status, "value", run.status) or "")
            if run_status in {
                RunStatus.completed.value,
                RunStatus.failed.value,
                RunStatus.cancelled.value,
            }:
                await self.reconcile_session_run(session=session, run=run)
                await self.db.refresh(session)
                run = await self.db.get(AgentRun, run.id)
        shared_draft = await self.shared_drafts.resolve_for_session(session=session)
        artifact_id = shared_draft.artifact_id or shared_draft.linked_artifact_id or session.artifact_id or session.linked_artifact_id
        artifact = None
        if artifact_id is not None:
            artifact = await self.registry.get_tenant_artifact(
                artifact_id=artifact_id,
                tenant_id=tenant_id,
            )
        last_test_run = await self.db.get(ArtifactRun, shared_draft.last_test_run_id) if shared_draft.last_test_run_id else None
        return session, shared_draft, artifact, run, last_test_run

    @staticmethod
    def serialize_runtime_state(
        *,
        session: ArtifactCodingSession,
        shared_draft: ArtifactCodingSharedDraft,
        artifact: Artifact | None,
        run: AgentRun | None,
        last_test_run: ArtifactRun | None,
    ) -> dict[str, Any]:
        snapshot = _serialize_form_state(
            shared_draft.working_draft_snapshot
            or ArtifactCodingRuntimeService._snapshot_from_artifact(artifact)
        )
        dependencies = [
            item.strip()
            for item in str(snapshot.get("python_dependencies") or "").split(",")
            if item.strip()
        ]
        kind = str(snapshot.get("kind") or "agent_node")
        capabilities = _parse_json_object(snapshot.get("capabilities"), field="capabilities", fallback=DEFAULT_CAPABILITIES)
        config_schema = _parse_json_object(snapshot.get("config_schema"), field="config_schema", fallback=DEFAULT_CONFIG_SCHEMA)
        create_payload: dict[str, Any] = {
            "slug": snapshot.get("slug") or "",
            "display_name": snapshot.get("display_name") or "",
            "description": snapshot.get("description") or "",
            "kind": kind,
            "runtime": {
                "source_files": _normalize_file_list(snapshot),
                "entry_module_path": snapshot.get("entry_module_path") or "main.py",
                "python_dependencies": dependencies,
                "runtime_target": snapshot.get("runtime_target") or "cloudflare_workers",
            },
            "capabilities": capabilities,
            "config_schema": config_schema,
        }
        if kind == "agent_node":
            create_payload["agent_contract"] = _parse_json_object(snapshot.get("agent_contract"), field="agent_contract", fallback=DEFAULT_AGENT_CONTRACT)
        elif kind == "rag_operator":
            create_payload["rag_contract"] = _parse_json_object(snapshot.get("rag_contract"), field="rag_contract", fallback=DEFAULT_RAG_CONTRACT)
        else:
            create_payload["tool_contract"] = _parse_json_object(snapshot.get("tool_contract"), field="tool_contract", fallback=DEFAULT_TOOL_CONTRACT)

        artifact_id = artifact.id if artifact is not None else (
            shared_draft.artifact_id or shared_draft.linked_artifact_id or session.artifact_id or session.linked_artifact_id
        )
        update_payload = {
            "artifact_id": str(artifact_id),
            "patch": {
                key: value
                for key, value in create_payload.items()
                if key not in {"slug", "kind"}
            },
        } if artifact_id is not None else None
        return {
            "chat_session_id": str(session.id),
            "artifact_id": str(artifact_id) if artifact_id is not None else None,
            "draft_key": session.draft_key,
            "thread_id": str(session.agent_thread_id),
            "draft_snapshot": deepcopy(snapshot),
            "last_run_id": str(run.id) if run else None,
            "last_run_status": str(getattr(run.status, "value", run.status)) if run else None,
            "last_test_run_id": str(last_test_run.id) if last_test_run else None,
            "last_test_result": {
                "status": str(getattr(last_test_run.status, "value", last_test_run.status)),
                "result_payload": deepcopy(last_test_run.result_payload or {}),
                "error_payload": deepcopy(last_test_run.error_payload or {}),
                "runtime_metadata": deepcopy(last_test_run.runtime_metadata or {}),
            } if last_test_run else None,
            "artifact_create_payload": create_payload if artifact_id is None else None,
            "artifact_update_payload": update_payload,
        }
