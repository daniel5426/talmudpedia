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
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionMode
from app.db.postgres.models.agents import Agent, AgentRun, RunStatus
from app.db.postgres.models.registry import ModelCapabilityType, ModelProviderType, ModelRegistry
from app.db.postgres.models.published_apps import (
    PublishedApp,
    PublishedAppDraftDevSessionStatus,
    PublishedAppRevision,
    PublishedAppRevisionBuildStatus,
    PublishedAppRevisionKind,
)
from app.services.published_app_coding_agent_profile import (
    CODING_AGENT_PROFILE_SLUG,
    ensure_coding_agent_profile,
    resolve_coding_agent_chat_model_id,
)
from app.services.published_app_coding_chat_history_service import PublishedAppCodingChatHistoryService
from app.services.published_app_coding_agent_engines.base import EngineRunContext, PublishedAppCodingAgentEngine
from app.services.published_app_coding_agent_engines.native_engine import NativePublishedAppCodingAgentEngine
from app.services.published_app_coding_agent_engines.opencode_engine import OpenCodePublishedAppCodingAgentEngine
from app.services.published_app_coding_agent_tools import CODING_AGENT_SURFACE
from app.services.published_app_draft_dev_runtime import PublishedAppDraftDevRuntimeDisabled, PublishedAppDraftDevRuntimeService
from app.services.published_app_revision_store import PublishedAppRevisionStore
from app.services.published_app_agent_integration_contract import build_published_app_agent_integration_contract
from app.services.opencode_server_client import OpenCodeServerClient
from app.api.routers.published_apps_admin_files import _filter_builder_snapshot_files, _validate_builder_project_or_raise

logger = logging.getLogger(__name__)

CODING_AGENT_ENGINE_NATIVE = "native"
CODING_AGENT_ENGINE_OPENCODE = "opencode"
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


