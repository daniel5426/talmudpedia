from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.agent_threads import AgentThread
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.artifact_runtime import ArtifactCodingSession, ArtifactRun
from app.services.artifact_coding_agent_profile import (
    ARTIFACT_CODING_AGENT_PROFILE_SLUG,
    ensure_artifact_coding_agent_profile,
)
from app.services.artifact_coding_agent_tools import ARTIFACT_CODING_AGENT_SURFACE
from app.services.artifact_coding_runtime_service import ArtifactCodingRuntimeService


TERMINAL_RUN_STATUSES = {
    RunStatus.completed.value,
    RunStatus.failed.value,
    RunStatus.cancelled.value,
}

ARTIFACT_SHARED_DRAFT_BINDING = "artifact_shared_draft"


@dataclass(frozen=True)
class WorkerBindingRef:
    binding_type: str
    binding_id: str

    def as_dict(self) -> dict[str, str]:
        return {
            "binding_type": self.binding_type,
            "binding_id": self.binding_id,
        }


class WorkerBindingAdapter(Protocol):
    binding_type: str

    async def prepare(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        binding_payload: dict[str, Any],
        replace_snapshot: bool,
    ) -> dict[str, Any]:
        ...

    async def get_state(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        binding_ref: WorkerBindingRef,
        reconcile_run_id: UUID | None,
    ) -> dict[str, Any]:
        ...

    async def build_spawn_payload(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        binding_ref: WorkerBindingRef,
    ) -> dict[str, Any]:
        ...

    async def register_spawned_run(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        binding_ref: WorkerBindingRef,
        run_id: UUID,
        user_prompt: str,
    ) -> dict[str, Any]:
        ...


def parse_binding_ref(raw: Any) -> WorkerBindingRef:
    if not isinstance(raw, dict):
        raise ValueError("binding_ref is required")
    binding_type = str(raw.get("binding_type") or "").strip()
    binding_id = str(raw.get("binding_id") or "").strip()
    if not binding_type:
        raise ValueError("binding_ref.binding_type is required")
    if not binding_id:
        raise ValueError("binding_ref.binding_id is required")
    return WorkerBindingRef(binding_type=binding_type, binding_id=binding_id)


