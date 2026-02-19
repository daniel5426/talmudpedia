from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from hashlib import sha256
from typing import Any, AsyncGenerator
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionMode
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.db.postgres.models.registry import ModelCapabilityType, ModelProviderType, ModelRegistry
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppCodingRunSandboxStatus,
    PublishedAppDraftDevSessionStatus,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
)
from app.services.published_app_coding_agent_profile import ensure_coding_agent_profile, resolve_coding_agent_chat_model_id
from app.services.published_app_coding_run_sandbox_service import PublishedAppCodingRunSandboxService
from app.services.published_app_coding_agent_engines.base import EngineRunContext, PublishedAppCodingAgentEngine
from app.services.published_app_coding_agent_engines.native_engine import NativePublishedAppCodingAgentEngine
from app.services.published_app_coding_agent_engines.opencode_engine import OpenCodePublishedAppCodingAgentEngine
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeDisabled, PublishedAppDraftDevRuntimeService
from app.services.opencode_server_client import OpenCodeServerClient
from app.api.routers.published_apps_admin_files import _filter_builder_snapshot_files, _validate_builder_project_or_raise

logger = logging.getLogger(__name__)

CODING_AGENT_ENGINE_NATIVE = "native"
CODING_AGENT_ENGINE_OPENCODE = "opencode"


class PublishedAppCodingAgentRuntimeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.executor = AgentExecutorService(db=db)
        self._opencode_client = OpenCodeServerClient.from_env()
        self._run_sandbox_service = PublishedAppCodingRunSandboxService(db)
        self._native_engine = NativePublishedAppCodingAgentEngine(executor=self.executor)
        self._opencode_engine = OpenCodePublishedAppCodingAgentEngine(
            db=self.db,
            client=self._opencode_client,
        )

    @staticmethod
    def serialize_run(run: AgentRun) -> dict[str, Any]:
        execution_engine = str(run.execution_engine or CODING_AGENT_ENGINE_NATIVE).strip().lower() or CODING_AGENT_ENGINE_NATIVE
        input_params = run.input_params if isinstance(run.input_params, dict) else {}
        context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
        return {
            "run_id": str(run.id),
            "status": run.status.value if hasattr(run.status, "value") else str(run.status),
            "execution_engine": execution_engine,
            "surface": run.surface,
            "published_app_id": str(run.published_app_id) if run.published_app_id else None,
            "base_revision_id": str(run.base_revision_id) if run.base_revision_id else None,
            "result_revision_id": str(run.result_revision_id) if run.result_revision_id else None,
            "checkpoint_revision_id": str(run.checkpoint_revision_id) if run.checkpoint_revision_id else None,
            "requested_model_id": str(run.requested_model_id) if run.requested_model_id else None,
            "resolved_model_id": str(run.resolved_model_id) if run.resolved_model_id else None,
            "error": run.error_message,
            "created_at": run.created_at,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "sandbox_id": str(context.get("coding_run_sandbox_id") or "") or None,
            "sandbox_status": str(context.get("coding_run_sandbox_status") or "") or None,
            "sandbox_started_at": context.get("coding_run_sandbox_started_at"),
        }

    @staticmethod
    def _model_unavailable_error(message: str) -> HTTPException:
        return HTTPException(
            status_code=400,
            detail={
                "code": "CODING_AGENT_MODEL_UNAVAILABLE",
                "field": "model_id",
                "message": message,
            },
        )

    @staticmethod
    def _engine_unavailable_error(message: str) -> HTTPException:
        return HTTPException(
            status_code=400,
            detail={
                "code": "CODING_AGENT_ENGINE_UNAVAILABLE",
                "field": "engine",
                "message": message,
            },
        )

    @staticmethod
    def _engine_unsupported_runtime_error(message: str) -> HTTPException:
        return HTTPException(
            status_code=400,
            detail={
                "code": "CODING_AGENT_ENGINE_UNSUPPORTED_RUNTIME",
                "field": "engine",
                "message": message,
            },
        )

    @staticmethod
    def _sandbox_required_error(message: str) -> HTTPException:
        return HTTPException(
            status_code=400,
            detail={
                "code": "CODING_AGENT_SANDBOX_REQUIRED",
                "field": "engine",
                "message": message,
            },
        )

    @staticmethod
    def _compact_messages_for_budget(messages: list[dict[str, str]], max_chars: int) -> list[dict[str, str]]:
        if max_chars < 512:
            max_chars = 512
        if not messages:
            return messages

        total_chars = sum(len(str(item.get("content") or "")) for item in messages)
        if total_chars <= max_chars:
            return messages

        preserved: list[dict[str, str]] = []
        remaining_budget = max_chars
        for message in reversed(messages):
            content = str(message.get("content") or "")
            cost = len(content)
            if not preserved:
                preserved.append(message)
                remaining_budget -= cost
                continue
            if cost <= remaining_budget:
                preserved.append(message)
                remaining_budget -= cost
        compacted = list(reversed(preserved))
        dropped_count = max(0, len(messages) - len(compacted))
        if dropped_count > 0:
            compacted.insert(
                0,
                {
                    "role": "system",
                    "content": f"Context compacted: {dropped_count} earlier message(s) omitted to stay within budget.",
                },
            )
        return compacted

    async def _resolve_run_model_ids(
        self,
        *,
        tenant_id: UUID,
        requested_model_id: UUID | None,
    ) -> tuple[UUID | None, UUID]:
        if requested_model_id is None:
            try:
                resolved = await resolve_coding_agent_chat_model_id(self.db, tenant_id)
            except Exception as exc:
                raise self._model_unavailable_error("No active chat model is available for this tenant.") from exc
            return None, UUID(str(resolved))

        model = (
            await self.db.execute(
                select(ModelRegistry).where(
                    and_(
                        ModelRegistry.id == requested_model_id,
                        ModelRegistry.is_active == True,
                        ModelRegistry.capability_type == ModelCapabilityType.CHAT,
                        or_(ModelRegistry.tenant_id == tenant_id, ModelRegistry.tenant_id.is_(None)),
                    )
                )
            )
        ).scalar_one_or_none()
        if model is None:
            raise self._model_unavailable_error("Selected model is unavailable for this tenant.")
        return requested_model_id, model.id

    @staticmethod
    def _normalize_execution_engine(value: str | None) -> str:
        engine = str(value or CODING_AGENT_ENGINE_NATIVE).strip().lower()
        if engine == CODING_AGENT_ENGINE_OPENCODE:
            return CODING_AGENT_ENGINE_OPENCODE
        return CODING_AGENT_ENGINE_NATIVE

    @staticmethod
    def _opencode_provider_prefix(provider: ModelProviderType | str | None) -> str | None:
        key = str(provider.value if hasattr(provider, "value") else provider or "").strip().lower()
        if not key:
            return None
        mapping = {
            "openai": "openai",
            "anthropic": "anthropic",
            "google": "google",
            "gemini": "google",
            "groq": "groq",
            "mistral": "mistral",
            "together": "together",
            "cohere": "cohere",
        }
        return mapping.get(key)

    async def _resolve_opencode_model_id(
        self,
        *,
        tenant_id: UUID,
        resolved_model_id: UUID,
    ) -> str:
        resolved_model_str = str(resolved_model_id).strip()
        if "/" in resolved_model_str:
            return resolved_model_str

        map_raw = (os.getenv("APPS_CODING_AGENT_OPENCODE_MODEL_MAP_JSON") or "").strip()
        if map_raw:
            try:
                model_map = json.loads(map_raw)
            except Exception:
                model_map = {}
            mapped = ""
            if isinstance(model_map, dict):
                mapped = str(model_map.get(resolved_model_str) or "").strip()
            if mapped:
                return mapped

        model_row = (
            await self.db.execute(
                select(ModelRegistry)
                .options(selectinload(ModelRegistry.providers))
                .where(
                    and_(
                        ModelRegistry.id == resolved_model_id,
                        ModelRegistry.is_active == True,
                        ModelRegistry.capability_type == ModelCapabilityType.CHAT,
                        or_(ModelRegistry.tenant_id == tenant_id, ModelRegistry.tenant_id.is_(None)),
                    )
                )
            )
        ).scalar_one_or_none()
        if model_row is not None:
            tenant_bindings = [item for item in (model_row.providers or []) if item.is_enabled and item.tenant_id == tenant_id]
            global_bindings = [item for item in (model_row.providers or []) if item.is_enabled and item.tenant_id is None]
            for binding in sorted([*tenant_bindings, *global_bindings], key=lambda item: int(item.priority or 0)):
                provider_model_id = str(binding.provider_model_id or "").strip()
                if not provider_model_id:
                    continue
                if "/" in provider_model_id:
                    return provider_model_id
                prefix = self._opencode_provider_prefix(binding.provider)
                if prefix:
                    return f"{prefix}/{provider_model_id}"

        default_model = (os.getenv("APPS_CODING_AGENT_OPENCODE_DEFAULT_MODEL") or "").strip()
        if default_model:
            return default_model

        raise self._engine_unavailable_error(
            "OpenCode model mapping unavailable for resolved model. "
            "Configure provider bindings, APPS_CODING_AGENT_OPENCODE_MODEL_MAP_JSON, "
            "or APPS_CODING_AGENT_OPENCODE_DEFAULT_MODEL."
        )

    @staticmethod
    def _run_context(run: AgentRun) -> dict[str, Any]:
        input_params = run.input_params if isinstance(run.input_params, dict) else {}
        context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
        input_params["context"] = context
        run.input_params = input_params
        return context

    def _assert_opencode_sandbox_mode_available(self) -> None:
        if not self._run_sandbox_service.settings.required:
            return
        if self._run_sandbox_service.is_controller_enabled:
            return
        raise self._sandbox_required_error(
            "OpenCode engine requires sandbox-controller mode when "
            "APPS_CODING_AGENT_SANDBOX_REQUIRED=1."
        )

    async def _ensure_run_sandbox_context(
        self,
        *,
        run: AgentRun,
        app: PublishedApp,
        base_revision: PublishedAppRevision,
        actor_id: UUID | None,
    ) -> dict[str, str]:
        session = await self._run_sandbox_service.ensure_session(
            run=run,
            app=app,
            revision=base_revision,
            actor_id=actor_id,
        )
        status = session.status.value if hasattr(session.status, "value") else str(session.status)
        if session.status == PublishedAppCodingRunSandboxStatus.error or not session.sandbox_id:
            raise self._engine_unsupported_runtime_error(
                f"Failed to initialize run sandbox session: {session.last_error or 'unknown error'}"
            )
        workspace_path = str(session.workspace_path or "/workspace")
        context = self._run_context(run)
        context["coding_run_sandbox_id"] = str(session.sandbox_id)
        context["coding_run_sandbox_status"] = status
        context["coding_run_sandbox_started_at"] = (
            session.started_at.isoformat() if isinstance(session.started_at, datetime) else None
        )
        context["coding_run_sandbox_workspace_path"] = workspace_path
        return {
            "opencode_sandbox_id": str(session.sandbox_id),
            "opencode_workspace_path": workspace_path,
        }

    async def _recover_or_bootstrap_run_sandbox_context(
        self,
        *,
        run: AgentRun,
        app: PublishedApp,
    ) -> tuple[str | None, str | None]:
        context = self._run_context(run)
        sandbox_id = str(context.get("coding_run_sandbox_id") or "").strip()
        if sandbox_id:
            changed = False
            if not str(context.get("opencode_sandbox_id") or "").strip():
                context["opencode_sandbox_id"] = sandbox_id
                changed = True
            workspace_path = str(context.get("coding_run_sandbox_workspace_path") or "").strip()
            if workspace_path and not str(context.get("opencode_workspace_path") or "").strip():
                context["opencode_workspace_path"] = workspace_path
                changed = True
            if changed:
                await self.db.commit()
            return sandbox_id, None

        session = await self._run_sandbox_service.get_session_for_run(run_id=run.id)
        if session is not None and session.sandbox_id:
            context["coding_run_sandbox_id"] = str(session.sandbox_id)
            context["coding_run_sandbox_status"] = (
                session.status.value if hasattr(session.status, "value") else str(session.status)
            )
            context["coding_run_sandbox_started_at"] = (
                session.started_at.isoformat() if isinstance(session.started_at, datetime) else None
            )
            workspace_path = str(session.workspace_path or "/workspace")
            context["coding_run_sandbox_workspace_path"] = workspace_path
            context["opencode_sandbox_id"] = str(session.sandbox_id)
            context["opencode_workspace_path"] = workspace_path
            await self.db.commit()
            return str(session.sandbox_id), None

        base_revision_id = run.base_revision_id or app.current_draft_revision_id
        if base_revision_id is None:
            return None, "Run sandbox session is required before execution (base revision missing)."
        base_revision = await self.db.get(PublishedAppRevision, base_revision_id)
        if base_revision is None:
            return None, "Run sandbox session is required before execution (base revision not found)."

        actor_id = run.initiator_user_id or run.user_id
        try:
            context.update(
                await self._ensure_run_sandbox_context(
                    run=run,
                    app=app,
                    base_revision=base_revision,
                    actor_id=actor_id,
                )
            )
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            message = str(detail.get("message") or exc.detail or "sandbox bootstrap failed")
            return None, f"Run sandbox session is required before execution ({message})."
        except Exception as exc:
            return None, f"Run sandbox session is required before execution ({exc})."

        await self.db.commit()
        sandbox_id = str(context.get("coding_run_sandbox_id") or "").strip()
        if sandbox_id:
            return sandbox_id, None
        return None, "Run sandbox session is required before execution."

    def _resolve_engine_for_run(self, run: AgentRun) -> PublishedAppCodingAgentEngine:
        engine = self._normalize_execution_engine(str(run.execution_engine or CODING_AGENT_ENGINE_NATIVE))
        if engine == CODING_AGENT_ENGINE_OPENCODE:
            return self._opencode_engine
        return self._native_engine

    async def create_run(
        self,
        *,
        app: PublishedApp,
        base_revision: PublishedAppRevision,
        actor_id: UUID | None,
        user_prompt: str,
        messages: list[dict[str, str]] | None = None,
        requested_scopes: list[str] | None = None,
        requested_model_id: UUID | None = None,
        execution_engine: str = CODING_AGENT_ENGINE_NATIVE,
    ) -> AgentRun:
        requested_model_id, resolved_model_id = await self._resolve_run_model_ids(
            tenant_id=app.tenant_id,
            requested_model_id=requested_model_id,
        )
        normalized_engine = self._normalize_execution_engine(execution_engine)
        opencode_model_id: str | None = None
        if normalized_engine == CODING_AGENT_ENGINE_OPENCODE:
            self._assert_opencode_sandbox_mode_available()
            try:
                await self._opencode_client.ensure_healthy()
            except Exception as exc:
                raise self._engine_unavailable_error(f"OpenCode engine is unavailable: {exc}") from exc
            opencode_model_id = await self._resolve_opencode_model_id(
                tenant_id=app.tenant_id,
                resolved_model_id=resolved_model_id,
            )
        profile = await ensure_coding_agent_profile(self.db, app.tenant_id)

        normalized_messages: list[dict[str, str]] = []
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "").strip().lower()
            content = str(message.get("content") or "").strip()
            if role not in {"user", "assistant", "system"}:
                continue
            if not content:
                continue
            normalized_messages.append({"role": role, "content": content})
        if not normalized_messages:
            normalized_messages = [{"role": "user", "content": user_prompt}]
        elif normalized_messages[-1]["role"] != "user" or normalized_messages[-1]["content"] != user_prompt:
            normalized_messages.append({"role": "user", "content": user_prompt})
        message_budget_chars = int(os.getenv("APPS_CODING_AGENT_MESSAGE_BUDGET_CHARS", "28000"))
        normalized_messages = self._compact_messages_for_budget(normalized_messages, message_budget_chars)

        input_params = {
            "input": user_prompt,
            "messages": normalized_messages,
            "context": {
                "surface": CODING_AGENT_SURFACE,
                "app_id": str(app.id),
                "base_revision_id": str(base_revision.id),
                "entry_file": base_revision.entry_file,
                "resolved_model_id": str(resolved_model_id),
                "execution_engine": normalized_engine,
                "opencode_model_id": opencode_model_id,
            },
        }

        run_id = await self.executor.start_run(
            profile.id,
            input_params,
            user_id=actor_id,
            background=False,
            mode=ExecutionMode.DEBUG,
            requested_scopes=requested_scopes,
        )

        run = await self.db.get(AgentRun, run_id)
        if run is None:
            raise RuntimeError("Failed to load created coding-agent run")

        run.surface = CODING_AGENT_SURFACE
        run.published_app_id = app.id
        run.base_revision_id = base_revision.id
        run.result_revision_id = None
        run.checkpoint_revision_id = None
        run.requested_model_id = requested_model_id
        run.resolved_model_id = resolved_model_id
        run.execution_engine = normalized_engine
        run.engine_run_ref = None

        try:
            sandbox_context = await self._ensure_run_sandbox_context(
                run=run,
                app=app,
                base_revision=base_revision,
                actor_id=actor_id,
            )
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            message = str(detail.get("message") or exc.detail)
            run.status = RunStatus.failed
            run.error_message = message
            run.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            raise
        except Exception as exc:
            run.status = RunStatus.failed
            run.error_message = str(exc)
            run.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            raise self._engine_unsupported_runtime_error(f"Failed to initialize run sandbox: {exc}") from exc

        context = self._run_context(run)
        if normalized_engine == CODING_AGENT_ENGINE_OPENCODE:
            context.update(sandbox_context)

        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def list_runs(self, *, app_id: UUID, limit: int = 25) -> list[AgentRun]:
        result = await self.db.execute(
            select(AgentRun)
            .where(
                and_(
                    AgentRun.surface == CODING_AGENT_SURFACE,
                    AgentRun.published_app_id == app_id,
                )
            )
            .order_by(AgentRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_run_for_app(self, *, app_id: UUID, run_id: UUID) -> AgentRun:
        result = await self.db.execute(
            select(AgentRun).where(
                and_(
                    AgentRun.id == run_id,
                    AgentRun.surface == CODING_AGENT_SURFACE,
                    AgentRun.published_app_id == app_id,
                )
            )
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail="Coding-agent run not found")
        return run

    async def cancel_run(self, run: AgentRun) -> AgentRun:
        status = run.status.value if hasattr(run.status, "value") else str(run.status)
        if status in {RunStatus.completed.value, RunStatus.failed.value, RunStatus.cancelled.value}:
            return run
        engine = self._resolve_engine_for_run(run)
        if self._normalize_execution_engine(str(run.execution_engine)) == CODING_AGENT_ENGINE_OPENCODE:
            try:
                cancel_result = await engine.cancel(run)
            except Exception as exc:
                cancel_result = None
                logger.exception("OpenCode cancellation failed for run %s: %s", run.id, exc)
            if cancel_result and cancel_result.confirmed:
                run.status = RunStatus.cancelled
                run.error_message = None
            else:
                diagnostics = (cancel_result.diagnostics if cancel_result else None) or []
                message = str(diagnostics[0].get("message") or "OpenCode cancellation could not be confirmed")
                run.status = RunStatus.failed
                run.error_message = message
        else:
            run.status = RunStatus.cancelled

        sandbox_session = await self._run_sandbox_service.stop_session_for_run(run_id=run.id)
        if sandbox_session is not None:
            context = self._run_context(run)
            context["coding_run_sandbox_status"] = (
                sandbox_session.status.value
                if hasattr(sandbox_session.status, "value")
                else str(sandbox_session.status)
            )

        run.completed_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def list_checkpoints(self, *, app_id: UUID, limit: int = 25) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(AgentRun)
            .where(
                and_(
                    AgentRun.surface == CODING_AGENT_SURFACE,
                    AgentRun.published_app_id == app_id,
                    AgentRun.checkpoint_revision_id.is_not(None),
                )
            )
            .order_by(AgentRun.created_at.desc())
            .limit(limit)
        )
        runs = list(result.scalars().all())
        payload: list[dict[str, Any]] = []
        for run in runs:
            payload.append(
                {
                    "checkpoint_id": str(run.checkpoint_revision_id),
                    "run_id": str(run.id),
                    "app_id": str(app_id),
                    "revision_id": str(run.result_revision_id) if run.result_revision_id else None,
                    "created_at": run.completed_at or run.created_at,
                }
            )
        return payload

    async def restore_checkpoint(
        self,
        *,
        app: PublishedApp,
        checkpoint_revision_id: UUID,
        actor_id: UUID | None,
        run: AgentRun | None = None,
    ) -> PublishedAppRevision:
        checkpoint_revision = await self.db.get(PublishedAppRevision, checkpoint_revision_id)
        if checkpoint_revision is None or str(checkpoint_revision.published_app_id) != str(app.id):
            raise HTTPException(status_code=404, detail="Checkpoint revision not found")

        current_revision = await self.db.get(PublishedAppRevision, app.current_draft_revision_id)
        if current_revision is None:
            current_revision = checkpoint_revision

        restored = await self._create_draft_revision_from_files(
            app=app,
            current=current_revision,
            actor_id=actor_id,
            files=dict(checkpoint_revision.files or {}),
            entry_file=checkpoint_revision.entry_file,
        )

        if actor_id is not None:
            runtime_service = PublishedAppDraftDevRuntimeService(self.db)
            try:
                await runtime_service.sync_session(
                    app=app,
                    revision=restored,
                    user_id=actor_id,
                    files=dict(restored.files or {}),
                    entry_file=restored.entry_file,
                )
            except PublishedAppDraftDevRuntimeDisabled:
                pass

        if run is not None:
            run.result_revision_id = restored.id
            run.checkpoint_revision_id = checkpoint_revision.id

        await self.db.commit()
        await self.db.refresh(restored)
        return restored

    async def _create_draft_revision_from_files(
        self,
        *,
        app: PublishedApp,
        current: PublishedAppRevision,
        actor_id: UUID | None,
        files: dict[str, str],
        entry_file: str,
    ) -> PublishedAppRevision:
        sanitized_files = _filter_builder_snapshot_files(files)
        _validate_builder_project_or_raise(sanitized_files, entry_file)
        revision = PublishedAppRevision(
            published_app_id=app.id,
            kind=PublishedAppRevisionKind.draft,
            template_key=app.template_key,
            entry_file=entry_file,
            files=sanitized_files,
            build_status=PublishedAppRevisionBuildStatus.queued,
            build_seq=int(current.build_seq or 0) + 1,
            build_error=None,
            build_started_at=None,
            build_finished_at=None,
            dist_storage_prefix=None,
            dist_manifest=None,
            template_runtime="vite_static",
            compiled_bundle=None,
            bundle_hash=sha256(json.dumps(sanitized_files, sort_keys=True).encode("utf-8")).hexdigest(),
            source_revision_id=current.id,
            created_by=actor_id,
        )
        self.db.add(revision)
        await self.db.flush()
        app.current_draft_revision_id = revision.id
        return revision

    async def auto_apply_and_checkpoint(self, run: AgentRun) -> PublishedAppRevision | None:
        if run.result_revision_id is not None:
            existing = await self.db.get(PublishedAppRevision, run.result_revision_id)
            return existing

        if run.published_app_id is None:
            return None
        actor_id = run.initiator_user_id or run.user_id
        if actor_id is None:
            return None

        app = await self.db.get(PublishedApp, run.published_app_id)
        if app is None:
            return None

        current_revision_id = app.current_draft_revision_id or run.base_revision_id
        if current_revision_id is None:
            return None
        current = await self.db.get(PublishedAppRevision, current_revision_id)
        if current is None:
            return None

        runtime_service = PublishedAppDraftDevRuntimeService(self.db)
        input_params = run.input_params if isinstance(run.input_params, dict) else {}
        context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
        run_sandbox_id = str(context.get("coding_run_sandbox_id") or "").strip()

        if run_sandbox_id:
            snapshot = await runtime_service.client.snapshot_files(sandbox_id=run_sandbox_id)
        else:
            try:
                session = await runtime_service.ensure_active_session(
                    app=app,
                    revision=current,
                    user_id=actor_id,
                )
            except PublishedAppDraftDevRuntimeDisabled:
                return None

            if session.status == PublishedAppDraftDevSessionStatus.error or not session.sandbox_id:
                return None
            snapshot = await runtime_service.client.snapshot_files(sandbox_id=session.sandbox_id)

        raw_files = snapshot.get("files")
        if not isinstance(raw_files, dict):
            return None
        files = _filter_builder_snapshot_files(raw_files)

        revision = await self._create_draft_revision_from_files(
            app=app,
            current=current,
            actor_id=actor_id,
            files=files,
            entry_file=current.entry_file,
        )
        run.result_revision_id = revision.id
        run.checkpoint_revision_id = revision.id
        await self.db.commit()
        await self.db.refresh(revision)

        # If the user already has an active builder draft session, best-effort sync it
        # to the newly auto-applied revision so preview reflects coding-run changes.
        try:
            existing_builder_session = await runtime_service.get_session(
                app_id=app.id,
                user_id=actor_id,
            )
            if existing_builder_session is not None and existing_builder_session.sandbox_id:
                await runtime_service.sync_session(
                    app=app,
                    revision=revision,
                    user_id=actor_id,
                    files=files,
                    entry_file=revision.entry_file,
                )
                await self.db.commit()
        except PublishedAppDraftDevRuntimeDisabled:
            pass
        except Exception as exc:
            logger.warning(
                "Failed to sync existing builder draft session after auto-apply for app %s run %s: %s",
                app.id,
                run.id,
                exc,
            )
        return revision

    def _envelope(
        self,
        *,
        seq: int,
        event: str,
        run_id: UUID,
        app_id: UUID,
        stage: str,
        payload: dict[str, Any] | None = None,
        diagnostics: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "event": event,
            "run_id": str(run_id),
            "app_id": str(app_id),
            "seq": seq,
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "payload": payload or {},
            "diagnostics": diagnostics or [],
        }
        return data

    @staticmethod
    def _coerce_assistant_text(value: Any) -> str | None:
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        parts.append(text)
                    continue
                if isinstance(item, dict):
                    nested = PublishedAppCodingAgentRuntimeService._coerce_assistant_text(item)
                    if nested:
                        parts.append(nested)
            joined = " ".join(parts).strip()
            return joined or None
        if isinstance(value, dict):
            for key in ("content", "message", "text", "summary"):
                candidate = value.get(key)
                text = PublishedAppCodingAgentRuntimeService._coerce_assistant_text(candidate)
                if text:
                    return text
        return None

    def _extract_assistant_text_from_output(self, output_result: Any) -> str | None:
        if not isinstance(output_result, dict):
            return None

        state = output_result.get("state")
        if isinstance(state, dict):
            text = self._coerce_assistant_text(state.get("last_agent_output"))
            if text:
                return text

        text = self._coerce_assistant_text(output_result.get("last_agent_output"))
        if text:
            return text

        messages = output_result.get("messages")
        if isinstance(messages, list):
            for message in reversed(messages):
                if not isinstance(message, dict):
                    continue
                role = str(message.get("role") or message.get("type") or "").strip().lower()
                if role not in {"assistant", "ai"}:
                    continue
                text = self._coerce_assistant_text(message.get("content"))
                if text:
                    return text

        return None

    def _fallback_assistant_text(self, run: AgentRun) -> str:
        input_params = run.input_params if isinstance(run.input_params, dict) else {}
        prompt = str(input_params.get("input") or "").strip().lower()
        if prompt in {"hi", "hello", "hey", "yo", "shalom"}:
            return "Hi. I can edit app code, run checks, and explain changes. What would you like to change?"
        if "what can you do" in prompt or prompt == "help" or "how can you help" in prompt:
            return (
                "I can inspect and edit files, run targeted checks/tests, and create or restore checkpoints. "
                "Tell me what you want to build or fix."
            )
        return "I can help with code changes, debugging, and verification in this app workspace. Tell me your goal."

    async def stream_run_events(
        self,
        *,
        app: PublishedApp,
        run: AgentRun,
        resume_payload: dict[str, Any] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        run_id = run.id
        persistent_run = await self.db.get(AgentRun, run_id)
        if persistent_run is not None:
            run = persistent_run

        seq = 1
        assistant_delta_emitted = False

        def emit(
            event: str,
            stage: str,
            payload: dict[str, Any] | None = None,
            diagnostics: list[dict[str, Any]] | None = None,
        ) -> dict[str, Any]:
            nonlocal seq
            envelope = self._envelope(
                seq=seq,
                event=event,
                run_id=run.id,
                app_id=app.id,
                stage=stage,
                payload=payload,
                diagnostics=diagnostics,
            )
            seq += 1
            return envelope

        async def finalize_sandbox(reason: PublishedAppCodingRunSandboxStatus) -> None:
            sandbox_session = await self._run_sandbox_service.stop_session_for_run(
                run_id=run.id,
                reason=reason,
            )
            if sandbox_session is None:
                return
            context = self._run_context(run)
            context["coding_run_sandbox_status"] = (
                sandbox_session.status.value
                if hasattr(sandbox_session.status, "value")
                else str(sandbox_session.status)
            )

        yield emit(
            "run.accepted",
            "run",
            {
                "status": run.status.value if hasattr(run.status, "value") else str(run.status),
                "surface": CODING_AGENT_SURFACE,
            },
        )
        yield emit("plan.updated", "plan", {"summary": "Coding-agent run started"})

        terminal_status = run.status.value if hasattr(run.status, "value") else str(run.status)
        if terminal_status in {RunStatus.completed.value, RunStatus.failed.value, RunStatus.cancelled.value}:
            if terminal_status == RunStatus.completed.value:
                await finalize_sandbox(PublishedAppCodingRunSandboxStatus.stopped)
                assistant_text = self._extract_assistant_text_from_output(run.output_result) or self._fallback_assistant_text(run)
                yield emit("assistant.delta", "assistant", {"content": assistant_text})
                yield emit("run.completed", "run", self.serialize_run(run))
            else:
                await finalize_sandbox(PublishedAppCodingRunSandboxStatus.error)
                yield emit(
                    "run.failed",
                    "run",
                    self.serialize_run(run),
                    [{"message": run.error_message or f"run {terminal_status}"}],
                )
            return

        run_context = self._run_context(run)
        sandbox_id = str(run_context.get("coding_run_sandbox_id") or "").strip()
        if not sandbox_id:
            sandbox_id, sandbox_error = await self._recover_or_bootstrap_run_sandbox_context(run=run, app=app)
        else:
            sandbox_error = None
        if not sandbox_id:
            run.status = RunStatus.failed
            run.error_message = sandbox_error or "Run sandbox session is required before execution."
            run.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            yield emit(
                "run.failed",
                "run",
                self.serialize_run(run),
                [{"code": "CODING_AGENT_SANDBOX_REQUIRED", "message": run.error_message}],
            )
            return

        try:
            engine = self._resolve_engine_for_run(run)
            async for raw_event in engine.stream(
                EngineRunContext(
                    app=app,
                    run=run,
                    resume_payload=resume_payload,
                )
            ):
                mapped_event = raw_event.event
                stage = raw_event.stage
                payload = raw_event.payload
                diagnostics = raw_event.diagnostics
                if mapped_event == "assistant.delta":
                    content = str((payload or {}).get("content") or "").strip()
                    if content:
                        assistant_delta_emitted = True
                yield emit(mapped_event, stage, payload, diagnostics)

            run = await self.db.get(AgentRun, run_id) or run
            status = run.status.value if hasattr(run.status, "value") else str(run.status)
            if status == RunStatus.completed.value:
                revision = await self.auto_apply_and_checkpoint(run)
                await finalize_sandbox(PublishedAppCodingRunSandboxStatus.stopped)
                if revision is not None:
                    yield emit(
                        "revision.created",
                        "revision",
                        {
                            "revision_id": str(revision.id),
                            "entry_file": revision.entry_file,
                            "file_count": len(revision.files or {}),
                        },
                    )
                    yield emit(
                        "checkpoint.created",
                        "checkpoint",
                        {
                            "checkpoint_id": str(run.checkpoint_revision_id or revision.id),
                            "revision_id": str(revision.id),
                        },
                    )
                if not assistant_delta_emitted:
                    assistant_text = self._extract_assistant_text_from_output(run.output_result) or self._fallback_assistant_text(run)
                    yield emit("assistant.delta", "assistant", {"content": assistant_text})
                yield emit("run.completed", "run", self.serialize_run(run))
                return

            if status == RunStatus.cancelled.value:
                await finalize_sandbox(PublishedAppCodingRunSandboxStatus.stopped)
                yield emit(
                    "run.failed",
                    "run",
                    self.serialize_run(run),
                    [{"message": "run cancelled"}],
                )
                return

            if status == RunStatus.paused.value:
                await finalize_sandbox(PublishedAppCodingRunSandboxStatus.stopped)
                yield emit("run.completed", "run", self.serialize_run(run))
                return

            await finalize_sandbox(PublishedAppCodingRunSandboxStatus.error)
            yield emit(
                "run.failed",
                "run",
                self.serialize_run(run),
                [{"message": run.error_message or "run failed"}],
            )
        except Exception as exc:
            failed_run = await self.db.get(AgentRun, run_id)
            if failed_run is not None:
                failed_run.status = RunStatus.failed
                failed_run.error_message = str(exc)
                failed_run.completed_at = datetime.now(timezone.utc)
                sandbox_session = await self._run_sandbox_service.stop_session_for_run(
                    run_id=failed_run.id,
                    reason=PublishedAppCodingRunSandboxStatus.error,
                )
                if sandbox_session is not None:
                    context = self._run_context(failed_run)
                    context["coding_run_sandbox_status"] = (
                        sandbox_session.status.value
                        if hasattr(sandbox_session.status, "value")
                        else str(sandbox_session.status)
                    )
                await self.db.commit()
                run = failed_run
            yield emit(
                "run.failed",
                "run",
                self.serialize_run(run),
                [{"message": str(exc)}],
            )