class PublishedAppCodingAgentRuntimeService:
    _profile_cache_by_tenant: dict[str, tuple[str, float]] = {}

    def __init__(self, db: AsyncSession):
        self.db = db
        self.executor = AgentExecutorService(db=db)
        self._opencode_client = OpenCodeServerClient.from_env()
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
            "sandbox_id": str(context.get("preview_sandbox_id") or "") or None,
            "sandbox_status": str(context.get("preview_sandbox_status") or "") or None,
            "sandbox_started_at": context.get("preview_sandbox_started_at"),
            "chat_session_id": str(context.get("chat_session_id") or "") or None,
        }

    @staticmethod
    def _default_execution_engine() -> str:
        value = str(os.getenv("APPS_CODING_AGENT_DEFAULT_ENGINE", CODING_AGENT_ENGINE_OPENCODE) or "").strip().lower()
        if value == CODING_AGENT_ENGINE_NATIVE:
            return CODING_AGENT_ENGINE_NATIVE
        return CODING_AGENT_ENGINE_OPENCODE

    @staticmethod
    def _native_engine_enabled() -> bool:
        value = str(os.getenv("APPS_CODING_AGENT_NATIVE_ENABLED", "0") or "").strip().lower()
        return value in {"1", "true", "yes", "on"}

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

    async def _resolve_cached_coding_agent_profile(self, *, tenant_id: UUID) -> tuple[Agent, bool]:
        cache_ttl = self._profile_cache_ttl_seconds()
        tenant_key = str(tenant_id)
        if cache_ttl > 0:
            cache_entry = self._profile_cache_by_tenant.get(tenant_key)
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
                            and str(cached_profile.tenant_id) == tenant_key
                            and str(cached_profile.slug or "") == CODING_AGENT_PROFILE_SLUG
                            and bool(cached_profile.is_active)
                        ):
                            return cached_profile, True
                self._profile_cache_by_tenant.pop(tenant_key, None)

        profile = await ensure_coding_agent_profile(self.db, tenant_id)
        if cache_ttl > 0 and profile is not None and profile.id is not None:
            self._profile_cache_by_tenant[tenant_key] = (
                str(profile.id),
                time.monotonic() + cache_ttl,
            )
        return profile, False

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
        engine = str(value or PublishedAppCodingAgentRuntimeService._default_execution_engine()).strip().lower()
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

    @staticmethod
    def _local_telemetry_file_path() -> Path | None:
        raw = str(os.getenv("APPS_CODING_AGENT_LOCAL_TELEMETRY_FILE_PATH") or "").strip()
        disabled_values = {"0", "false", "off", "none", "disabled"}
        if raw.lower() in disabled_values:
            return None
        if raw:
            return Path(raw).expanduser()
        dev_shim_enabled = str(os.getenv("APPS_SANDBOX_CONTROLLER_DEV_SHIM_ENABLED", "0") or "").strip().lower()
        if dev_shim_enabled in {"1", "true", "yes", "on"}:
            return Path("/tmp/talmudpedia-coding-agent-telemetry.ndjson")
        return None

    def _append_local_telemetry_snapshot(
        self,
        *,
        app: PublishedApp,
        run: AgentRun,
        terminal_event: str,
        assistant_delta_events: int,
        saw_write_tool_event: bool,
        revision_created: bool,
    ) -> None:
        path = self._local_telemetry_file_path()
        if path is None:
            return
        input_params = run.input_params if isinstance(run.input_params, dict) else {}
        context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
        timing_metrics = context.get("timing_metrics_ms") if isinstance(context.get("timing_metrics_ms"), dict) else {}
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "run_id": str(run.id),
            "app_id": str(app.id),
            "engine": str(run.execution_engine or CODING_AGENT_ENGINE_NATIVE),
            "status": run.status.value if hasattr(run.status, "value") else str(run.status),
            "terminal_event": terminal_event,
            "assistant_delta_events": int(max(0, assistant_delta_events)),
            "saw_write_tool_event": bool(saw_write_tool_event),
            "revision_created": bool(revision_created),
            "error": str(run.error_message or ""),
            "timing_metrics_ms": timing_metrics,
            "started_at": run.started_at.isoformat() if isinstance(run.started_at, datetime) else None,
            "completed_at": run.completed_at.isoformat() if isinstance(run.completed_at, datetime) else None,
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, default=str, sort_keys=True))
                handle.write("\n")
        except Exception as exc:
            logger.warning("Failed to append local coding-agent telemetry snapshot path=%s error=%s", path, exc)

    @staticmethod
    def _is_workspace_write_tool_event(*, event: str, payload: dict[str, Any] | None) -> bool:
        if event not in {"tool.started", "tool.completed"}:
            return False
        tool_name = str((payload or {}).get("tool") or "").strip().lower()
        if not tool_name:
            return False
        return any(hint in tool_name for hint in _WORKSPACE_WRITE_TOOL_HINTS)

    async def _ensure_run_sandbox_context(
        self,
        *,
        run: AgentRun,
        app: PublishedApp,
        base_revision: PublishedAppRevision,
        actor_id: UUID | None,
    ) -> dict[str, Any]:
        if actor_id is None:
            raise self._engine_unsupported_runtime_error(
                "Coding-agent preview session requires a user-scoped run."
            )
        runtime_service = PublishedAppDraftDevRuntimeService(self.db)
        try:
            session = await runtime_service.ensure_active_session(
                app=app,
                revision=base_revision,
                user_id=actor_id,
            )
        except PublishedAppDraftDevRuntimeDisabled as exc:
            raise self._engine_unsupported_runtime_error(str(exc)) from exc

        status = session.status.value if hasattr(session.status, "value") else str(session.status)
        if session.status == PublishedAppDraftDevSessionStatus.error or not session.sandbox_id:
            raise self._engine_unsupported_runtime_error(
                f"Failed to initialize preview sandbox session: {session.last_error or 'unknown error'}"
            )
        sandbox_id = str(session.sandbox_id)
        stage_prepare_started_at = time.monotonic()
        stage_payload = await runtime_service.client.prepare_stage_workspace(
            sandbox_id=sandbox_id,
            run_id=str(run.id),
        )
        stage_prepare_ms = max(0, int((time.monotonic() - stage_prepare_started_at) * 1000))
        live_workspace_path = str(stage_payload.get("live_workspace_path") or "").strip()
        if not live_workspace_path:
            live_workspace_path = (
                str(await runtime_service.client.resolve_local_workspace_path(sandbox_id=sandbox_id) or "").strip()
            )
        stage_workspace_path = str(
            stage_payload.get("stage_workspace_path")
            or stage_payload.get("workspace_path")
            or live_workspace_path
            or "/workspace"
        ).strip()
        started_at = datetime.now(timezone.utc).isoformat()
        context = self._run_context(run)
        context["preview_sandbox_id"] = sandbox_id
        context["preview_sandbox_status"] = status
        context["preview_sandbox_started_at"] = started_at
        context["preview_workspace_live_path"] = live_workspace_path or "/workspace"
        context["preview_workspace_stage_path"] = stage_workspace_path
        return {
            "preview_sandbox_id": sandbox_id,
            "preview_sandbox_status": status,
            "preview_sandbox_started_at": started_at,
            "preview_workspace_live_path": live_workspace_path or "/workspace",
            "preview_workspace_stage_path": stage_workspace_path,
            "opencode_sandbox_id": sandbox_id,
            "opencode_workspace_path": stage_workspace_path,
            "stage_prepare_ms": stage_prepare_ms,
        }

    async def _recover_or_bootstrap_run_sandbox_context(
        self,
        *,
        run: AgentRun,
        app: PublishedApp,
    ) -> tuple[str | None, str | None]:
        context = self._run_context(run)
        sandbox_id = str(context.get("preview_sandbox_id") or "").strip()
        if sandbox_id:
            changed = False
            if not str(context.get("opencode_sandbox_id") or "").strip():
                context["opencode_sandbox_id"] = sandbox_id
                changed = True
            stage_workspace_path = str(context.get("preview_workspace_stage_path") or "").strip()
            if stage_workspace_path and not str(context.get("opencode_workspace_path") or "").strip():
                context["opencode_workspace_path"] = stage_workspace_path
                changed = True
            if changed:
                await self.db.commit()
            return sandbox_id, None

        base_revision_id = run.base_revision_id or app.current_draft_revision_id
        if base_revision_id is None:
            return None, "Preview sandbox session is required before execution (base revision missing)."
        base_revision = await self.db.get(PublishedAppRevision, base_revision_id)
        if base_revision is None:
            return None, "Preview sandbox session is required before execution (base revision not found)."

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
            message = str(detail.get("message") or exc.detail or "preview bootstrap failed")
            return None, f"Preview sandbox session is required before execution ({message})."
        except Exception as exc:
            return None, f"Preview sandbox session is required before execution ({exc})."

        await self.db.commit()
        sandbox_id = str(context.get("preview_sandbox_id") or "").strip()
        if sandbox_id:
            return sandbox_id, None
        return None, "Preview sandbox session is required before execution."

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
        execution_engine: str | None = None,
        chat_session_id: UUID | None = None,
    ) -> AgentRun:
        create_run_started_at = time.monotonic()
        create_run_phase_metrics: dict[str, int] = {}

        def _record_create_run_phase_metric(phase: str, started_at: float) -> int:
            duration_ms = max(0, int((time.monotonic() - started_at) * 1000))
            create_run_phase_metrics[str(phase)] = duration_ms
            return duration_ms

        normalized_engine = self._normalize_execution_engine(execution_engine)
        if normalized_engine == CODING_AGENT_ENGINE_NATIVE and not self._native_engine_enabled():
            raise self._engine_unavailable_error(
                "Native engine is disabled by policy. Set APPS_CODING_AGENT_NATIVE_ENABLED=1 to enable it."
            )
        opencode_health_task: asyncio.Task[int] | None = None
        if normalized_engine == CODING_AGENT_ENGINE_OPENCODE:
            async def _probe_opencode_health() -> int:
                probe_started_at = time.monotonic()
                await self._opencode_client.ensure_healthy()
                return max(0, int((time.monotonic() - probe_started_at) * 1000))
            opencode_health_task = asyncio.create_task(_probe_opencode_health())

        resolve_model_started_at = time.monotonic()
        requested_model_id, resolved_model_id = await self._resolve_run_model_ids(
            tenant_id=app.tenant_id,
            requested_model_id=requested_model_id,
        )
        _record_create_run_phase_metric("create_run_model_resolve", resolve_model_started_at)
        create_run_phase_metrics["create_run_opencode_health"] = 0
        create_run_phase_metrics["create_run_opencode_model_resolve"] = 0
        opencode_model_id: str | None = None
        if normalized_engine == CODING_AGENT_ENGINE_OPENCODE:
            opencode_model_started_at = time.monotonic()
            opencode_model_id = await self._resolve_opencode_model_id(
                tenant_id=app.tenant_id,
                resolved_model_id=resolved_model_id,
            )
            _record_create_run_phase_metric("create_run_opencode_model_resolve", opencode_model_started_at)
        ensure_profile_started_at = time.monotonic()
        profile, profile_cache_hit = await self._resolve_cached_coding_agent_profile(tenant_id=app.tenant_id)
        _record_create_run_phase_metric("create_run_profile_resolve", ensure_profile_started_at)
        create_run_phase_metrics["create_run_profile_cache_hit"] = 1 if profile_cache_hit else 0

        normalize_messages_started_at = time.monotonic()
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
                normalized_messages.insert(0, {"role": "system", "content": contract_message})

        if opencode_health_task is not None:
            try:
                opencode_health_ms = await opencode_health_task
            except Exception as exc:
                raise self._engine_unavailable_error(f"OpenCode engine is unavailable: {exc}") from exc
            create_run_phase_metrics["create_run_opencode_health"] = int(max(0, opencode_health_ms))

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
            raise RuntimeError("Failed to load created coding-agent run")
        _record_create_run_phase_metric("create_run_load_run", load_run_started_at)

        run.surface = CODING_AGENT_SURFACE
        run.published_app_id = app.id
        run.base_revision_id = base_revision.id
        run.result_revision_id = None
        run.checkpoint_revision_id = None
        run.requested_model_id = requested_model_id
        run.resolved_model_id = resolved_model_id
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
            raise
        except Exception as exc:
            run.status = RunStatus.failed
            run.error_message = str(exc)
            run.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            raise self._engine_unsupported_runtime_error(f"Failed to initialize preview session: {exc}") from exc

        context = self._run_context(run)
        context.update({key: value for key, value in sandbox_context.items() if key != "stage_prepare_ms"})
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

    async def _clear_preview_run_lock(
        self,
        *,
        app_id: UUID | None,
        actor_id: UUID | None,
        run_id: UUID,
    ) -> None:
        if app_id is None or actor_id is None:
            return
        runtime_service = PublishedAppDraftDevRuntimeService(self.db)
        try:
            session = await runtime_service.get_session(app_id=app_id, user_id=actor_id)
        except Exception:
            return
        if session is None or session.active_coding_run_id is None:
            return
        if str(session.active_coding_run_id) != str(run_id):
            return
        session.active_coding_run_id = None
        session.active_coding_run_locked_at = None
        session.active_coding_run_client_message_id = None

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
        revision_store = PublishedAppRevisionStore(self.db)
        checkpoint_files = await revision_store.materialize_revision_files(checkpoint_revision)

        restored = await self._create_draft_revision_from_files(
            app=app,
            current=current_revision,
            actor_id=actor_id,
            files=checkpoint_files,
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
        revision_store = PublishedAppRevisionStore(self.db)
        manifest_json, bundle_hash = await revision_store.build_manifest_and_store_blobs(sanitized_files)
        revision = PublishedAppRevision(
            published_app_id=app.id,
            kind=PublishedAppRevisionKind.draft,
            template_key=app.template_key,
            entry_file=entry_file,
            files=sanitized_files,
            manifest_json=manifest_json,
            build_status=PublishedAppRevisionBuildStatus.queued,
            build_seq=int(current.build_seq or 0) + 1,
            build_error=None,
            build_started_at=None,
            build_finished_at=None,
            dist_storage_prefix=None,
            dist_manifest=None,
            template_runtime="vite_static",
            compiled_bundle=None,
            bundle_hash=bundle_hash,
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
        preview_sandbox_id = str(context.get("preview_sandbox_id") or "").strip()
        run_scope_id = str(run.id)

        if not preview_sandbox_id:
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
            preview_sandbox_id = str(session.sandbox_id)

        try:
            snapshot = await runtime_service.client.snapshot_workspace(
                sandbox_id=preview_sandbox_id,
                workspace="stage",
                run_id=run_scope_id,
            )
        except Exception:
            await runtime_service.client.prepare_stage_workspace(
                sandbox_id=preview_sandbox_id,
                run_id=run_scope_id,
            )
            snapshot = await runtime_service.client.snapshot_workspace(
                sandbox_id=preview_sandbox_id,
                workspace="stage",
                run_id=run_scope_id,
            )

        raw_files = snapshot.get("files")
        if not isinstance(raw_files, dict):
            return None
        files = _filter_builder_snapshot_files(raw_files)
        current_files = dict(current.files or {})
        if files == current_files:
            run.result_revision_id = None
            run.checkpoint_revision_id = None
            await self.db.commit()
            return None

        promote_started_at = time.monotonic()
        await runtime_service.client.promote_stage_workspace(
            sandbox_id=preview_sandbox_id,
            run_id=run_scope_id,
        )
        self._set_timing_metric_value(
            run,
            metric="promote_live",
            value=max(0, int((time.monotonic() - promote_started_at) * 1000)),
        )
        live_snapshot = await runtime_service.client.snapshot_workspace(
            sandbox_id=preview_sandbox_id,
            workspace="live",
            run_id=run_scope_id,
        )
        live_raw_files = live_snapshot.get("files")
        if not isinstance(live_raw_files, dict):
            raise RuntimeError("Preview live workspace snapshot did not return files after stage promotion")
        live_files = _filter_builder_snapshot_files(live_raw_files)

        revision = await self._create_draft_revision_from_files(
            app=app,
            current=current,
            actor_id=actor_id,
            files=live_files,
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
                    files=live_files,
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

    @staticmethod
    def _stream_guardrail_seconds() -> tuple[float, float]:
        inactivity_raw = (os.getenv("APPS_CODING_AGENT_STREAM_INACTIVITY_TIMEOUT_SECONDS") or "75").strip()
        max_duration_raw = (os.getenv("APPS_CODING_AGENT_STREAM_MAX_DURATION_SECONDS") or "300").strip()
        try:
            inactivity_timeout = float(inactivity_raw)
        except Exception:
            inactivity_timeout = 75.0
        try:
            max_duration = float(max_duration_raw)
        except Exception:
            max_duration = 300.0
        inactivity_timeout = max(10.0, inactivity_timeout)
        max_duration = max(inactivity_timeout + 5.0, max_duration)
        return inactivity_timeout, max_duration

    @staticmethod
    def _extract_chat_session_id(run: AgentRun) -> UUID | None:
        input_params = run.input_params if isinstance(run.input_params, dict) else {}
        context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
        raw = str(context.get("chat_session_id") or "").strip()
        if not raw:
            return None
        try:
            return UUID(raw)
        except Exception:
            return None

    async def _persist_assistant_chat_message_if_needed(
        self,
        *,
        run: AgentRun,
        assistant_text: str,
    ) -> None:
        session_id = self._extract_chat_session_id(run)
        if session_id is None:
            return
        text = str(assistant_text or "").strip()
        if not text:
            return
        history_service = PublishedAppCodingChatHistoryService(self.db)
        await history_service.persist_assistant_message(
            session_id=session_id,
            run_id=run.id,
            content=text,
        )

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
        assistant_chunks: list[str] = []
        assistant_message_persisted = False
        first_token_recorded = False
        stream_started_at = time.monotonic()
        saw_write_tool_event = False
        assistant_delta_events = 0

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

        async def persist_assistant_message_for_terminal(default_text: str | None = None) -> None:
            nonlocal assistant_message_persisted
            if assistant_message_persisted:
                return
            text = "".join(assistant_chunks).strip()
            if not text:
                text = str(default_text or "").strip()
            if not text:
                text = self._extract_assistant_text_from_output(run.output_result) or self._fallback_assistant_text(run)
            if not text:
                return
            await self._persist_assistant_chat_message_if_needed(run=run, assistant_text=text)
            assistant_message_persisted = True

        async def finalize_sandbox(reason: str) -> None:
            _ = reason
            context = self._run_context(run)
            context["preview_sandbox_status"] = "running"

        async def release_run_lock() -> None:
            await self._clear_preview_run_lock(
                app_id=run.published_app_id,
                actor_id=run.initiator_user_id or run.user_id,
                run_id=run.id,
            )
            await self.db.commit()

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
                await finalize_sandbox("stopped")
                assistant_text = self._extract_assistant_text_from_output(run.output_result) or self._fallback_assistant_text(run)
                assistant_chunks.append(assistant_text)
                yield emit("assistant.delta", "assistant", {"content": assistant_text})
                await persist_assistant_message_for_terminal(assistant_text)
                self._append_local_telemetry_snapshot(
                    app=app,
                    run=run,
                    terminal_event="run.completed",
                    assistant_delta_events=1 if assistant_text else 0,
                    saw_write_tool_event=False,
                    revision_created=bool(run.result_revision_id),
                )
                await release_run_lock()
                yield emit("run.completed", "run", self.serialize_run(run))
            else:
                await finalize_sandbox("error")
                await persist_assistant_message_for_terminal(run.error_message or f"run {terminal_status}")
                self._append_local_telemetry_snapshot(
                    app=app,
                    run=run,
                    terminal_event="run.failed",
                    assistant_delta_events=0,
                    saw_write_tool_event=False,
                    revision_created=bool(run.result_revision_id),
                )
                yield emit(
                    "run.failed",
                    "run",
                    self.serialize_run(run),
                    [{"message": run.error_message or f"run {terminal_status}"}],
                )
                await release_run_lock()
            return

        run_context = self._run_context(run)
        sandbox_id = str(run_context.get("preview_sandbox_id") or "").strip()
        if not sandbox_id:
            sandbox_id, sandbox_error = await self._recover_or_bootstrap_run_sandbox_context(run=run, app=app)
        else:
            sandbox_error = None
        if not sandbox_id:
            run.status = RunStatus.failed
            run.error_message = sandbox_error or "Preview sandbox session is required before execution."
            run.completed_at = datetime.now(timezone.utc)
            await release_run_lock()
            await self.db.commit()
            await persist_assistant_message_for_terminal(run.error_message)
            yield emit(
                "run.failed",
                "run",
                self.serialize_run(run),
                [{"code": "CODING_AGENT_SANDBOX_REQUIRED", "message": run.error_message}],
            )
            return

        try:
            engine = self._resolve_engine_for_run(run)
            inactivity_timeout_s, max_stream_duration_s = self._stream_guardrail_seconds()
            stream_deadline = time.monotonic() + max_stream_duration_s
            engine_iter = engine.stream(
                EngineRunContext(
                    app=app,
                    run=run,
                    resume_payload=resume_payload,
                )
            ).__aiter__()
            terminal_engine_event: str | None = None
            terminal_engine_payload: dict[str, Any] = {}
            terminal_engine_diagnostics: list[dict[str, Any]] | None = None
            try:
                while True:
                    remaining = stream_deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(
                            f"Coding-agent stream exceeded max duration ({int(max_stream_duration_s)}s) without terminal event."
                        )
                    next_timeout = min(inactivity_timeout_s, remaining)
                    try:
                        raw_event = await asyncio.wait_for(engine_iter.__anext__(), timeout=next_timeout)
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError as exc:
                        raise TimeoutError(
                            f"Coding-agent stream stalled for {int(next_timeout)}s without provider progress."
                        ) from exc
                    mapped_event = raw_event.event
                    stage = raw_event.stage
                    payload = raw_event.payload
                    diagnostics = raw_event.diagnostics
                    if mapped_event in {"run.completed", "run.failed"}:
                        terminal_engine_event = mapped_event
                        terminal_engine_payload = payload if isinstance(payload, dict) else {}
                        terminal_engine_diagnostics = diagnostics
                        break
                    if self._is_workspace_write_tool_event(event=mapped_event, payload=payload):
                        saw_write_tool_event = True
                    if mapped_event == "assistant.delta":
                        raw_content = str((payload or {}).get("content") or "")
                        if raw_content.strip():
                            assistant_delta_events += 1
                            assistant_delta_emitted = True
                            assistant_chunks.append(raw_content)
                            if not first_token_recorded:
                                first_token_recorded = True
                                first_token_ms = self._record_timing_metric(
                                    run,
                                    phase="first_token",
                                    started_at=stream_started_at,
                                )
                                logger.info(
                                    "CODING_AGENT_TIMING run_id=%s app_id=%s phase=first_token duration_ms=%s",
                                    run.id,
                                    app.id,
                                    first_token_ms,
                                )
                                await self.db.commit()
                    yield emit(mapped_event, stage, payload, diagnostics)
            finally:
                aclose = getattr(engine_iter, "aclose", None)
                if callable(aclose):
                    try:
                        await aclose()
                    except Exception:
                        pass

            run = await self.db.get(AgentRun, run_id) or run
            status = run.status.value if hasattr(run.status, "value") else str(run.status)
            if terminal_engine_event in {"run.completed", "run.failed"} and status not in {
                RunStatus.completed.value,
                RunStatus.failed.value,
                RunStatus.cancelled.value,
            }:
                if terminal_engine_event == "run.completed":
                    run.status = RunStatus.completed
                    run.error_message = None
                else:
                    failure_message = str(
                        (terminal_engine_diagnostics or [{}])[0].get("message")
                        or terminal_engine_payload.get("error")
                        or "run failed"
                    )
                    run.status = RunStatus.failed
                    run.error_message = failure_message
                run.completed_at = run.completed_at or datetime.now(timezone.utc)
                await self.db.commit()
                status = run.status.value if hasattr(run.status, "value") else str(run.status)
            if status == RunStatus.completed.value:
                terminal_event_ms = self._record_timing_metric(
                    run,
                    phase="terminal_event",
                    started_at=stream_started_at,
                )
                logger.info(
                    "CODING_AGENT_TIMING run_id=%s app_id=%s phase=terminal_event duration_ms=%s",
                    run.id,
                    app.id,
                    terminal_event_ms,
                )
                checkpoint_started_at = time.monotonic()
                if saw_write_tool_event:
                    revision = await self.auto_apply_and_checkpoint(run)
                    self._set_timing_metric_value(run, metric="checkpoint_skipped_no_edit_tool", value=False)
                else:
                    revision = None
                    self._set_timing_metric_value(run, metric="checkpoint_skipped_no_edit_tool", value=True)
                checkpoint_done_ms = self._record_timing_metric(
                    run,
                    phase="revision_persist",
                    started_at=checkpoint_started_at,
                )
                self._set_timing_metric_value(
                    run,
                    metric="opencode_delta_events",
                    value=assistant_delta_events,
                )
                logger.info(
                    "CODING_AGENT_TIMING run_id=%s app_id=%s phase=revision_persist duration_ms=%s",
                    run.id,
                    app.id,
                    checkpoint_done_ms,
                )
                await finalize_sandbox("stopped")
                await self.db.commit()
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
                    assistant_chunks.append(assistant_text)
                    yield emit("assistant.delta", "assistant", {"content": assistant_text})
                await persist_assistant_message_for_terminal()
                self._append_local_telemetry_snapshot(
                    app=app,
                    run=run,
                    terminal_event="run.completed",
                    assistant_delta_events=assistant_delta_events,
                    saw_write_tool_event=saw_write_tool_event,
                    revision_created=revision is not None,
                )
                await release_run_lock()
                yield emit("run.completed", "run", self.serialize_run(run))
                return

            if status == RunStatus.cancelled.value:
                await finalize_sandbox("stopped")
                await persist_assistant_message_for_terminal("Run cancelled.")
                self._append_local_telemetry_snapshot(
                    app=app,
                    run=run,
                    terminal_event="run.failed",
                    assistant_delta_events=assistant_delta_events,
                    saw_write_tool_event=saw_write_tool_event,
                    revision_created=bool(run.result_revision_id),
                )
                yield emit(
                    "run.failed",
                    "run",
                    self.serialize_run(run),
                    [{"message": "run cancelled"}],
                )
                await release_run_lock()
                return

            if status == RunStatus.paused.value:
                await finalize_sandbox("stopped")
                await persist_assistant_message_for_terminal("Run paused.")
                self._append_local_telemetry_snapshot(
                    app=app,
                    run=run,
                    terminal_event="run.completed",
                    assistant_delta_events=assistant_delta_events,
                    saw_write_tool_event=saw_write_tool_event,
                    revision_created=bool(run.result_revision_id),
                )
                await release_run_lock()
                yield emit("run.completed", "run", self.serialize_run(run))
                return

            await finalize_sandbox("error")
            await persist_assistant_message_for_terminal(run.error_message or "run failed")
            self._append_local_telemetry_snapshot(
                app=app,
                run=run,
                terminal_event="run.failed",
                assistant_delta_events=assistant_delta_events,
                saw_write_tool_event=saw_write_tool_event,
                revision_created=bool(run.result_revision_id),
            )
            yield emit(
                "run.failed",
                "run",
                self.serialize_run(run),
                [{"message": run.error_message or "run failed"}],
            )
            await release_run_lock()
        except Exception as exc:
            failed_run = await self.db.get(AgentRun, run_id)
            if failed_run is not None:
                failed_run.status = RunStatus.failed
                failed_run.error_message = str(exc)
                failed_run.completed_at = datetime.now(timezone.utc)
                context = self._run_context(failed_run)
                context["preview_sandbox_status"] = "running"
                await release_run_lock()
                await self.db.commit()
                run = failed_run
            await persist_assistant_message_for_terminal(str(exc))
            self._append_local_telemetry_snapshot(
                app=app,
                run=run,
                terminal_event="run.failed",
                assistant_delta_events=assistant_delta_events,
                saw_write_tool_event=saw_write_tool_event,
                revision_created=bool(run.result_revision_id),
            )
            yield emit(
                "run.failed",
                "run",
                self.serialize_run(run),
                [{"message": str(exc)}],
            )
