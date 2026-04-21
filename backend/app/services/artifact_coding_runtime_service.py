from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionMode
from app.db.postgres.models.agent_threads import AgentThreadSurface, AgentThreadTurnStatus
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
    _default_entry_module_for_language,
    _initial_snapshot_for_kind,
    _normalize_language,
    _normalize_kind,
    _normalize_path,
    _normalize_file_list,
    _parse_json_object,
    _serialize_form_state,
)
from app.services.artifact_coding_chat_history_service import ArtifactCodingChatHistoryService
from app.services.artifact_coding_shared_draft_service import ArtifactCodingSharedDraftService
from app.services.artifact_runtime.execution_service import ArtifactExecutionService
from app.services.artifact_runtime.registry_service import ArtifactRegistryService
from app.services.thread_service import ThreadService

ARTIFACT_CODING_SCOPE_LOCKED = "locked"


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

    @staticmethod
    def _session_id_for_run(run: AgentRun) -> UUID | None:
        input_context = run.input_params.get("context") if isinstance(run.input_params, dict) else {}
        if not isinstance(input_context, dict):
            return None
        raw = input_context.get("artifact_coding_session_id")
        try:
            return UUID(str(raw)) if raw else None
        except Exception:
            return None

    @staticmethod
    def _run_input_text(run: AgentRun) -> str | None:
        input_params = run.input_params if isinstance(run.input_params, dict) else {}
        raw = input_params.get("input_display_text") or input_params.get("input")
        text = str(raw or "").strip()
        return text or None

    @staticmethod
    def _apply_partial_assistant_text(run: AgentRun, partial_assistant_text: str | None) -> None:
        partial_text = str(partial_assistant_text or "").strip()
        if not partial_text:
            return
        output_result = dict(run.output_result or {}) if isinstance(run.output_result, dict) else {}
        messages = output_result.get("messages")
        if not isinstance(messages, list):
            messages = []
        messages.append({"role": "assistant", "content": partial_text})
        output_result["messages"] = messages
        output_result["final_output"] = partial_text
        run.output_result = output_result

    async def _ensure_thread_turn_started(
        self,
        *,
        run: AgentRun,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if run.thread_id is None:
            return
        await ThreadService(self.db).start_turn(
            thread_id=run.thread_id,
            run_id=run.id,
            user_input_text=self._run_input_text(run),
            metadata=metadata,
        )

    @staticmethod
    def build_initial_snapshot_from_seed(draft_seed: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(draft_seed, dict):
            raise ValueError("draft_seed is required")
        kind = str(draft_seed.get("kind") or "").strip()
        if not kind:
            raise ValueError("draft_seed.kind is required")
        language = _normalize_language(draft_seed.get("language"))
        snapshot = _initial_snapshot_for_kind(_normalize_kind(kind), language=language)
        for field_name in ("display_name", "description"):
            value = draft_seed.get(field_name)
            if isinstance(value, str):
                snapshot[field_name] = value.strip()
        entry_module_path = draft_seed.get("entry_module_path")
        if isinstance(entry_module_path, str) and entry_module_path.strip():
            normalized_path = _normalize_path(entry_module_path)
            snapshot["entry_module_path"] = normalized_path
            files = list(snapshot.get("source_files") or [])
            if files and isinstance(files[0], dict):
                files[0] = {"path": normalized_path, "content": str(files[0].get("content") or "")}
                snapshot["source_files"] = files
        runtime_target = draft_seed.get("runtime_target")
        if isinstance(runtime_target, str) and runtime_target.strip():
            snapshot["runtime_target"] = runtime_target.strip()
        return _serialize_form_state(snapshot)

    async def _get_session_for_user(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        user_id: UUID,
        session_id: UUID,
    ) -> ArtifactCodingSession:
        session = await self.history.get_session_for_user(
            organization_id=organization_id,
            project_id=project_id,
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
                "display_name": artifact.display_name,
                "description": artifact.description or "",
                "kind": kind,
                "language": getattr(revision.language, "value", revision.language) or "python",
                "source_files": list(revision.source_files or []),
                "entry_module_path": revision.entry_module_path,
                "dependencies": ", ".join(list(revision.python_dependencies or [])),
                "runtime_target": revision.runtime_target,
                "capabilities": deepcopy(revision.capabilities or DEFAULT_CAPABILITIES),
                "config_schema": deepcopy(revision.config_schema or DEFAULT_CONFIG_SCHEMA),
                "agent_contract": deepcopy(revision.agent_contract or DEFAULT_AGENT_CONTRACT),
                "rag_contract": deepcopy(revision.rag_contract or DEFAULT_RAG_CONTRACT),
                "tool_contract": deepcopy(revision.tool_contract or DEFAULT_TOOL_CONTRACT),
            }
        )

    @staticmethod
    def _scope_artifact_id(
        *,
        session: ArtifactCodingSession,
        shared_draft: ArtifactCodingSharedDraft,
    ) -> UUID | None:
        return (
            shared_draft.artifact_id
            or shared_draft.linked_artifact_id
            or session.artifact_id
            or session.linked_artifact_id
        )

    @staticmethod
    def _scope_draft_key(
        *,
        session: ArtifactCodingSession,
        shared_draft: ArtifactCodingSharedDraft,
    ) -> str | None:
        return str(shared_draft.draft_key or session.draft_key or "").strip() or None

    @classmethod
    def _assert_compatible_existing_session_scope(
        cls,
        *,
        session: ArtifactCodingSession,
        shared_draft: ArtifactCodingSharedDraft,
        artifact_id: UUID | None,
        draft_key: str | None,
    ) -> None:
        existing_artifact_id = cls._scope_artifact_id(session=session, shared_draft=shared_draft)
        existing_draft_key = cls._scope_draft_key(session=session, shared_draft=shared_draft)
        if artifact_id is not None and existing_artifact_id is not None and artifact_id != existing_artifact_id:
            raise ValueError("Artifact coding chat session is already bound to a different artifact")
        if draft_key and existing_draft_key and draft_key != existing_draft_key:
            raise ValueError("Artifact coding chat session is already bound to a different draft")

    async def _resolve_initial_snapshot(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        artifact_id: UUID | None,
        draft_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if isinstance(draft_snapshot, dict) and draft_snapshot:
            return _serialize_form_state(draft_snapshot)
        if artifact_id is not None:
            artifact = await self.registry.get_organization_artifact(
                artifact_id=artifact_id,
                organization_id=organization_id,
                project_id=project_id,
            )
            return self._snapshot_from_artifact(artifact)
        return _initial_snapshot_for_kind("agent_node")

    async def prepare_session(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None = None,
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
            organization_id=organization_id,
            project_id=project_id,
            artifact_id=artifact_id,
            draft_snapshot=draft_snapshot,
        )
        if chat_session_id is not None:
            session = await self._get_session_for_user(
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                session_id=chat_session_id,
            )
            shared_draft = await self.shared_drafts.resolve_for_session(session=session)
            self._assert_compatible_existing_session_scope(
                session=session,
                shared_draft=shared_draft,
                artifact_id=artifact_id,
                draft_key=draft_key,
            )
            if session.shared_draft_id != shared_draft.id:
                session.shared_draft_id = shared_draft.id
                await self.db.flush()
        else:
            thread = (
                await ThreadService(self.db).resolve_or_create_thread(
                    organization_id=organization_id,
                    project_id=project_id,
                    user_id=user_id,
                    app_account_id=None,
                    agent_id=agent_id,
                    published_app_id=None,
                    surface=AgentThreadSurface.artifact_admin,
                    thread_id=None,
                    input_text=title_prompt,
                )
            ).thread
            shared_draft = await self.shared_drafts.get_or_create_for_scope(
                organization_id=organization_id,
                project_id=project_id,
                artifact_id=artifact_id,
                draft_key=draft_key,
                initial_snapshot=initial_snapshot,
            )
            session = await self.history.create_session(
                organization_id=organization_id,
                project_id=project_id,
                artifact_id=artifact_id,
                shared_draft_id=shared_draft.id,
                draft_key=draft_key,
                agent_thread_id=thread.id,
                title_prompt=title_prompt,
            )
        session.scope_mode = ARTIFACT_CODING_SCOPE_LOCKED

        if replace_snapshot:
            await self.shared_drafts.update_snapshot(
                shared_draft=shared_draft,
                draft_snapshot=initial_snapshot,
                artifact_id=artifact_id if artifact_id is not None else self._scope_artifact_id(session=session, shared_draft=shared_draft),
                draft_key=draft_key or self._scope_draft_key(session=session, shared_draft=shared_draft),
            )
        elif artifact_id is not None or draft_key:
            await self.shared_drafts.update_snapshot(
                shared_draft=shared_draft,
                draft_snapshot=shared_draft.working_draft_snapshot or initial_snapshot,
                artifact_id=artifact_id if artifact_id is not None else self._scope_artifact_id(session=session, shared_draft=shared_draft),
                draft_key=draft_key or self._scope_draft_key(session=session, shared_draft=shared_draft),
            )

        current_artifact_id = self._scope_artifact_id(session=session, shared_draft=shared_draft)
        current_draft_key = self._scope_draft_key(session=session, shared_draft=shared_draft)
        effective_draft_key = draft_key or current_draft_key
        should_link_existing_draft_session = (
            artifact_id is not None
            and effective_draft_key is not None
            and current_artifact_id is None
            and current_draft_key == effective_draft_key
        )

        if artifact_id is not None and effective_draft_key:
            await self.shared_drafts.link_scope_to_artifact(
                organization_id=organization_id,
                project_id=project_id,
                draft_key=effective_draft_key,
                artifact_id=artifact_id,
            )
            if should_link_existing_draft_session:
                await self.history.link_sessions_to_artifact(
                    organization_id=organization_id,
                    project_id=project_id,
                    draft_key=effective_draft_key,
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
        organization_id: UUID,
        project_id: UUID | None = None,
        user_id: UUID,
        user_prompt: str,
        artifact_id: UUID | None,
        draft_key: str | None,
        chat_session_id: UUID | None,
        draft_snapshot: dict[str, Any] | None,
        model_id: str | None,
    ) -> tuple[ArtifactCodingSession, ArtifactCodingSharedDraft, AgentRun]:
        agent = await ensure_artifact_coding_agent_profile(
            self.db,
            organization_id,
            project_id=project_id,
            actor_user_id=user_id,
        )
        prepared = await self.prepare_session(
            organization_id=organization_id,
            project_id=project_id,
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

        return await self._start_session_run(
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            session=session,
            shared_draft=shared_draft,
            prompt=user_prompt,
            prompt_role="user",
            model_id=model_id,
            background=False,
        )

    async def continue_prompt_run(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None = None,
        user_id: UUID,
        chat_session_id: UUID,
        orchestrator_prompt: str,
        model_id: str | None,
    ) -> tuple[ArtifactCodingSession, ArtifactCodingSharedDraft, AgentRun]:
        session = await self._get_session_for_user(
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            session_id=chat_session_id,
        )
        shared_draft = await self.shared_drafts.resolve_for_session(session=session)
        return await self._start_session_run(
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            session=session,
            shared_draft=shared_draft,
            prompt=orchestrator_prompt,
            prompt_role="orchestrator",
            model_id=model_id,
            background=True,
        )

    async def _start_session_run(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None = None,
        user_id: UUID,
        session: ArtifactCodingSession,
        shared_draft: ArtifactCodingSharedDraft,
        prompt: str,
        prompt_role: str,
        model_id: str | None,
        background: bool,
    ) -> tuple[ArtifactCodingSession, ArtifactCodingSharedDraft, AgentRun]:
        agent = await ensure_artifact_coding_agent_profile(
            self.db,
            organization_id,
            project_id=project_id,
            actor_user_id=user_id,
        )
        prepared = await self.prepare_session_run_input(
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            session=session,
            shared_draft=shared_draft,
            prompt=prompt,
            prompt_role=prompt_role,
            model_id=model_id,
        )
        executor = AgentExecutorService(db=self.db)
        run_id = await executor.start_run(
            agent_id=agent.id,
            input_params=prepared["input_params"],
            user_id=user_id,
            background=background,
            mode=ExecutionMode.DEBUG,
            requested_scopes=[],
            thread_id=session.agent_thread_id,
        )
        run = await self.db.get(AgentRun, run_id)
        if run is None:
            raise RuntimeError("Artifact coding run was not created")
        await self.register_session_run(
            session=session,
            shared_draft=shared_draft,
            run=run,
            prompt=prompt,
            prompt_role=prompt_role,
        )
        await self.db.commit()
        await self.db.refresh(session)
        await self.db.refresh(run)
        return session, shared_draft, run

    async def prepare_session_run_input(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None = None,
        user_id: UUID,
        session: ArtifactCodingSession,
        shared_draft: ArtifactCodingSharedDraft,
        prompt: str,
        prompt_role: str,
        model_id: str | None,
        extra_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
            current_prompt=prompt,
            current_role=prompt_role,
            include_current_prompt=False,
        )
        artifact_id = (
            shared_draft.artifact_id
            or shared_draft.linked_artifact_id
            or session.artifact_id
            or session.linked_artifact_id
        )
        request_context = {
            "surface": ARTIFACT_CODING_AGENT_SURFACE,
            "artifact_coding_session_id": str(session.id),
            "artifact_coding_shared_draft_id": str(shared_draft.id),
            "artifact_id": str(artifact_id) if artifact_id else None,
            "draft_key": self._normalize_draft_key(session.draft_key),
            "requested_model_id": model_id,
            "thread_id": str(session.agent_thread_id),
            "organization_id": str(organization_id),
            "project_id": str(project_id) if project_id else None,
            "user_id": str(user_id),
            "initiator_user_id": str(user_id),
            "conversation_message_role": prompt_role,
        }
        if isinstance(extra_context, dict):
            request_context.update(extra_context)
        return {
            "thread_id": str(session.agent_thread_id),
            "input_params": {
                "messages": run_messages,
                "input": prompt,
                "thread_id": str(session.agent_thread_id),
                "context": request_context,
            },
        }

    async def register_session_run(
        self,
        *,
        session: ArtifactCodingSession,
        shared_draft: ArtifactCodingSharedDraft,
        run: AgentRun,
        prompt: str,
        prompt_role: str,
    ) -> None:
        run.surface = ARTIFACT_CODING_AGENT_SURFACE
        await self._ensure_thread_turn_started(
            run=run,
            metadata={"surface": ARTIFACT_CODING_AGENT_SURFACE},
        )
        await self.history.mark_run_started(session=session, run_id=run.id)
        await self.shared_drafts.set_last_run(shared_draft=shared_draft, run_id=run.id)
        await self.shared_drafts.create_run_snapshot(
            shared_draft=shared_draft,
            run_id=run.id,
            session_id=session.id,
        )
        if prompt_role == "orchestrator":
            await self.history.persist_orchestrator_message(
                session_id=session.id,
                run_id=run.id,
                content=prompt,
            )
        else:
            await self.history.persist_user_message(
                session_id=session.id,
                run_id=run.id,
                content=prompt,
            )

    async def cancel_run(
        self,
        *,
        run: AgentRun,
        partial_assistant_text: str | None = None,
    ) -> tuple[AgentRun, ArtifactCodingSession | None]:
        session_id = self._session_id_for_run(run)
        session = await self.db.get(ArtifactCodingSession, session_id) if session_id is not None else None
        status = str(getattr(run.status, "value", run.status) or "").strip().lower()
        turn_status = AgentThreadTurnStatus.cancelled

        if status not in {
            RunStatus.completed.value,
            RunStatus.failed.value,
            RunStatus.cancelled.value,
        }:
            run.status = RunStatus.cancelled
            run.completed_at = datetime.now(timezone.utc)
            run.error_message = None
        elif status == RunStatus.failed.value:
            turn_status = AgentThreadTurnStatus.failed
        elif status == RunStatus.completed.value:
            turn_status = AgentThreadTurnStatus.completed

        self._apply_partial_assistant_text(run, partial_assistant_text)
        await self._ensure_thread_turn_started(
            run=run,
            metadata={"surface": ARTIFACT_CODING_AGENT_SURFACE, "cancelled": True},
        )
        if run.thread_id is not None:
            assistant_text = self.history._extract_assistant_output_text(run)
            await ThreadService(self.db).complete_turn(
                run_id=run.id,
                status=turn_status,
                assistant_output_text=assistant_text,
                metadata={"cancelled": True},
            )

        if session is not None:
            await self.history.reconcile_session_run(session=session, run=run)

        await self.db.commit()
        await self.db.refresh(run)
        if session is not None:
            await self.db.refresh(session)
        return run, session

    async def reconcile_session_run(
        self,
        *,
        session: ArtifactCodingSession,
        run: AgentRun,
    ) -> None:
        run_status = str(getattr(run.status, "value", run.status) or "").strip().lower()
        if run_status in {
            RunStatus.completed.value,
            RunStatus.failed.value,
            RunStatus.cancelled.value,
        }:
            shared_draft = await self.shared_drafts.resolve_for_session(session=session)
            if shared_draft.last_test_run_id is not None:
                last_test_run = await self.db.get(ArtifactRun, shared_draft.last_test_run_id)
                if last_test_run is not None:
                    test_status = str(getattr(last_test_run.status, "value", last_test_run.status) or "").strip().lower()
                    originating_agent_run_id = str((last_test_run.context_payload or {}).get("originating_agent_run_id") or "").strip()
                    if (
                        test_status in {"queued", "running", "cancel_requested"}
                        and originating_agent_run_id == str(run.id)
                    ):
                        await ArtifactExecutionService(self.db).cancel_run(
                            run_id=last_test_run.id,
                            organization_id=session.organization_id,
                        )
        await self.history.reconcile_session_run(session=session, run=run)
        await self.db.commit()

    async def register_spawned_run(
        self,
        *,
        session: ArtifactCodingSession,
        shared_draft: ArtifactCodingSharedDraft,
        run: AgentRun,
        prompt: str,
        prompt_role: str = "user",
    ) -> None:
        await self.register_session_run(
            session=session,
            shared_draft=shared_draft,
            run=run,
            prompt=prompt,
            prompt_role=prompt_role,
        )
        await self.db.commit()

    async def get_session_state_for_user(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None = None,
        user_id: UUID,
        session_id: UUID,
        reconcile_run_id: UUID | None = None,
    ) -> tuple[ArtifactCodingSession, ArtifactCodingSharedDraft, Artifact | None, AgentRun | None, ArtifactRun | None]:
        session = await self._get_session_for_user(
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            session_id=session_id,
        )
        run_id = reconcile_run_id or session.last_run_id
        run = await self.db.get(AgentRun, run_id) if run_id is not None else None
        if run is not None and run.organization_id == organization_id:
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
            artifact = await self.registry.get_organization_artifact(
                artifact_id=artifact_id,
                organization_id=organization_id,
                project_id=project_id,
            )
        last_test_run = await self.db.get(ArtifactRun, shared_draft.last_test_run_id) if shared_draft.last_test_run_id else None
        return session, shared_draft, artifact, run, last_test_run

    @staticmethod
    def _serialize_verification_state(last_test_run: ArtifactRun | None) -> dict[str, Any]:
        if last_test_run is None:
            return {
                "has_test_run": False,
                "latest_test_run_id": None,
                "latest_test_status": None,
                "latest_test_terminal": None,
                "latest_test_successful": None,
                "result_payload": None,
                "error_payload": None,
                "runtime_metadata": None,
            }
        status = str(getattr(last_test_run.status, "value", last_test_run.status))
        return {
            "has_test_run": True,
            "latest_test_run_id": str(last_test_run.id),
            "latest_test_status": status,
            "latest_test_terminal": status in {"completed", "failed", "cancelled"},
            "latest_test_successful": status == "completed",
            "result_payload": deepcopy(last_test_run.result_payload or {}),
            "error_payload": deepcopy(last_test_run.error_payload or {}),
            "runtime_metadata": deepcopy(last_test_run.runtime_metadata or {}),
        }

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
            for item in str(snapshot.get("dependencies") or "").split(",")
            if item.strip()
        ]
        kind = str(snapshot.get("kind") or "agent_node")
        language = str(snapshot.get("language") or "python")
        capabilities = _parse_json_object(snapshot.get("capabilities"), field="capabilities", fallback=DEFAULT_CAPABILITIES)
        config_schema = _parse_json_object(snapshot.get("config_schema"), field="config_schema", fallback=DEFAULT_CONFIG_SCHEMA)
        artifact_payload: dict[str, Any] = {
            "display_name": snapshot.get("display_name") or "",
            "description": snapshot.get("description") or "",
            "kind": kind,
            "runtime": {
                "language": language,
                "source_files": _normalize_file_list(snapshot),
                "entry_module_path": snapshot.get("entry_module_path") or _default_entry_module_for_language(language),
                "dependencies": dependencies,
                "runtime_target": snapshot.get("runtime_target") or "cloudflare_workers",
            },
            "capabilities": capabilities,
            "config_schema": config_schema,
        }
        if kind == "agent_node":
            artifact_payload["agent_contract"] = _parse_json_object(snapshot.get("agent_contract"), field="agent_contract", fallback=DEFAULT_AGENT_CONTRACT)
        elif kind == "rag_operator":
            artifact_payload["rag_contract"] = _parse_json_object(snapshot.get("rag_contract"), field="rag_contract", fallback=DEFAULT_RAG_CONTRACT)
        else:
            artifact_payload["tool_contract"] = _parse_json_object(snapshot.get("tool_contract"), field="tool_contract", fallback=DEFAULT_TOOL_CONTRACT)

        artifact_id = artifact.id if artifact is not None else (
            shared_draft.artifact_id or shared_draft.linked_artifact_id or session.artifact_id or session.linked_artifact_id
        )
        missing_create_fields = [
            field_name
            for field_name, field_value in (
                ("display_name", artifact_payload.get("display_name")),
            )
            if not str(field_value or "").strip()
        ]
        persistence_mode = "update" if artifact_id is not None else "create"
        update_payload = {
            "artifact_id": str(artifact_id),
            "patch": {
                key: value
                for key, value in artifact_payload.items()
                if key != "kind"
            },
        } if artifact_id is not None else None
        platform_assets_create_input = {
            "action": "artifacts.create",
            "payload": deepcopy(artifact_payload),
        } if artifact_id is None else None
        platform_assets_update_input = {
            "action": "artifacts.update",
            "payload": deepcopy(update_payload),
        } if update_payload is not None else None
        return {
            "chat_session_id": str(session.id),
            "scope_mode": ARTIFACT_CODING_SCOPE_LOCKED,
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
            "verification_state": ArtifactCodingRuntimeService._serialize_verification_state(last_test_run),
            "persistence_readiness": {
                "ready": artifact_id is not None or not missing_create_fields,
                "mode": persistence_mode,
                "missing_fields": missing_create_fields,
            },
            "platform_assets_create_input": platform_assets_create_input,
            "platform_assets_update_input": platform_assets_update_input,
        }
