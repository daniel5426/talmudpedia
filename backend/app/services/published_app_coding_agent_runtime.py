from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, AsyncGenerator
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionMode
from app.db.postgres.models.agents import Agent, AgentRun, RunStatus
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppCodingChatSession,
    PublishedAppDraftDevSessionStatus,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
)
from app.services.published_app_coding_agent_profile import (
    CODING_AGENT_PROFILE_SYSTEM_KEY,
    ensure_coding_agent_profile,
)
from app.services.published_app_coding_agent_engines.base import PublishedAppCodingAgentEngine
from app.services.published_app_coding_agent_engines.opencode_engine import OpenCodePublishedAppCodingAgentEngine
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from app.services.published_app_revision_store import PublishedAppRevisionStore
from app.services.published_app_agent_integration_contract import build_published_app_agent_integration_contract
from app.services.opencode_server_client import OpenCodeServerClient
from app.services.published_app_coding_pipeline_trace import pipeline_trace
from app.api.routers.published_apps_admin_files import _filter_builder_snapshot_files, _validate_builder_project_or_raise
from app.services.published_app_coding_agent_runtime_sandbox import PublishedAppCodingAgentRuntimeSandboxMixin
from app.services.published_app_coding_agent_runtime_streaming import PublishedAppCodingAgentRuntimeStreamingMixin
from app.services.context_window_service import ContextWindowService
from app.services.model_accounting import usage_payload_from_run

logger = logging.getLogger(__name__)

CODING_AGENT_ENGINE_OPENCODE = "opencode"
CODING_AGENT_OPENCODE_AUTO_MODEL_ID = "opencode/big-pickle"
_TERMINAL_RUN_STATUSES = {
    RunStatus.completed.value,
    RunStatus.failed.value,
    RunStatus.cancelled.value,
    RunStatus.paused.value,
}
_WORKSPACE_WRITE_TOOL_HINTS = (
    "write",
    "edit",
    "replace",
    "insert",
    "append",
    "prepend",
    "rename",
    "move",
    "delete",
    "remove",
    "mkdir",
    "touch",
    "create",
    "apply_patch",
    "mv",
    "rm",
    "cp",
    "bash",
    "command",
    "exec",
)


