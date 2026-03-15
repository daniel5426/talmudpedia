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
    _normalize_kind,
    _normalize_path,
    _normalize_file_list,
    _parse_json_object,
    _serialize_form_state,
)
from app.services.artifact_coding_chat_history_service import ArtifactCodingChatHistoryService
from app.services.artifact_coding_shared_draft_service import ArtifactCodingSharedDraftService
from app.services.artifact_runtime.registry_service import ArtifactRegistryService
from app.services.artifact_runtime.revision_service import ArtifactRevisionService
from app.services.thread_service import ThreadService

ARTIFACT_CODING_SCOPE_LOCKED = "locked"
ARTIFACT_CODING_SCOPE_STANDALONE = "standalone"
ARTIFACT_CODING_SCOPE_MODES = {
    ARTIFACT_CODING_SCOPE_LOCKED,
    ARTIFACT_CODING_SCOPE_STANDALONE,
}


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
    def normalize_scope_mode(value: str | None) -> str:
        normalized = str(value or ARTIFACT_CODING_SCOPE_LOCKED).strip().lower()
        if normalized not in ARTIFACT_CODING_SCOPE_MODES:
            raise ValueError("Unsupported artifact coding scope mode")
        return normalized

    @staticmethod
    def build_initial_snapshot_from_seed(draft_seed: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(draft_seed, dict):
            raise ValueError("draft_seed is required")
        kind = str(draft_seed.get("kind") or "").strip()
        if not kind:
            raise ValueError("draft_seed.kind is required")
        snapshot = _initial_snapshot_for_kind(_normalize_kind(kind))
        for field_name in ("slug", "display_name", "description"):
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
        scope_mode: str = ARTIFACT_CODING_SCOPE_LOCKED,
    ) -> PreparedArtifactCodingSession:
        scope_mode = self.normalize_scope_mode(scope_mode)
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
                shared_draft_id=shared_draft.id,
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
            shared_draft = await self.shared_drafts.get_or_create_for_scope(
                tenant_id=tenant_id,
                artifact_id=artifact_id,
                draft_key=draft_key,
                initial_snapshot=initial_snapshot,
            )
            session = await self.history.create_session(
                tenant_id=tenant_id,
                artifact_id=artifact_id,
                shared_draft_id=shared_draft.id,
                draft_key=draft_key,
                agent_thread_id=thread.id,
                title_prompt=title_prompt,
                scope_mode=scope_mode,
            )
        session.scope_mode = scope_mode

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
        scope_mode: str = ARTIFACT_CODING_SCOPE_LOCKED,
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
            scope_mode=scope_mode,
        )
        session = prepared.session
        shared_draft = prepared.shared_draft

        return await self._start_session_run(
            tenant_id=tenant_id,
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
        tenant_id: UUID,
        user_id: UUID,
        chat_session_id: UUID,
        orchestrator_prompt: str,
        model_id: str | None,
    ) -> tuple[ArtifactCodingSession, ArtifactCodingSharedDraft, AgentRun]:
        session = await self._get_session_for_user(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=chat_session_id,
        )
        shared_draft = await self.shared_drafts.resolve_for_session(session=session)
        return await self._start_session_run(
            tenant_id=tenant_id,
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
        tenant_id: UUID,
        user_id: UUID,
        session: ArtifactCodingSession,
        shared_draft: ArtifactCodingSharedDraft,
        prompt: str,
        prompt_role: str,
        model_id: str | None,
        background: bool,
    ) -> tuple[ArtifactCodingSession, ArtifactCodingSharedDraft, AgentRun]:
        agent = await ensure_artifact_coding_agent_profile(self.db, tenant_id, actor_user_id=user_id)
        prepared = await self.prepare_session_run_input(
            tenant_id=tenant_id,
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
        tenant_id: UUID,
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
            "artifact_coding_scope_mode": self.normalize_scope_mode(getattr(session, "scope_mode", None)),
            "artifact_id": str(artifact_id) if artifact_id else None,
            "draft_key": self._normalize_draft_key(session.draft_key),
            "requested_model_id": model_id,
            "thread_id": str(session.agent_thread_id),
            "tenant_id": str(tenant_id),
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

    async def search_accessible_artifacts(
        self,
        *,
        tenant_id: UUID,
        query: str | None,
        limit: int = 10,
    ) -> list[Artifact]:
        normalized_query = str(query or "").strip().lower()
        artifacts = await self.registry.list_accessible_artifacts(tenant_id=tenant_id)
        if not normalized_query:
            return artifacts[: max(1, limit)]

        def _score(item: Artifact) -> tuple[int, str]:
            slug = str(item.slug or "").lower()
            display_name = str(item.display_name or "").lower()
            if slug == normalized_query or display_name == normalized_query:
                return (0, slug)
            if slug.startswith(normalized_query) or display_name.startswith(normalized_query):
                return (1, slug)
            if normalized_query in slug or normalized_query in display_name:
                return (2, slug)
            return (3, slug)

        filtered = [
            artifact
            for artifact in artifacts
            if normalized_query in str(artifact.slug or "").lower()
            or normalized_query in str(artifact.display_name or "").lower()
            or normalized_query in str(artifact.description or "").lower()
        ]
        filtered.sort(key=_score)
        return filtered[: max(1, limit)]

    async def list_recent_accessible_artifacts(
        self,
        *,
        tenant_id: UUID,
        limit: int = 10,
    ) -> list[Artifact]:
        artifacts = await self.registry.list_accessible_artifacts(tenant_id=tenant_id)
        return artifacts[: max(1, limit)]

    async def open_artifact_for_session(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        session_id: UUID,
        artifact_id: UUID,
    ) -> tuple[ArtifactCodingSession, ArtifactCodingSharedDraft, Artifact]:
        session = await self._get_session_for_user(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        if self.normalize_scope_mode(getattr(session, "scope_mode", None)) != ARTIFACT_CODING_SCOPE_STANDALONE:
            raise RuntimeError("ARTIFACT_CODING_SCOPE_LOCKED")
        artifact = await self.registry.get_accessible_artifact(artifact_id=artifact_id, tenant_id=tenant_id)
        if artifact is None:
            raise ValueError("Artifact not found")
        snapshot = self._snapshot_from_artifact(artifact)
        shared_draft = await self.shared_drafts.resolve_for_session(session=session)
        session.artifact_id = artifact.id
        session.linked_artifact_id = artifact.id
        session.linked_at = datetime.now(timezone.utc)
        session.draft_key = None
        await self.history.update_session_scope(
            session=session,
            artifact_id=artifact.id,
            draft_key=None,
            shared_draft_id=shared_draft.id,
        )
        shared_draft.artifact_id = artifact.id
        shared_draft.linked_artifact_id = artifact.id
        shared_draft.linked_at = datetime.now(timezone.utc)
        shared_draft.draft_key = None
        await self.shared_drafts.update_snapshot(
            shared_draft=shared_draft,
            draft_snapshot=snapshot,
            artifact_id=artifact.id,
            draft_key=None,
        )
        await self.db.commit()
        await self.db.refresh(session)
        await self.db.refresh(shared_draft)
        return session, shared_draft, artifact

    async def start_new_draft_for_session(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        session_id: UUID,
        draft_seed: dict[str, Any],
    ) -> tuple[ArtifactCodingSession, ArtifactCodingSharedDraft]:
        session = await self._get_session_for_user(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        if self.normalize_scope_mode(getattr(session, "scope_mode", None)) != ARTIFACT_CODING_SCOPE_STANDALONE:
            raise RuntimeError("ARTIFACT_CODING_SCOPE_LOCKED")
        snapshot = self.build_initial_snapshot_from_seed(draft_seed)
        shared_draft = await self.shared_drafts.resolve_for_session(session=session)
        session.artifact_id = None
        session.linked_artifact_id = None
        session.linked_at = None
        session.draft_key = None
        await self.history.update_session_scope(
            session=session,
            artifact_id=None,
            draft_key=None,
            shared_draft_id=shared_draft.id,
        )
        shared_draft.artifact_id = None
        shared_draft.linked_artifact_id = None
        shared_draft.linked_at = None
        shared_draft.draft_key = None
        await self.shared_drafts.update_snapshot(
            shared_draft=shared_draft,
            draft_snapshot=snapshot,
            artifact_id=None,
            draft_key=None,
        )
        await self.shared_drafts.set_last_test_run(shared_draft=shared_draft, test_run_id=None)
        await self.db.commit()
        await self.db.refresh(session)
        await self.db.refresh(shared_draft)
        return session, shared_draft

    async def persist_session_artifact(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        session_id: UUID,
        mode: str,
    ) -> dict[str, Any]:
        normalized_mode = str(mode or "auto").strip().lower() or "auto"
        if normalized_mode not in {"auto", "create", "update"}:
            raise ValueError("mode must be one of auto, create, update")
        session, shared_draft, artifact, run, last_test_run = await self.get_session_state_for_user(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        runtime_state = self.serialize_runtime_state(
            session=session,
            shared_draft=shared_draft,
            artifact=artifact,
            run=run,
            last_test_run=last_test_run,
        )
        existing_artifact_id = (
            shared_draft.artifact_id
            or shared_draft.linked_artifact_id
            or session.artifact_id
            or session.linked_artifact_id
        )
        persistence_mode = "update" if existing_artifact_id is not None else "create"
        if normalized_mode == "create" and existing_artifact_id is not None:
            raise ValueError("Session already links to an artifact; create is not allowed")
        if normalized_mode == "update" and existing_artifact_id is None:
            raise ValueError("Session is not linked to an artifact; update is not allowed")
        if normalized_mode != "auto":
            persistence_mode = normalized_mode
        if session.active_run_id is not None:
            active_run = await self.db.get(AgentRun, session.active_run_id)
            if active_run is not None and str(getattr(active_run.status, "value", active_run.status)) not in {
                RunStatus.completed.value,
                RunStatus.failed.value,
                RunStatus.cancelled.value,
            }:
                raise RuntimeError("CODING_AGENT_RUN_ACTIVE")
        readiness = runtime_state.get("persistence_readiness") if isinstance(runtime_state, dict) else None
        if persistence_mode == "create" and isinstance(readiness, dict) and not bool(readiness.get("ready")):
            missing_fields = [str(item).strip() for item in (readiness.get("missing_fields") or []) if str(item).strip()]
            raise ValueError(
                "ARTIFACT_PERSISTENCE_NOT_READY: missing required create fields: "
                + ", ".join(missing_fields)
            )
        revision_service = ArtifactRevisionService(self.db)
        if persistence_mode == "create":
            create_input = runtime_state.get("platform_assets_create_input")
            if not isinstance(create_input, dict):
                raise ValueError("Session state is missing canonical create input")
            artifact_payload = create_input.get("payload")
            if not isinstance(artifact_payload, dict):
                raise ValueError("Session create payload is invalid")
            runtime_payload = artifact_payload.get("runtime")
            if not isinstance(runtime_payload, dict):
                raise ValueError("Session create runtime payload is invalid")
            artifact = await revision_service.create_artifact(
                tenant_id=tenant_id,
                created_by=user_id,
                slug=str(artifact_payload.get("slug") or "").strip(),
                display_name=str(artifact_payload.get("display_name") or "").strip(),
                description=artifact_payload.get("description"),
                kind=str(artifact_payload.get("kind") or "").strip(),
                source_files=list(runtime_payload.get("source_files") or []),
                entry_module_path=runtime_payload.get("entry_module_path"),
                python_dependencies=list(runtime_payload.get("python_dependencies") or []),
                runtime_target=str(runtime_payload.get("runtime_target") or "cloudflare_workers"),
                capabilities=dict(artifact_payload.get("capabilities") or {}),
                config_schema=dict(artifact_payload.get("config_schema") or {}),
                agent_contract=artifact_payload.get("agent_contract"),
                rag_contract=artifact_payload.get("rag_contract"),
                tool_contract=artifact_payload.get("tool_contract"),
            )
            session.artifact_id = artifact.id
            session.linked_artifact_id = artifact.id
            session.linked_at = datetime.now(timezone.utc)
            shared_draft.artifact_id = artifact.id
            shared_draft.linked_artifact_id = artifact.id
            shared_draft.linked_at = datetime.now(timezone.utc)
        else:
            update_input = runtime_state.get("platform_assets_update_input")
            if not isinstance(update_input, dict):
                raise ValueError("Session state is missing canonical update input")
            update_payload = update_input.get("payload")
            if not isinstance(update_payload, dict):
                raise ValueError("Session update payload is invalid")
            patch = update_payload.get("patch")
            if not isinstance(patch, dict):
                raise ValueError("Session update patch is invalid")
            target_artifact = artifact
            if target_artifact is None and existing_artifact_id is not None:
                target_artifact = await self.registry.get_tenant_artifact(
                    artifact_id=existing_artifact_id,
                    tenant_id=tenant_id,
                )
            if target_artifact is None:
                raise ValueError("Linked artifact not found for update")
            artifact = target_artifact
            runtime_payload = patch.get("runtime")
            if not isinstance(runtime_payload, dict):
                raise ValueError("Session update runtime payload is invalid")
            await revision_service.update_artifact(
                artifact,
                updated_by=user_id,
                display_name=str(patch.get("display_name") or "").strip(),
                description=patch.get("description"),
                source_files=list(runtime_payload.get("source_files") or []),
                entry_module_path=runtime_payload.get("entry_module_path"),
                python_dependencies=list(runtime_payload.get("python_dependencies") or []),
                runtime_target=str(runtime_payload.get("runtime_target") or "cloudflare_workers"),
                capabilities=dict(patch.get("capabilities") or {}),
                config_schema=dict(patch.get("config_schema") or {}),
                agent_contract=patch.get("agent_contract"),
                rag_contract=patch.get("rag_contract"),
                tool_contract=patch.get("tool_contract"),
            )
        await self.db.commit()
        await self.db.refresh(session)
        await self.db.refresh(shared_draft)
        session, shared_draft, artifact, run, last_test_run = await self.get_session_state_for_user(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session.id,
        )
        refreshed_state = self.serialize_runtime_state(
            session=session,
            shared_draft=shared_draft,
            artifact=artifact,
            run=run,
            last_test_run=last_test_run,
        )
        return {
            "artifact_id": str(artifact.id) if artifact is not None else None,
            "artifact_slug": str(getattr(artifact, "slug", "") or "") or None,
            "artifact_kind": str(getattr(artifact.kind, "value", artifact.kind)) if artifact is not None else None,
            "persistence_mode": persistence_mode,
            "session_state": refreshed_state,
            "verification_state": refreshed_state.get("verification_state"),
        }

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
            for item in str(snapshot.get("python_dependencies") or "").split(",")
            if item.strip()
        ]
        kind = str(snapshot.get("kind") or "agent_node")
        capabilities = _parse_json_object(snapshot.get("capabilities"), field="capabilities", fallback=DEFAULT_CAPABILITIES)
        config_schema = _parse_json_object(snapshot.get("config_schema"), field="config_schema", fallback=DEFAULT_CONFIG_SCHEMA)
        artifact_payload: dict[str, Any] = {
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
                ("slug", artifact_payload.get("slug")),
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
                if key not in {"slug", "kind"}
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
            "scope_mode": ArtifactCodingRuntimeService.normalize_scope_mode(getattr(session, "scope_mode", None)),
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