class ArtifactSharedDraftBindingAdapter:
    binding_type = ARTIFACT_SHARED_DRAFT_BINDING

    def __init__(self, db: AsyncSession):
        self.db = db
        self.runtime = ArtifactCodingRuntimeService(db)

    async def _resolve_binding_session(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        binding_id: str,
    ) -> ArtifactCodingSession:
        try:
            session_id = UUID(str(binding_id))
        except Exception as exc:
            raise ValueError("Invalid binding_ref.binding_id") from exc
        session = await self.runtime.history.get_session_for_user(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        if session is None:
            raise ValueError("Artifact shared draft binding not found")
        return session

    async def _latest_session_for_scope(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        artifact_id: UUID | None,
        draft_key: str | None,
    ) -> ArtifactCodingSession | None:
        stmt = (
            select(ArtifactCodingSession)
            .join(AgentThread, ArtifactCodingSession.agent_thread_id == AgentThread.id)
            .where(
                and_(
                    ArtifactCodingSession.tenant_id == tenant_id,
                    AgentThread.user_id == user_id,
                )
            )
            .order_by(ArtifactCodingSession.last_message_at.desc(), ArtifactCodingSession.created_at.desc())
        )
        if artifact_id is not None:
            stmt = stmt.where(
                (ArtifactCodingSession.artifact_id == artifact_id)
                | (ArtifactCodingSession.linked_artifact_id == artifact_id)
            )
        elif draft_key:
            stmt = stmt.where(ArtifactCodingSession.draft_key == draft_key)
        else:
            return None
        result = await self.db.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    async def prepare(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        binding_payload: dict[str, Any],
        replace_snapshot: bool,
    ) -> dict[str, Any]:
        explicit_binding_id = str(binding_payload.get("binding_id") or "").strip() or None
        artifact_id_raw = binding_payload.get("artifact_id")
        draft_key = str(binding_payload.get("draft_key") or "").strip() or None
        title_prompt = str(
            binding_payload.get("title_prompt")
            or "Platform Architect artifact work binding"
        ).strip()
        draft_snapshot = binding_payload.get("draft_snapshot") if isinstance(binding_payload.get("draft_snapshot"), dict) else None
        artifact_id = UUID(str(artifact_id_raw)) if artifact_id_raw else None

        artifact_agent = await ensure_artifact_coding_agent_profile(self.db, tenant_id, actor_user_id=user_id)

        session_id: UUID | None = None
        if explicit_binding_id:
            session = await self._resolve_binding_session(
                tenant_id=tenant_id,
                user_id=user_id,
                binding_id=explicit_binding_id,
            )
            session_id = session.id
        else:
            latest = await self._latest_session_for_scope(
                tenant_id=tenant_id,
                user_id=user_id,
                artifact_id=artifact_id,
                draft_key=draft_key,
            )
            session_id = latest.id if latest is not None else None

        prepared = await self.runtime.prepare_session(
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=artifact_agent.id,
            title_prompt=title_prompt,
            artifact_id=artifact_id,
            draft_key=draft_key,
            chat_session_id=session_id,
            draft_snapshot=draft_snapshot,
            replace_snapshot=replace_snapshot,
        )
        active_run = await self.db.get(AgentRun, prepared.session.active_run_id) if prepared.session.active_run_id else None
        last_run = await self.db.get(AgentRun, prepared.session.last_run_id) if prepared.session.last_run_id else None
        artifact = None
        artifact_id_for_load = (
            prepared.shared_draft.artifact_id
            or prepared.shared_draft.linked_artifact_id
            or prepared.session.artifact_id
            or prepared.session.linked_artifact_id
        )
        if artifact_id_for_load is not None:
            artifact = await self.runtime.registry.get_tenant_artifact(
                artifact_id=artifact_id_for_load,
                tenant_id=tenant_id,
            )
        last_test_run = await self.db.get(ArtifactRun, prepared.shared_draft.last_test_run_id) if prepared.shared_draft.last_test_run_id else None
        runtime_state = self.runtime.serialize_runtime_state(
            session=prepared.session,
            shared_draft=prepared.shared_draft,
            artifact=artifact,
            run=last_run,
            last_test_run=last_test_run,
        )
        return {
            "binding_ref": WorkerBindingRef(self.binding_type, str(prepared.session.id)).as_dict(),
            "binding_type": self.binding_type,
            "worker_agent_slug": ARTIFACT_CODING_AGENT_PROFILE_SLUG,
            "binding_state": runtime_state,
            "active_run_id": str(active_run.id) if active_run else None,
            "active_run_status": str(getattr(active_run.status, "value", active_run.status)) if active_run else None,
            "has_active_run": bool(
                active_run
                and str(getattr(active_run.status, "value", active_run.status)) not in TERMINAL_RUN_STATUSES
            ),
        }

    async def get_state(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        binding_ref: WorkerBindingRef,
        reconcile_run_id: UUID | None,
    ) -> dict[str, Any]:
        session = await self._resolve_binding_session(
            tenant_id=tenant_id,
            user_id=user_id,
            binding_id=binding_ref.binding_id,
        )
        session, shared_draft, artifact, run, last_test_run = await self.runtime.get_session_state_for_user(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session.id,
            reconcile_run_id=reconcile_run_id,
        )
        active_run = await self.db.get(AgentRun, session.active_run_id) if session.active_run_id else None
        runtime_state = self.runtime.serialize_runtime_state(
            session=session,
            shared_draft=shared_draft,
            artifact=artifact,
            run=run,
            last_test_run=last_test_run,
        )
        return {
            "binding_ref": binding_ref.as_dict(),
            "binding_type": self.binding_type,
            "worker_agent_slug": ARTIFACT_CODING_AGENT_PROFILE_SLUG,
            "binding_state": runtime_state,
            "active_run_id": str(active_run.id) if active_run else None,
            "active_run_status": str(getattr(active_run.status, "value", active_run.status)) if active_run else None,
            "has_active_run": bool(
                active_run
                and str(getattr(active_run.status, "value", active_run.status)) not in TERMINAL_RUN_STATUSES
            ),
        }

    async def build_spawn_payload(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        binding_ref: WorkerBindingRef,
    ) -> dict[str, Any]:
        session = await self._resolve_binding_session(
            tenant_id=tenant_id,
            user_id=user_id,
            binding_id=binding_ref.binding_id,
        )
        shared_draft = await self.runtime.shared_drafts.resolve_for_session(session=session)
        last_run = await self.db.get(AgentRun, shared_draft.last_run_id) if shared_draft.last_run_id else None
        if last_run is not None:
            last_status = str(getattr(last_run.status, "value", last_run.status))
            if last_status not in TERMINAL_RUN_STATUSES:
                raise RuntimeError("BINDING_RUN_ACTIVE")
        return {
            "worker_agent_slug": ARTIFACT_CODING_AGENT_PROFILE_SLUG,
            "context": {
                "surface": ARTIFACT_CODING_AGENT_SURFACE,
                "artifact_coding_session_id": str(session.id),
                "artifact_id": str(session.artifact_id or session.linked_artifact_id) if (session.artifact_id or session.linked_artifact_id) else None,
                "draft_key": session.draft_key,
                "architect_worker_binding_ref": binding_ref.as_dict(),
            },
        }

    async def register_spawned_run(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        binding_ref: WorkerBindingRef,
        run_id: UUID,
        user_prompt: str,
    ) -> dict[str, Any]:
        session = await self._resolve_binding_session(
            tenant_id=tenant_id,
            user_id=user_id,
            binding_id=binding_ref.binding_id,
        )
        shared_draft = await self.runtime.shared_drafts.resolve_for_session(session=session)
        run = await self.db.get(AgentRun, run_id)
        if run is None or run.tenant_id != tenant_id:
            raise ValueError("Spawned run not found")
        await self.runtime.register_spawned_run(
            session=session,
            shared_draft=shared_draft,
            run=run,
            user_prompt=user_prompt,
        )
        return {
            "binding_ref": binding_ref.as_dict(),
            "binding_type": self.binding_type,
            "worker_agent_slug": ARTIFACT_CODING_AGENT_PROFILE_SLUG,
            "run_id": str(run.id),
            "status": str(getattr(run.status, "value", run.status)),
        }


class PlatformArchitectWorkerBindingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._adapters: dict[str, WorkerBindingAdapter] = {
            ARTIFACT_SHARED_DRAFT_BINDING: ArtifactSharedDraftBindingAdapter(db),
        }

    def adapter_for_type(self, binding_type: str) -> WorkerBindingAdapter:
        adapter = self._adapters.get(str(binding_type or "").strip())
        if adapter is None:
            raise ValueError(f"Unsupported binding_type '{binding_type}'")
        return adapter

    def adapter_for_ref(self, binding_ref: WorkerBindingRef) -> WorkerBindingAdapter:
        return self.adapter_for_type(binding_ref.binding_type)