class PublishedAppCodingAgentRuntimeService(
    PublishedAppCodingAgentRuntimeSandboxMixin,
    PublishedAppCodingAgentRuntimeStreamingMixin,
):
    _profile_cache_by_organization: dict[str, tuple[str, float]] = {}

    def __init__(self, db: AsyncSession):
        self.db = db
        self.executor = AgentExecutorService(db=db)
        self._opencode_client = OpenCodeServerClient.from_env()
        self._opencode_engine = OpenCodePublishedAppCodingAgentEngine(
            db=self.db,
            client=self._opencode_client,
        )

    @staticmethod
    def _trace(event: str, **fields: Any) -> None:
        pipeline_trace(event, pipeline="runtime", **fields)

    @staticmethod
    def serialize_run(run: AgentRun) -> dict[str, Any]:
        execution_engine = CODING_AGENT_ENGINE_OPENCODE
        input_params = run.input_params if isinstance(run.input_params, dict) else {}
        context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
        requested_model_id = (
            str(context.get("requested_model_id") or "").strip()
            or (str(run.requested_model_id) if run.requested_model_id else "")
        )
        resolved_model_id = (
            str(context.get("resolved_model_id") or "").strip()
            or (str(run.resolved_model_id) if run.resolved_model_id else "")
        )
        return {
            "run_id": str(run.id),
            "status": run.status.value if hasattr(run.status, "value") else str(run.status),
            "execution_engine": execution_engine,
            "surface": run.surface,
            "published_app_id": str(run.published_app_id) if run.published_app_id else None,
            "base_revision_id": str(run.base_revision_id) if run.base_revision_id else None,
            "result_revision_id": str(run.result_revision_id) if run.result_revision_id else None,
            "requested_model_id": requested_model_id or None,
            "resolved_model_id": resolved_model_id or None,
            "error": run.error_message,
            "created_at": run.created_at,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "sandbox_id": str(context.get("preview_sandbox_id") or "") or None,
            "sandbox_status": str(context.get("preview_sandbox_status") or "") or None,
            "sandbox_started_at": context.get("preview_sandbox_started_at"),
            "chat_session_id": str(context.get("chat_session_id") or "") or None,
            "context_window": ContextWindowService.read_from_run(run),
            "run_usage": usage_payload_from_run(run),
        }

    @staticmethod
    def _default_execution_engine() -> str:
        return CODING_AGENT_ENGINE_OPENCODE

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

    @staticmethod
    def _build_selected_agent_contract_message(contract: dict[str, Any] | None) -> str | None:
        if not isinstance(contract, dict) or not contract:
            return None
        max_chars = int(os.getenv("APPS_CODING_AGENT_CONTRACT_CONTEXT_MAX_CHARS", "16000") or 16000)
        if max_chars < 1024:
            max_chars = 1024
        try:
            rendered = json.dumps(contract, sort_keys=True, default=str)
        except Exception:
            rendered = str(contract)
        if len(rendered) > max_chars:
            rendered = rendered[:max_chars] + "... [truncated]"
        return (
            "Selected app agent integration contract (source of truth for tools/schemas/UI hints):\n"
            f"{rendered}"
        )

    @staticmethod
    def _profile_cache_ttl_seconds() -> float:
        raw = str(os.getenv("APPS_CODING_AGENT_PROFILE_CACHE_TTL_SECONDS") or "120").strip()
        try:
            ttl = float(raw)
        except Exception:
            ttl = 120.0
        return max(0.0, ttl)

    async def _resolve_cached_coding_agent_profile(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID | None,
    ) -> tuple[Agent, bool]:
        cache_ttl = self._profile_cache_ttl_seconds()
        organization_key = str(organization_id)
        if cache_ttl > 0:
            cache_entry = self._profile_cache_by_organization.get(organization_key)
            if cache_entry:
                profile_id_raw, expires_at = cache_entry
                if time.monotonic() <= float(expires_at):
                    try:
                        profile_id = UUID(str(profile_id_raw))
                    except Exception:
                        profile_id = None
                    if profile_id is not None:
                        cached_profile = await self.db.get(Agent, profile_id)
                        if (
                            cached_profile is not None
                            and str(cached_profile.organization_id) == organization_key
                            and str(cached_profile.system_key or "") == CODING_AGENT_PROFILE_SYSTEM_KEY
                            and bool(cached_profile.is_active)
                        ):
                            return cached_profile, True
                self._profile_cache_by_organization.pop(organization_key, None)

        profile = await ensure_coding_agent_profile(
            self.db,
            organization_id,
            actor_user_id=actor_user_id,
        )
        if cache_ttl > 0 and profile is not None and profile.id is not None:
            self._profile_cache_by_organization[organization_key] = (
                str(profile.id),
                time.monotonic() + cache_ttl,
            )
        return profile, False

    @staticmethod
    def _normalize_execution_engine(value: str | None) -> str:
        engine_raw = str(value or CODING_AGENT_ENGINE_OPENCODE).strip().lower()
        if not engine_raw:
            return CODING_AGENT_ENGINE_OPENCODE
        if engine_raw == CODING_AGENT_ENGINE_OPENCODE or engine_raw.endswith(".opencode") or "opencode" in engine_raw:
            return CODING_AGENT_ENGINE_OPENCODE
        return CODING_AGENT_ENGINE_OPENCODE

    @staticmethod
    def _normalize_opencode_model_id(raw_model_id: str | None) -> str | None:
        raw = str(raw_model_id or "").strip()
        if not raw:
            return None
        if "/" not in raw:
            raw = f"{CODING_AGENT_ENGINE_OPENCODE}/{raw}"
        provider, model = raw.split("/", 1)
        provider = provider.strip().lower()
        model = model.strip()
        if provider != CODING_AGENT_ENGINE_OPENCODE or not model:
            return None
        return f"{provider}/{model}"

    def _resolve_requested_opencode_model_id(self, requested_model_id: str | None) -> tuple[str | None, str]:
        requested = self._normalize_opencode_model_id(requested_model_id)
        if requested_model_id and not requested:
            raise self._model_unavailable_error(
                "Selected model must be an OpenCode model id (for example: opencode/big-pickle)."
            )
        fallback = CODING_AGENT_OPENCODE_AUTO_MODEL_ID
        return requested, requested or fallback

    @staticmethod
    def _run_context(run: AgentRun) -> dict[str, Any]:
        input_params = dict(run.input_params) if isinstance(run.input_params, dict) else {}
        raw_context = input_params.get("context")
        context = dict(raw_context) if isinstance(raw_context, dict) else {}
        input_params["context"] = context
        run.input_params = input_params
        return context

    @staticmethod
    def _timing_metrics_for_run(run: AgentRun) -> dict[str, int]:
        context = PublishedAppCodingAgentRuntimeService._run_context(run)
        metrics = context.get("timing_metrics_ms")
        if not isinstance(metrics, dict):
            metrics = {}
            context["timing_metrics_ms"] = metrics
        return metrics

    @staticmethod
    def _record_timing_metric(run: AgentRun, *, phase: str, started_at: float) -> int:
        duration_ms = max(0, int((time.monotonic() - started_at) * 1000))
        metrics = PublishedAppCodingAgentRuntimeService._timing_metrics_for_run(run)
        metrics[str(phase)] = duration_ms
        return duration_ms

    @staticmethod
    def _set_timing_metric_value(run: AgentRun, *, metric: str, value: Any) -> None:
        metrics = PublishedAppCodingAgentRuntimeService._timing_metrics_for_run(run)
        metrics[str(metric)] = value

    def _resolve_engine_for_run(self, run: AgentRun) -> PublishedAppCodingAgentEngine:
        _ = run
        return self._opencode_engine

    @staticmethod
    def _normalize_recovery_messages(
        messages: list[dict[str, str]] | None,
        *,
        user_prompt: str,
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        normalized: list[dict[str, str]] = []
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "").strip().lower()
            content = str(message.get("content") or "").strip()
            if role not in {"user", "assistant", "system"} or not content:
                continue
            normalized.append({"role": role, "content": content})
        if not normalized:
            normalized = [{"role": "user", "content": user_prompt}]
        elif normalized[-1]["role"] != "user" or normalized[-1]["content"] != user_prompt:
            normalized.append({"role": "user", "content": user_prompt})

        message_budget_chars = int(os.getenv("APPS_CODING_AGENT_MESSAGE_BUDGET_CHARS", "28000"))
        normalized = PublishedAppCodingAgentRuntimeService._compact_messages_for_budget(normalized, message_budget_chars)
        minimal = [{"role": "user", "content": user_prompt}]
        return normalized, minimal

    async def _load_chat_session(
        self,
        *,
        chat_session_id: UUID | None,
    ) -> PublishedAppCodingChatSession | None:
        if chat_session_id is None:
            return None
        session = await self.db.get(PublishedAppCodingChatSession, chat_session_id)
        return session

    @staticmethod
    def _session_matches_runtime(
        session: PublishedAppCodingChatSession,
        *,
        sandbox_id: str,
        workspace_path: str,
    ) -> bool:
        session_id = str(session.opencode_session_id or "").strip()
        if not session_id:
            return False
        if str(session.opencode_sandbox_id or "").strip() != str(sandbox_id or "").strip():
            return False
        if str(session.opencode_workspace_path or "").strip() != str(workspace_path or "").strip():
            return False
        return True

    async def create_run(
        self,
        *,
        app: PublishedApp,
        base_revision: PublishedAppRevision,
        actor_id: UUID | None,
        user_prompt: str,
        messages: list[dict[str, str]] | None = None,
        requested_scopes: list[str] | None = None,
        requested_model_id: str | None = None,
        execution_engine: str | None = None,
        chat_session_id: UUID | None = None,
    ) -> AgentRun:
        create_run_started_at = time.monotonic()
        create_run_phase_metrics: dict[str, int] = {}
        self._trace(
            "runtime.create_run.requested",
            app_id=str(app.id),
            actor_id=str(actor_id) if actor_id else None,
            chat_session_id=str(chat_session_id) if chat_session_id else None,
            requested_model_id=str(requested_model_id or "") or None,
            requested_engine=str(execution_engine or "") or None,
            messages_count=len(messages or []),
        )

        def _record_create_run_phase_metric(phase: str, started_at: float) -> int:
            duration_ms = max(0, int((time.monotonic() - started_at) * 1000))
            create_run_phase_metrics[str(phase)] = duration_ms
            return duration_ms

        normalized_engine = self._normalize_execution_engine(execution_engine)
        if execution_engine and normalized_engine != CODING_AGENT_ENGINE_OPENCODE:
            raise self._engine_unavailable_error(
                "Only the OpenCode engine is supported."
            )
        create_run_phase_metrics["create_run_opencode_health"] = 0
        create_run_phase_metrics["create_run_opencode_model_resolve"] = 0
        create_run_phase_metrics["create_run_opencode_session_create"] = 0
        if normalized_engine == CODING_AGENT_ENGINE_OPENCODE:
            probe_started_at = time.monotonic()
            try:
                await self._opencode_client.ensure_healthy()
            except Exception as exc:
                self._trace(
                    "runtime.create_run.opencode_unhealthy",
                    app_id=str(app.id),
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                )
                raise self._engine_unavailable_error(f"OpenCode engine is unavailable: {exc}") from exc
            create_run_phase_metrics["create_run_opencode_health"] = max(
                0,
                int((time.monotonic() - probe_started_at) * 1000),
            )

        resolve_model_started_at = time.monotonic()
        requested_model_id, resolved_model_id = self._resolve_requested_opencode_model_id(requested_model_id)
        _record_create_run_phase_metric("create_run_model_resolve", resolve_model_started_at)
        create_run_phase_metrics["create_run_opencode_model_resolve"] = create_run_phase_metrics["create_run_model_resolve"]
        ensure_profile_started_at = time.monotonic()
        profile, profile_cache_hit = await self._resolve_cached_coding_agent_profile(
            organization_id=app.organization_id,
            actor_user_id=actor_id,
        )
        _record_create_run_phase_metric("create_run_profile_resolve", ensure_profile_started_at)
        create_run_phase_metrics["create_run_profile_cache_hit"] = 1 if profile_cache_hit else 0

        normalize_messages_started_at = time.monotonic()
        recovery_messages, run_messages = self._normalize_recovery_messages(
            messages,
            user_prompt=user_prompt,
        )
        _record_create_run_phase_metric("create_run_message_prepare", normalize_messages_started_at)

        include_agent_contract = str(
            os.getenv("APPS_CODING_AGENT_INCLUDE_AGENT_CONTRACT", "1") or "1"
        ).strip().lower() in {"1", "true", "yes", "on"}
        build_contract_started_at = time.monotonic()
        selected_agent_contract: dict[str, Any] | None = None
        if include_agent_contract:
            try:
                selected_agent_contract = await build_published_app_agent_integration_contract(
                    db=self.db,
                    app=app,
                )
            except Exception as exc:
                selected_agent_contract = {
                    "error": str(exc) or "Failed to resolve selected agent contract",
                }
        _record_create_run_phase_metric("create_run_contract_build", build_contract_started_at)
        contract_message = self._build_selected_agent_contract_message(selected_agent_contract)
        if contract_message:
            include_contract_snapshot = str(
                os.getenv("APPS_CODING_AGENT_INCLUDE_CONTRACT_PROMPT_SNAPSHOT", "0") or "0"
            ).strip().lower() in {"1", "true", "yes", "on"}
            if include_contract_snapshot:
                recovery_messages.insert(0, {"role": "system", "content": contract_message})

        input_params = {
            "input": user_prompt,
            "messages": run_messages,
            "context": {
                "surface": CODING_AGENT_SURFACE,
                "app_id": str(app.id),
                "base_revision_id": str(base_revision.id),
                "entry_file": base_revision.entry_file,
                "requested_model_id": requested_model_id,
                "resolved_model_id": resolved_model_id,
                "execution_engine": normalized_engine,
                "opencode_model_id": resolved_model_id,
                "chat_session_id": str(chat_session_id) if chat_session_id else None,
                "selected_agent_contract": selected_agent_contract,
            },
        }

        start_executor_started_at = time.monotonic()
        run_id = await self.executor.start_run(
            profile.id,
            input_params,
            user_id=actor_id,
            background=False,
            mode=ExecutionMode.DEBUG,
            requested_scopes=requested_scopes,
        )
        _record_create_run_phase_metric("create_run_executor_start", start_executor_started_at)

        load_run_started_at = time.monotonic()
        run = await self.db.get(AgentRun, run_id)
        if run is None:
            self._trace(
                "runtime.create_run.missing_run_after_start",
                app_id=str(app.id),
                run_id=str(run_id),
            )
            raise RuntimeError("Failed to load created coding-agent run")
        _record_create_run_phase_metric("create_run_load_run", load_run_started_at)

        run.surface = CODING_AGENT_SURFACE
        run.published_app_id = app.id
        run.base_revision_id = base_revision.id
        run.result_revision_id = None
        run.has_workspace_writes = False
        run.batch_finalized_at = None
        run.requested_model_id = None
        run.resolved_model_id = None
        run.execution_engine = normalized_engine
        run.engine_run_ref = None
        for metric_name, metric_value in create_run_phase_metrics.items():
            self._set_timing_metric_value(run, metric=metric_name, value=metric_value)

        resolve_preview_started_at = time.monotonic()
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
            self._trace(
                "runtime.create_run.sandbox_init_failed",
                app_id=str(app.id),
                run_id=str(run.id),
                error=message,
                error_type="HTTPException",
            )
            raise
        except Exception as exc:
            run.status = RunStatus.failed
            run.error_message = str(exc)
            run.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            self._trace(
                "runtime.create_run.sandbox_init_failed",
                app_id=str(app.id),
                run_id=str(run.id),
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            raise self._engine_unsupported_runtime_error(f"Failed to initialize preview session: {exc}") from exc

        context = self._run_context(run)
        context.update({key: value for key, value in sandbox_context.items() if key != "stage_prepare_ms"})
        workspace_path = str(
            context.get("opencode_workspace_path")
            or context.get("preview_workspace_live_path")
            or ""
        ).strip()
        sandbox_id = str(
            context.get("opencode_sandbox_id")
            or context.get("preview_sandbox_id")
            or ""
        ).strip()
        chat_session = await self._load_chat_session(chat_session_id=chat_session_id)
        opencode_session_create_started_at = time.monotonic()
        if chat_session is not None and normalized_engine == CODING_AGENT_ENGINE_OPENCODE:
            existing_session_id = str(chat_session.opencode_session_id or "").strip()
            if self._session_matches_runtime(chat_session, sandbox_id=sandbox_id, workspace_path=workspace_path):
                context["opencode_session_id"] = existing_session_id
                context["opencode_sandbox_id"] = sandbox_id or None
                context["opencode_workspace_path"] = workspace_path or None
                context["opencode_recovery_messages"] = []
                self._trace(
                    "opencode.session.reused",
                    app_id=str(app.id),
                    run_id=str(run.id),
                    chat_session_id=str(chat_session.id),
                    session_id=existing_session_id,
                    sandbox_id=sandbox_id or None,
                    workspace_path=workspace_path or None,
                )
            else:
                if existing_session_id:
                    self._trace(
                        "opencode.session.invalidated",
                        app_id=str(app.id),
                        run_id=str(run.id),
                        chat_session_id=str(chat_session.id),
                        session_id=existing_session_id,
                        persisted_sandbox_id=str(chat_session.opencode_sandbox_id or "") or None,
                        current_sandbox_id=sandbox_id or None,
                        persisted_workspace_path=str(chat_session.opencode_workspace_path or "") or None,
                        current_workspace_path=workspace_path or None,
                    )
                created_session_id = await self._opencode_client.create_session(
                    run_id=str(run.id),
                    app_id=str(app.id),
                    sandbox_id=sandbox_id,
                    workspace_path=workspace_path,
                    model_id=resolved_model_id,
                    selected_agent_contract=selected_agent_contract,
                )
                chat_session.opencode_session_id = created_session_id
                chat_session.opencode_sandbox_id = sandbox_id or None
                chat_session.opencode_workspace_path = workspace_path or None
                chat_session.opencode_session_opened_at = datetime.now(timezone.utc)
                chat_session.opencode_session_closed_at = None
                context["opencode_session_id"] = created_session_id
                context["opencode_sandbox_id"] = sandbox_id or None
                context["opencode_workspace_path"] = workspace_path or None
                context["opencode_recovery_messages"] = recovery_messages if existing_session_id else []
                self._trace(
                    "opencode.session.create.confirmed",
                    app_id=str(app.id),
                    run_id=str(run.id),
                    chat_session_id=str(chat_session.id),
                    session_id=created_session_id,
                    sandbox_id=sandbox_id or None,
                    workspace_path=workspace_path or None,
                    recovered=bool(existing_session_id),
                )
                create_run_phase_metrics["create_run_opencode_session_create"] = max(
                    0,
                    int((time.monotonic() - opencode_session_create_started_at) * 1000),
                )
                self._set_timing_metric_value(
                    run,
                    metric="create_run_opencode_session_create",
                    value=create_run_phase_metrics["create_run_opencode_session_create"],
                )
                self._set_timing_metric_value(
                    run,
                    metric="opencode_session_create_ms",
                    value=create_run_phase_metrics["create_run_opencode_session_create"],
                )
        resolve_preview_ms = self._record_timing_metric(
            run,
            phase="resolve_preview_session",
            started_at=resolve_preview_started_at,
        )
        self._set_timing_metric_value(
            run,
            metric="create_run_resolve_preview_session",
            value=resolve_preview_ms,
        )
        self._set_timing_metric_value(
            run,
            metric="stage_prepare",
            value=int(sandbox_context.get("stage_prepare_ms") or 0),
        )
        create_run_ms = self._record_timing_metric(
            run,
            phase="create_run",
            started_at=create_run_started_at,
        )
        logger.info(
            "CODING_AGENT_TIMING run_id=%s app_id=%s phase=create_run duration_ms=%s resolve_preview_session_ms=%s phase_breakdown_ms=%s",
            run.id,
            app.id,
            create_run_ms,
            resolve_preview_ms,
            json.dumps(create_run_phase_metrics, sort_keys=True),
        )

        await self.db.commit()
        await self.db.refresh(run)
        self._trace(
            "runtime.create_run.started",
            app_id=str(app.id),
            run_id=str(run.id),
            chat_session_id=str(context.get("chat_session_id") or "") or None,
            sandbox_id=str(context.get("preview_sandbox_id") or "") or None,
            workspace_path=str(context.get("opencode_workspace_path") or context.get("preview_workspace_live_path") or "") or None,
            resolved_model_id=str(context.get("resolved_model_id") or "") or None,
            phase_metrics_ms=create_run_phase_metrics,
            create_run_ms=create_run_ms,
        )
        return run

    async def create_prompt_async_bookkeeping_run(
        self,
        *,
        app: PublishedApp,
        base_revision: PublishedAppRevision,
        actor_id: UUID | None,
        user_prompt: str,
        requested_model_id: str | None,
        chat_session_id: UUID,
        opencode_session_id: str,
        sandbox_id: str | None,
        workspace_path: str | None,
        message_id: str,
    ) -> AgentRun:
        requested_model_id, resolved_model_id = self._resolve_requested_opencode_model_id(requested_model_id)
        profile, _ = await self._resolve_cached_coding_agent_profile(
            organization_id=app.organization_id,
            actor_user_id=actor_id,
        )
        input_params = {
            "input": user_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "context": {
                "surface": CODING_AGENT_SURFACE,
                "published_app_id": str(app.id),
                "app_id": str(app.id),
                "base_revision_id": str(base_revision.id),
                "entry_file": base_revision.entry_file,
                "requested_model_id": requested_model_id,
                "resolved_model_id": resolved_model_id,
                "execution_engine": CODING_AGENT_ENGINE_OPENCODE,
                "chat_session_id": str(chat_session_id),
                "opencode_submission_mode": "session_prompt_async",
                "opencode_session_id": str(opencode_session_id or "").strip() or None,
                "opencode_sandbox_id": str(sandbox_id or "").strip() or None,
                "opencode_workspace_path": str(workspace_path or "").strip() or None,
                "preview_sandbox_id": str(sandbox_id or "").strip() or None,
                "preview_workspace_live_path": str(workspace_path or "").strip() or None,
                "prompt_async_message_id": str(message_id or "").strip() or None,
            },
        }
        run_id = await self.executor.start_run(
            profile.id,
            input_params,
            user_id=actor_id,
            background=False,
            mode=ExecutionMode.DEBUG,
        )
        run = await self.db.get(AgentRun, run_id)
        if run is None:
            raise RuntimeError("Failed to load created prompt-async bookkeeping run")
        run.surface = CODING_AGENT_SURFACE
        run.published_app_id = app.id
        run.base_revision_id = base_revision.id
        run.result_revision_id = None
        run.has_workspace_writes = False
        run.batch_finalized_at = None
        run.execution_engine = CODING_AGENT_ENGINE_OPENCODE
        run.requested_model_id = None
        run.resolved_model_id = None
        run.engine_run_ref = None
        await self.db.commit()
        await self.db.refresh(run)
        self._trace(
            "runtime.prompt_async_bookkeeping_run.created",
            app_id=str(app.id),
            run_id=str(run.id),
            chat_session_id=str(chat_session_id),
            base_revision_id=str(base_revision.id),
            opencode_session_id=str(opencode_session_id or "") or None,
        )
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

    async def get_active_run_for_chat_session(
        self,
        *,
        app_id: UUID,
        chat_session_id: UUID,
    ) -> AgentRun | None:
        result = await self.db.execute(
            select(AgentRun)
            .where(
                AgentRun.published_app_id == app_id,
                AgentRun.surface == CODING_AGENT_SURFACE,
            )
            .order_by(AgentRun.created_at.desc())
            .limit(200)
        )
        runs = list(result.scalars().all())
        target_chat_session_id = str(chat_session_id)
        for run in runs:
            status = run.status.value if hasattr(run.status, "value") else str(run.status)
            if status in _TERMINAL_RUN_STATUSES:
                continue
            input_params = run.input_params if isinstance(run.input_params, dict) else {}
            context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
            if str(context.get("chat_session_id") or "").strip() == target_chat_session_id:
                return run
        return None

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

    async def _clear_preview_run_lock(
        self,
        *,
        app_id: UUID | None,
        actor_id: UUID | None,
        run_id: UUID,
    ) -> None:
        _ = app_id, actor_id, run_id
        return

    async def cancel_run(self, run: AgentRun) -> AgentRun:
        status = run.status.value if hasattr(run.status, "value") else str(run.status)
        if status in {RunStatus.completed.value, RunStatus.failed.value, RunStatus.cancelled.value}:
            self._trace(
                "runtime.cancel.skipped_terminal",
                run_id=str(run.id),
                app_id=str(run.published_app_id) if run.published_app_id else None,
                status=status,
            )
            return run
        self._trace(
            "runtime.cancel.requested",
            run_id=str(run.id),
            app_id=str(run.published_app_id) if run.published_app_id else None,
            status=status,
        )
        run.status = RunStatus.cancelled
        run.error_message = None
        context = self._run_context(run)
        context["preview_sandbox_status"] = "running"
        await self._clear_preview_run_lock(
            app_id=run.published_app_id,
            actor_id=run.initiator_user_id or run.user_id,
            run_id=run.id,
        )

        run.completed_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(run)
        logger.info(
            "CODING_AGENT_CANCEL_CONFIRMED run_id=%s app_id=%s status=%s",
            run.id,
            run.published_app_id,
            run.status.value if hasattr(run.status, "value") else str(run.status),
        )
        self._trace(
            "runtime.cancel.persisted",
            run_id=str(run.id),
            app_id=str(run.published_app_id) if run.published_app_id else None,
            status=(run.status.value if hasattr(run.status, "value") else str(run.status)),
        )
        try:
            engine = self._resolve_engine_for_run(run)
            # Provider abort is best-effort and must not delay local terminalization.
            async def _best_effort_cancel() -> None:
                try:
                    await engine.cancel(run)
                    self._trace(
                        "runtime.cancel.engine_confirmed",
                        run_id=str(run.id),
                        app_id=str(run.published_app_id) if run.published_app_id else None,
                    )
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.exception("OpenCode cancellation failed for run %s: %s", run.id, exc)
                    self._trace(
                        "runtime.cancel.engine_failed",
                        run_id=str(run.id),
                        app_id=str(run.published_app_id) if run.published_app_id else None,
                        error=str(exc),
                        error_type=exc.__class__.__name__,
                    )

            asyncio.create_task(_best_effort_cancel())
        except Exception:
            pass
        return run

    async def answer_question(
        self,
        *,
        run: AgentRun,
        question_id: str,
        answers: list[list[str]],
    ) -> AgentRun:
        status = run.status.value if hasattr(run.status, "value") else str(run.status)
        if status in {RunStatus.completed.value, RunStatus.failed.value, RunStatus.cancelled.value, RunStatus.paused.value}:
            self._trace(
                "runtime.answer_question.rejected_terminal",
                run_id=str(run.id),
                app_id=str(run.published_app_id) if run.published_app_id else None,
                status=status,
            )
            raise HTTPException(status_code=409, detail="Coding-agent run is not active")
        request_id = str(question_id or "").strip()
        if not request_id:
            raise HTTPException(status_code=400, detail="question_id is required")
        normalized_answers: list[list[str]] = []
        for row in answers or []:
            if not isinstance(row, list):
                continue
            values = [str(item).strip() for item in row if str(item).strip()]
            normalized_answers.append(values)
        if not normalized_answers:
            raise HTTPException(status_code=400, detail="answers must contain at least one response")
        self._trace(
            "runtime.answer_question.requested",
            run_id=str(run.id),
            app_id=str(run.published_app_id) if run.published_app_id else None,
            question_id=request_id,
            answer_groups=len(normalized_answers),
        )
        engine = self._resolve_engine_for_run(run)
        try:
            await engine.answer_question(
                run=run,
                question_id=request_id,
                answers=normalized_answers,
            )
        except HTTPException:
            self._trace(
                "runtime.answer_question.failed",
                run_id=str(run.id),
                app_id=str(run.published_app_id) if run.published_app_id else None,
                question_id=request_id,
                error_type="HTTPException",
            )
            raise
        except Exception as exc:
            self._trace(
                "runtime.answer_question.failed",
                run_id=str(run.id),
                app_id=str(run.published_app_id) if run.published_app_id else None,
                question_id=request_id,
                error=str(exc),
                error_type=exc.__class__.__name__,
            )
            raise HTTPException(status_code=502, detail=f"Failed to answer coding-agent question: {exc}") from exc
        await self.db.refresh(run)
        self._trace(
            "runtime.answer_question.queued",
            run_id=str(run.id),
            app_id=str(run.published_app_id) if run.published_app_id else None,
            question_id=request_id,
        )
        return run

    async def list_checkpoints(self, *, app_id: UUID, limit: int = 25) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(AgentRun)
            .where(
                and_(
                    AgentRun.surface == CODING_AGENT_SURFACE,
                    AgentRun.published_app_id == app_id,
                    AgentRun.result_revision_id.is_not(None),
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
                    "checkpoint_id": str(run.result_revision_id),
                    "run_id": str(run.id),
                    "app_id": str(app_id),
                    "revision_id": str(run.result_revision_id) if run.result_revision_id else None,
                    "created_at": run.completed_at or run.created_at,
                }
            )
        return payload
