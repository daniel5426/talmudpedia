import logging
import asyncio
import inspect
import traceback
from contextlib import suppress
from uuid import UUID, uuid4
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, AsyncGenerator, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.postgres.models.agents import Agent, AgentRun, RunStatus
from app.agent.graph.compiler import AgentCompiler
from app.agent.graph.schema import AgentGraph
from app.agent.runtime.registry import RuntimeAdapterRegistry
from app.agent.runtime.base import RuntimeState
from app.agent.execution.types import ExecutionEvent, EventVisibility, ExecutionMode
from app.agent.execution.durable_checkpointer import DurableMemorySaver
from app.agent.execution.chat_response_blocks import (
    build_response_blocks_from_trace_events,
    extract_assistant_text_from_blocks,
)
from app.agent.execution.output_projection import extract_assistant_output_text
from app.agent.execution.run_task_registry import (
    is_run_cancel_requested,
    record_run_lineage,
    register_run_task,
    unregister_run_task,
)
from app.agent.cel_engine import evaluate_template
from app.agent.execution.trace_recorder import ExecutionTraceRecorder
from app.db.postgres.models.agent_threads import AgentThreadSurface, AgentThreadTurnStatus
from app.services.prompt_reference_resolver import PromptReferenceResolver
from app.services.runtime_attachment_service import RuntimeAttachmentOwner, RuntimeAttachmentService
from app.services.runtime_input_preparation_service import RuntimeInputPreparationService
from app.services.speech_to_text_service import SpeechToTextService
from app.services.thread_service import ThreadAccessError, ThreadService
from app.services.usage_quota_service import UsageQuotaService
from app.services.resource_policy_quota_service import ResourcePolicyQuotaExceeded, ResourcePolicyQuotaService
from app.services.resource_policy_service import (
    ResourcePolicyAccessDenied,
    ResourcePolicySnapshot,
    ResourcePolicyService,
)
from app.services.model_accounting import (
    COST_SOURCE_UNKNOWN,
    EXACT_USAGE_SOURCES,
    USAGE_SOURCE_EXACT,
    USAGE_SOURCE_ESTIMATED,
    USAGE_SOURCE_UNKNOWN,
    NormalizedUsage,
    billable_total_tokens,
    binding_pricing_snapshot,
    build_usage_from_total,
    compute_cost_from_snapshot,
    usage_payload_from_run,
)
from app.services.context_window_service import ContextWindowService
from app.services.model_resolver import (
    ModelResolver,
    ModelResolverError,
    ResolvedModelBindingReceipt,
    ResolvedModelExecution,
)
from app.services.run_invocation_service import RunInvocationService
from app.services.architect_mode_service import (
    ArchitectModeError,
    ArchitectModeService,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RequestedModelTarget:
    logical_model_id: UUID | None
    ref: str | None


@dataclass(frozen=True)
class SyncRunExecutionResult:
    run_id: UUID
    status: str
    output_result: dict[str, Any]
    error_message: str | None


class AgentExecutorService:
    _checkpointer = DurableMemorySaver()
    _WORKER_LEASE_SECONDS = 30
    _WORKER_HEARTBEAT_SECONDS = 5

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        # Initial compiler for non-execution tasks if needed, 
        # but _execute will create its own local compiler.
        self.compiler = AgentCompiler(db=db) if db else None
        self.trace_recorder = ExecutionTraceRecorder(serializer=self._serialize_state)

    @staticmethod
    async def _rollback_quietly(db: AsyncSession) -> None:
        try:
            await asyncio.shield(db.rollback())
        except Exception:
            logger.debug("Best-effort session rollback failed", exc_info=True)

    @staticmethod
    async def _drain_task(task: asyncio.Task[Any] | None) -> None:
        if task is None:
            return
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.shield(task)

    @staticmethod
    def _apply_run_scoped_model_override(
        graph_definition: dict[str, Any],
        resolved_model_id: str | None,
    ) -> dict[str, Any]:
        if not resolved_model_id:
            return graph_definition

        nodes = graph_definition.get("nodes")
        if not isinstance(nodes, list):
            return graph_definition

        patched_nodes: list[Any] = []
        for raw_node in nodes:
            if not isinstance(raw_node, dict):
                patched_nodes.append(raw_node)
                continue
            node = dict(raw_node)
            node_type = str(node.get("type") or "").strip().lower()
            config = node.get("config")
            if node_type in {"agent", "classify"} and isinstance(config, dict):
                config = dict(config)
                if "model_id" in config:
                    config["model_id"] = resolved_model_id
                node["config"] = config
            patched_nodes.append(node)

        patched = dict(graph_definition)
        patched["nodes"] = patched_nodes
        return patched

    @staticmethod
    def _safe_policy_snapshot_from_context(runtime_context: dict[str, Any] | None) -> ResourcePolicySnapshot | None:
        try:
            snapshot = ResourcePolicySnapshot.from_payload((runtime_context or {}).get("resource_policy_snapshot"))
        except Exception:
            logger.warning("Ignoring malformed resource_policy_snapshot payload", exc_info=True)
            return None
        if snapshot is None:
            return None
        if snapshot.direct_policy_set_id is None and not snapshot.source_policy_set_ids:
            return None
        return snapshot

    @staticmethod
    def _collect_graph_model_ids(graph_definition: dict[str, Any]) -> list[str]:
        nodes = graph_definition.get("nodes")
        if not isinstance(nodes, list):
            return []
        model_ids: list[str] = []
        for raw_node in nodes:
            if not isinstance(raw_node, dict):
                continue
            node_type = str(raw_node.get("type") or "").strip().lower()
            if node_type not in {"agent", "classify"}:
                continue
            config = raw_node.get("config")
            if not isinstance(config, dict):
                continue
            model_id = str(config.get("model_id") or "").strip()
            if model_id:
                model_ids.append(model_id)
        return model_ids

    @staticmethod
    def _workflow_modality_flags(graph_definition: dict[str, Any]) -> dict[str, bool]:
        try:
            graph = AgentGraph.model_validate(graph_definition or {"nodes": [], "edges": []})
        except Exception:
            return {"text": True, "files": True, "audio": True, "images": True}

        flags = {"text": True, "files": True, "audio": True, "images": True}
        workflow_contract = getattr(graph, "workflow_contract", None)
        items = getattr(workflow_contract, "inputs", []) if workflow_contract is not None else []
        for item in items or []:
            key = str(getattr(item, "key", "") or "").strip()
            if key in flags:
                flags[key] = bool(getattr(item, "enabled", True))
        return flags

    @classmethod
    def _assert_workflow_inputs_allowed(
        cls,
        *,
        graph_definition: dict[str, Any],
        workflow_input: dict[str, Any],
    ) -> None:
        flags = cls._workflow_modality_flags(graph_definition)
        normalized_text = str(workflow_input.get("text") or workflow_input.get("input_as_text") or "").strip()
        if normalized_text and not flags["text"]:
            raise ValueError("This workflow does not allow text input")

        modality_values = {
            "files": workflow_input.get("files"),
            "audio": workflow_input.get("audio"),
            "images": workflow_input.get("images"),
        }
        for key, value in modality_values.items():
            if flags[key]:
                continue
            if isinstance(value, list) and value:
                raise ValueError(f"This workflow does not allow {key} input")
            if isinstance(value, dict) and value:
                raise ValueError(f"This workflow does not allow {key} input")

    @staticmethod
    def _resolve_requested_model_id(
        runtime_context: dict[str, Any],
        graph_definition: dict[str, Any],
    ) -> UUID | None:
        return AgentExecutorService._resolve_requested_model_target(runtime_context, graph_definition).logical_model_id

    @staticmethod
    def _resolve_requested_model_ref(
        runtime_context: dict[str, Any],
        graph_definition: dict[str, Any],
    ) -> str | None:
        return AgentExecutorService._resolve_requested_model_target(runtime_context, graph_definition).ref

    @staticmethod
    def _resolve_requested_model_target(
        runtime_context: dict[str, Any],
        graph_definition: dict[str, Any],
    ) -> RequestedModelTarget:
        raw_requested_model_id = str(runtime_context.get("requested_model_id") or "").strip()
        model_ref = raw_requested_model_id or None
        if not model_ref:
            model_ids = sorted({model_id for model_id in AgentExecutorService._collect_graph_model_ids(graph_definition or {}) if model_id})
            if len(model_ids) == 1:
                model_ref = model_ids[0]
        if not model_ref:
            return RequestedModelTarget(logical_model_id=None, ref=None)
        try:
            logical_model_id = UUID(model_ref)
        except Exception:
            logical_model_id = None
        return RequestedModelTarget(logical_model_id=logical_model_id, ref=model_ref)

    @staticmethod
    def _merge_quota_caps(*caps: Any) -> int | None:
        parsed_caps: list[int] = []
        for cap in caps:
            try:
                if cap is not None:
                    parsed = int(cap)
                    if parsed > 0:
                        parsed_caps.append(parsed)
            except Exception:
                continue
        return min(parsed_caps) if parsed_caps else None

    @staticmethod
    def _is_platform_architect(agent: Agent) -> bool:
        return str(getattr(agent, "slug", "") or "").strip() == "platform-architect"

    @staticmethod
    def _extract_usage_candidate(event: ExecutionEvent) -> tuple[NormalizedUsage | None, str | None]:
        payload = event.data if isinstance(event.data, dict) else {}
        usage = payload.get("usage")
        usage_source = payload.get("usage_source")
        nested_output = payload.get("output") if isinstance(payload.get("output"), dict) else None
        if not isinstance(usage, dict) and isinstance(nested_output, dict):
            nested_usage = nested_output.get("usage")
            if isinstance(nested_usage, dict):
                usage = nested_usage
            if usage_source is None:
                usage_source = nested_output.get("usage_source")
        if not isinstance(usage, dict):
            usage = payload if any(key in payload for key in ("input_tokens", "output_tokens", "total_tokens", "usage_tokens")) else None
        if not isinstance(usage, dict):
            return None, None

        normalized = NormalizedUsage(
            input_tokens=AgentExecutorService._maybe_int(usage.get("input_tokens") or usage.get("prompt_tokens")),
            output_tokens=AgentExecutorService._maybe_int(usage.get("output_tokens") or usage.get("completion_tokens")),
            total_tokens=AgentExecutorService._maybe_int(
                usage.get("total_tokens") or usage.get("usage_tokens") or usage.get("tokens")
            ),
            cached_input_tokens=AgentExecutorService._maybe_int(usage.get("cached_input_tokens") or usage.get("cache_read_input_tokens")),
            cached_output_tokens=AgentExecutorService._maybe_int(usage.get("cached_output_tokens")),
            reasoning_tokens=AgentExecutorService._maybe_int(usage.get("reasoning_tokens")),
            audio_input_tokens=AgentExecutorService._maybe_int(usage.get("audio_input_tokens")),
            audio_output_tokens=AgentExecutorService._maybe_int(usage.get("audio_output_tokens")),
            image_input_units=AgentExecutorService._maybe_int(usage.get("image_input_units")),
            image_output_units=AgentExecutorService._maybe_int(usage.get("image_output_units")),
            extra={
                key: value
                for key, value in usage.items()
                if key
                not in {
                    "input_tokens",
                    "prompt_tokens",
                    "output_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "usage_tokens",
                    "tokens",
                    "cached_input_tokens",
                    "cache_read_input_tokens",
                    "cached_output_tokens",
                    "reasoning_tokens",
                    "audio_input_tokens",
                    "audio_output_tokens",
                    "image_input_units",
                    "image_output_units",
                }
            },
        ).finalize()
        if not normalized.to_json():
            return None, None
        source = str(usage_source or "").strip().lower() or None
        if source in EXACT_USAGE_SOURCES:
            return normalized, USAGE_SOURCE_EXACT
        if source == USAGE_SOURCE_ESTIMATED:
            return normalized, USAGE_SOURCE_ESTIMATED
        if normalized.input_tokens is not None or normalized.output_tokens is not None:
            return normalized, USAGE_SOURCE_EXACT
        if normalized.total_tokens is not None:
            return normalized, USAGE_SOURCE_ESTIMATED
        return normalized, None

    @staticmethod
    def _extract_invocation_payload(event: ExecutionEvent) -> dict[str, Any] | None:
        payload = event.data if isinstance(event.data, dict) else {}
        output = payload.get("output") if isinstance(payload.get("output"), dict) else None
        invocation = output.get("invocation") if isinstance(output, dict) and isinstance(output.get("invocation"), dict) else None
        return dict(invocation) if isinstance(invocation, dict) else None

    @staticmethod
    def _maybe_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _serialize_run_usage_event(run: AgentRun) -> dict[str, Any]:
        return usage_payload_from_run(run) or {
            "source": USAGE_SOURCE_UNKNOWN,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": 0,
        }

    @staticmethod
    def _select_better_usage(
        current_usage: NormalizedUsage | None,
        current_source: str | None,
        candidate_usage: NormalizedUsage | None,
        candidate_source: str | None,
    ) -> tuple[NormalizedUsage | None, str | None]:
        if candidate_usage is None:
            return current_usage, current_source
        if current_usage is None:
            return candidate_usage, candidate_source
        priority = {
            USAGE_SOURCE_EXACT: 4,
            USAGE_SOURCE_ESTIMATED: 2,
            USAGE_SOURCE_UNKNOWN: 1,
            None: 0,
        }
        current_score = priority.get(current_source, 0)
        candidate_score = priority.get(candidate_source, 0)
        if candidate_score > current_score:
            return candidate_usage, candidate_source
        if candidate_score == current_score and len(candidate_usage.to_json()) > len(current_usage.to_json()):
            return candidate_usage, candidate_source
        return current_usage, current_source

    async def _resolve_run_model_receipt(
        self,
        *,
        db: AsyncSession,
        run: AgentRun,
        agent: Agent,
        runtime_context: dict[str, Any],
    ) -> ResolvedModelBindingReceipt | None:
        raw_requested_model_id = (
            runtime_context.get("requested_model_id")
            or (str(run.requested_model_id) if run.requested_model_id else None)
        )
        if not raw_requested_model_id:
            model_ids = self._collect_graph_model_ids(agent.graph_definition or {})
            if len(set(model_ids)) == 1:
                raw_requested_model_id = model_ids[0]
        if not raw_requested_model_id:
            return None

        try:
            policy_snapshot = self._safe_policy_snapshot_from_context(runtime_context)
            execution = await ModelResolver(db, agent.tenant_id).resolve_receipt(
                str(raw_requested_model_id),
                policy_snapshot=policy_snapshot,
            )
        except ModelResolverError:
            logger.warning("Failed to resolve accounting receipt for run %s", run.id, exc_info=True)
            return None

        run.requested_model_id = execution.logical_model.id
        run.resolved_model_id = execution.logical_model.id
        run.resolved_binding_id = execution.binding.id
        run.resolved_provider = execution.resolved_provider
        run.resolved_provider_model_id = execution.binding.provider_model_id
        return execution

    async def _finalize_run_accounting(
        self,
        *,
        run: AgentRun,
        resolved_execution: ResolvedModelExecution | None,
        observed_usage: NormalizedUsage | None,
        observed_usage_source: str | None,
        input_params: dict[str, Any],
        output_result: dict[str, Any] | None,
    ) -> None:
        invocation_service = RunInvocationService(self.db)
        usage_payload, context_window = await invocation_service.recompute_run_aggregates(run)
        usage = NormalizedUsage(
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            total_tokens=run.total_tokens,
            cached_input_tokens=run.cached_input_tokens,
            cached_output_tokens=run.cached_output_tokens,
            reasoning_tokens=run.reasoning_tokens,
        ).finalize()
        if not usage.to_json():
            observed = observed_usage.finalize() if observed_usage is not None else None
            if observed is not None and observed.to_json():
                run.usage_source = observed_usage_source or USAGE_SOURCE_UNKNOWN
                run.input_tokens = observed.input_tokens
                run.output_tokens = observed.output_tokens
                run.total_tokens = observed.total_tokens
                run.cached_input_tokens = observed.cached_input_tokens
                run.cached_output_tokens = observed.cached_output_tokens
                run.reasoning_tokens = observed.reasoning_tokens
                run.usage_breakdown_json = observed.to_json() or None
                run.usage_tokens = int(observed.total_tokens or 0)
                usage = observed
            else:
                run.usage_source = USAGE_SOURCE_UNKNOWN
                run.usage_tokens = 0
                usage = NormalizedUsage().finalize()
        else:
            run.usage_breakdown_json = usage_payload or usage.to_json() or None

        pricing_snapshot = resolved_execution.pricing_snapshot if resolved_execution is not None else (
            dict(run.pricing_snapshot_json or {}) if isinstance(run.pricing_snapshot_json, dict) else {}
        )
        if resolved_execution is not None:
            run.pricing_snapshot_json = pricing_snapshot or binding_pricing_snapshot(resolved_execution.binding)
            run.resolved_binding_id = resolved_execution.binding.id
            run.resolved_provider = resolved_execution.resolved_provider
            run.resolved_provider_model_id = resolved_execution.binding.provider_model_id

        normalized_cost = compute_cost_from_snapshot(
            usage=usage,
            pricing_snapshot=pricing_snapshot if pricing_snapshot else None,
        )
        run.cost_source = normalized_cost.source if normalized_cost.total_cost is not None else COST_SOURCE_UNKNOWN
        run.cost_usd = float(normalized_cost.total_cost) if normalized_cost.total_cost is not None else None
        run.cost_breakdown_json = normalized_cost.to_json() or None
        if normalized_cost.total_cost is not None:
            run.cost = f"{float(normalized_cost.total_cost):.6f}"
        if context_window is None:
            ContextWindowService.write_to_run(run, None)

    @staticmethod
    def _extract_assistant_output_text(output_result: Dict[str, Any] | None) -> str | None:
        # `assistant_output_text` is the persisted chat reply. `final_output` is
        # the workflow return value, so only use it as a narrow textual fallback.
        return extract_assistant_output_text(
            output_result,
            allow_final_output_fallback=True,
        )

    @staticmethod
    def _extract_turn_assistant_output_text(run: AgentRun) -> str | None:
        output_result = run.output_result if isinstance(run.output_result, dict) else None
        assistant_text = AgentExecutorService._extract_assistant_output_text(output_result)
        if assistant_text:
            return assistant_text
        status = str(getattr(run.status, "value", run.status) or "").strip().lower()
        if status == RunStatus.failed.value:
            error_text = str(getattr(run, "error_message", "") or "").strip()
            if error_text:
                return f"Execution failed: {error_text}"
        return None

    @staticmethod
    def _thread_turn_status_for_run(run: AgentRun) -> AgentThreadTurnStatus:
        if run.status == RunStatus.paused:
            return AgentThreadTurnStatus.paused
        if run.status == RunStatus.failed:
            return AgentThreadTurnStatus.failed
        if run.status == RunStatus.cancelled:
            return AgentThreadTurnStatus.cancelled
        return AgentThreadTurnStatus.completed

    @staticmethod
    def _status_text(value: Any) -> str:
        return str(getattr(value, "value", value) or "").strip().lower()

    @classmethod
    def _is_cancelled_status(cls, value: Any) -> bool:
        return cls._status_text(value) == RunStatus.cancelled.value

    @classmethod
    def _is_terminal_status(cls, value: Any) -> bool:
        return cls._status_text(value) in {
            RunStatus.completed.value,
            RunStatus.failed.value,
            RunStatus.cancelled.value,
        }

    @staticmethod
    def _normalize_execution_mode(raw: Any) -> ExecutionMode:
        value = str(raw or "").strip().lower()
        return ExecutionMode.DEBUG if value == ExecutionMode.DEBUG.value else ExecutionMode.PRODUCTION

    @classmethod
    def _execution_mode_from_input_params(cls, input_params: dict[str, Any] | None) -> ExecutionMode:
        context = input_params.get("context") if isinstance(input_params, dict) else {}
        if not isinstance(context, dict):
            context = {}
        return cls._normalize_execution_mode(context.get("execution_mode"))

    @staticmethod
    def _pending_resume_payload_from_input_params(input_params: dict[str, Any] | None) -> dict[str, Any] | None:
        context = input_params.get("context") if isinstance(input_params, dict) else {}
        if not isinstance(context, dict):
            return None
        payload = context.get("pending_resume_payload")
        return dict(payload) if isinstance(payload, dict) else None

    @staticmethod
    def _strip_pending_resume_payload(input_params: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(input_params, dict):
            return input_params
        updated = dict(input_params)
        context = updated.get("context")
        if not isinstance(context, dict):
            return updated
        context = dict(context)
        context.pop("pending_resume_payload", None)
        updated["context"] = context
        return updated

    async def _assert_parent_run_accepting_children(self, parent_run_id: UUID | None) -> None:
        if parent_run_id is None:
            return
        parent_status = (
            await self.db.execute(select(AgentRun.status).where(AgentRun.id == parent_run_id))
        ).scalar_one_or_none()
        if parent_status is None:
            raise ValueError(f"Parent run {parent_run_id} not found")
        if self._is_cancelled_status(parent_status):
            raise RuntimeError(f"Parent run {parent_run_id} is cancelled")

    @staticmethod
    async def _refresh_run_record(db: AsyncSession, run: AgentRun) -> AgentRun:
        await db.refresh(run)
        return run

    async def _enqueue_background_run(self, run_id: UUID) -> None:
        from app.workers.tasks import execute_agent_run_task
        from app.workers.celery_app import celery_app

        run = await self.db.get(AgentRun, run_id)
        if run is None:
            raise ValueError(f"Run {run_id} not found")

        run.dispatch_count = int(getattr(run, "dispatch_count", 0) or 0) + 1
        run.last_dispatched_at = datetime.now(timezone.utc)
        if not str(getattr(run, "execution_owner_kind", "") or "").strip():
            run.execution_owner_kind = "celery"
        await self.db.commit()

        if bool(getattr(celery_app.conf, "task_always_eager", False)):
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                asyncio.create_task(
                    self.__class__.execute_worker_run_with_new_session(
                        run_id=run_id,
                        owner_id=f"eager-{uuid4()}",
                    ),
                    name=f"agent-run-eager-dispatch:{run_id}",
                )
                return

        execute_agent_run_task.apply_async(args=[str(run_id)], queue="agent_runs")

    @classmethod
    async def _claim_run_for_worker(
        cls,
        *,
        run_id: UUID,
        owner_id: str,
    ) -> tuple[str, dict[str, Any] | None, ExecutionMode]:
        from app.db.postgres.engine import sessionmaker as get_session

        async with get_session() as session:
            run = await session.get(AgentRun, run_id, with_for_update=True)
            if run is None:
                return "missing", None, ExecutionMode.PRODUCTION

            status = cls._status_text(run.status)
            if cls._is_terminal_status(run.status):
                return "terminal", None, cls._execution_mode_from_input_params(run.input_params)

            now = datetime.now(timezone.utc)
            lease_expires_at = run.execution_lease_expires_at
            if (
                run.execution_owner_id
                and str(run.execution_owner_id) != str(owner_id)
                and lease_expires_at is not None
                and lease_expires_at > now
            ):
                return "busy", None, cls._execution_mode_from_input_params(run.input_params)

            resume_payload = cls._pending_resume_payload_from_input_params(run.input_params)
            run.input_params = cls._strip_pending_resume_payload(run.input_params)
            run.execution_owner_kind = "celery"
            run.execution_owner_id = str(owner_id)
            run.execution_heartbeat_at = now
            run.execution_lease_expires_at = now + timedelta(seconds=cls._WORKER_LEASE_SECONDS)
            if status == RunStatus.paused.value:
                run.status = RunStatus.queued
            await session.commit()
            return "claimed", resume_payload, cls._execution_mode_from_input_params(run.input_params)

    @classmethod
    async def _heartbeat_worker_run(
        cls,
        *,
        run_id: UUID,
        owner_id: str,
        stop_event: asyncio.Event,
    ) -> None:
        from app.db.postgres.engine import sessionmaker as get_session

        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=cls._WORKER_HEARTBEAT_SECONDS)
                break
            except asyncio.TimeoutError:
                pass

            async with get_session() as session:
                run = await session.get(AgentRun, run_id, with_for_update=True)
                if run is None or str(run.execution_owner_id or "") != str(owner_id):
                    return
                if cls._is_terminal_status(run.status):
                    return
                now = datetime.now(timezone.utc)
                run.execution_heartbeat_at = now
                run.execution_lease_expires_at = now + timedelta(seconds=cls._WORKER_LEASE_SECONDS)
                await session.commit()

    @classmethod
    async def _release_worker_claim(
        cls,
        *,
        run_id: UUID,
        owner_id: str,
    ) -> None:
        from app.db.postgres.engine import sessionmaker as get_session

        async with get_session() as session:
            run = await session.get(AgentRun, run_id, with_for_update=True)
            if run is None or str(run.execution_owner_id or "") != str(owner_id):
                return
            run.execution_owner_id = None
            run.execution_lease_expires_at = None
            run.execution_heartbeat_at = None
            await session.commit()

    @classmethod
    async def execute_worker_run_with_new_session(cls, *, run_id: UUID, owner_id: str) -> str:
        claim_status, resume_payload, mode = await cls._claim_run_for_worker(
            run_id=run_id,
            owner_id=owner_id,
        )
        if claim_status != "claimed":
            return claim_status

        from app.db.postgres.engine import sessionmaker as get_session

        stop_event = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            cls._heartbeat_worker_run(run_id=run_id, owner_id=owner_id, stop_event=stop_event),
            name=f"agent-run-heartbeat:{run_id}",
        )
        try:
            async with get_session() as session:
                executor = cls(db=session)
                await executor._execute(run_id, db=session, resume_payload=resume_payload, mode=mode)
        finally:
            stop_event.set()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
            await cls._release_worker_claim(run_id=run_id, owner_id=owner_id)
        return "claimed"

    @staticmethod
    def _extract_turn_metadata(output_result: Dict[str, Any] | None) -> Dict[str, Any] | None:
        if not isinstance(output_result, dict):
            return None
        metadata: Dict[str, Any] = {}
        if "final_output" in output_result:
            metadata["final_output"] = output_result.get("final_output")
        return metadata or None

    async def _build_thread_turn_payload(
        self,
        *,
        db: AsyncSession,
        run: AgentRun,
    ) -> tuple[str | None, Dict[str, Any] | None]:
        output_result = run.output_result if isinstance(run.output_result, dict) else None
        metadata = self._extract_turn_metadata(output_result)
        recorder = ExecutionTraceRecorder(serializer=lambda value: value)
        raw_events = await recorder.list_events(db, run.id)
        response_blocks = build_response_blocks_from_trace_events(
            raw_events=raw_events,
            run_id=str(run.id),
            final_output=(output_result or {}).get("final_output"),
            mode=ExecutionMode.PRODUCTION,
        )
        assistant_text = extract_assistant_text_from_blocks(response_blocks) or self._extract_turn_assistant_output_text(run)
        next_metadata = dict(metadata or {})
        if response_blocks:
            next_metadata["response_blocks"] = response_blocks
        return assistant_text, (next_metadata or None)

    @staticmethod
    def _build_paused_node_payload(
        *,
        node: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any] | None:
        node_type = str(node.get("type") or "").strip().lower()
        config = node.get("config") if isinstance(node.get("config"), dict) else {}
        label = str((config or {}).get("label") or config.get("name") or node.get("id") or "").strip() or None
        payload: dict[str, Any] = {
            "id": str(node.get("id") or ""),
            "type": node_type or None,
            "name": label,
        }
        if node_type == "user_approval":
            message = str(config.get("message") or "")
            payload["interaction"] = {
                "kind": "user_approval",
                "message": evaluate_template(message, state) if message else "",
                "require_comment": bool(config.get("require_comment")),
                "timeout_seconds": config.get("timeout_seconds"),
            }
            return payload
        if node_type == "human_input":
            prompt = str(config.get("prompt") or "")
            payload["interaction"] = {
                "kind": "human_input",
                "prompt": evaluate_template(prompt, state) if prompt else "",
                "timeout_seconds": config.get("timeout_seconds"),
            }
            return payload
        return payload

    async def start_run(
        self, 
        agent_id: UUID, 
        input_params: Dict[str, Any], 
        user_id: Optional[UUID] = None, 
        background: bool = True,
        mode: ExecutionMode = ExecutionMode.DEBUG,
        requested_scopes: Optional[list[str]] = None,
        root_run_id: Optional[UUID] = None,
        parent_run_id: Optional[UUID] = None,
        parent_node_id: Optional[str] = None,
        depth: int = 0,
        spawn_key: Optional[str] = None,
        orchestration_group_id: Optional[UUID] = None,
        thread_id: Optional[UUID] = None,
    ) -> UUID:
        """
        Starts a new agent execution run.
        If background is True, it triggers a background task and returns the ID.
        If background is False, it only creates the DB record.
        """
        if is_run_cancel_requested(run_id=parent_run_id, root_run_id=root_run_id):
            raise RuntimeError("Cannot start run under a cancelled run tree")
        agent = await self.db.get(Agent, agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        await self._assert_parent_run_accepting_children(parent_run_id)

        # Create Run record
        runtime_context = {}
        if isinstance(input_params, dict):
            runtime_context = dict(input_params.get("context") or {})

        initiator_user_id = runtime_context.get("initiator_user_id")
        parsed_initiator_id = None
        try:
            parsed_initiator_id = UUID(str(initiator_user_id)) if initiator_user_id else None
        except Exception:
            parsed_initiator_id = None

        run_id = uuid4()
        effective_initiator_id = user_id or parsed_initiator_id

        # Resolve/create thread before creating the run record.
        input_params = dict(input_params or {})
        raw_thread_id = thread_id or runtime_context.get("thread_id") or input_params.get("thread_id")
        parsed_thread_id: Optional[UUID] = None
        try:
            parsed_thread_id = UUID(str(raw_thread_id)) if raw_thread_id else None
        except Exception:
            raise ValueError("Invalid thread_id")

        surface = AgentThreadSurface.internal
        runtime_surface = str(runtime_context.get("surface") or "").strip().lower()
        if runtime_surface == "artifact_coding_agent":
            surface = AgentThreadSurface.artifact_admin
        elif runtime_context.get("published_app_preview"):
            surface = AgentThreadSurface.preview_runtime
        elif runtime_context.get("published_app_id"):
            surface = AgentThreadSurface.published_host_runtime
        elif runtime_surface == "embedded_agent_runtime":
            surface = AgentThreadSurface.embedded_runtime

        published_app_id: Optional[UUID] = None
        raw_published_app_id = runtime_context.get("published_app_id")
        try:
            published_app_id = UUID(str(raw_published_app_id)) if raw_published_app_id else None
        except Exception:
            published_app_id = None

        published_app_account_id: Optional[UUID] = None
        raw_published_app_account_id = runtime_context.get("published_app_account_id")
        try:
            published_app_account_id = UUID(str(raw_published_app_account_id)) if raw_published_app_account_id else None
        except Exception:
            published_app_account_id = None

        tenant_api_key_id: Optional[UUID] = None
        raw_tenant_api_key_id = runtime_context.get("tenant_api_key_id")
        try:
            tenant_api_key_id = UUID(str(raw_tenant_api_key_id)) if raw_tenant_api_key_id else None
        except Exception:
            tenant_api_key_id = None

        external_user_id = str(runtime_context.get("external_user_id") or "").strip() or None
        external_session_id = str(runtime_context.get("external_session_id") or "").strip() or None

        thread_service = ThreadService(self.db)
        try:
            thread_result = await thread_service.resolve_or_create_thread(
                tenant_id=agent.tenant_id,
                user_id=effective_initiator_id,
                app_account_id=published_app_account_id,
                tenant_api_key_id=tenant_api_key_id,
                agent_id=agent_id,
                published_app_id=published_app_id,
                external_user_id=external_user_id,
                external_session_id=external_session_id,
                surface=surface,
                thread_id=parsed_thread_id,
                input_text=input_params.get("input") if isinstance(input_params.get("input"), str) else None,
                parent_run_id=parent_run_id,
            )
        except ThreadAccessError as exc:
            raise ValueError(str(exc)) from exc

        attachment_service = RuntimeAttachmentService(self.db)
        attachment_owner = RuntimeAttachmentOwner(
            tenant_id=agent.tenant_id,
            surface=surface,
            user_id=effective_initiator_id,
            app_account_id=published_app_account_id,
            tenant_api_key_id=tenant_api_key_id,
            agent_id=agent_id,
            published_app_id=published_app_id,
            external_user_id=external_user_id,
            external_session_id=external_session_id,
            thread_id=thread_result.thread.id,
        )
        attachment_ids = input_params.get("attachment_ids") if isinstance(input_params.get("attachment_ids"), list) else []
        input_preparation_service = RuntimeInputPreparationService(
            attachment_service,
            stt_service=SpeechToTextService(self.db, agent.tenant_id),
        )
        prepared_message = await input_preparation_service.prepare_for_run(
            owner=attachment_owner,
            attachment_ids=[str(item) for item in attachment_ids],
            input_text=input_params.get("input") if isinstance(input_params.get("input"), str) else None,
            model_ids=self._collect_graph_model_ids(agent.graph_definition or {}),
        )
        base_messages = input_params.get("messages")
        normalized_messages = list(base_messages) if isinstance(base_messages, list) else []
        if prepared_message.content is not None:
            normalized_messages.append({"role": "user", "content": prepared_message.content})
        input_params["messages"] = normalized_messages
        input_params["input_display_text"] = prepared_message.display_text
        input_params["attachment_ids"] = [str(attachment.id) for attachment in prepared_message.attachments]
        input_params["attachments"] = [
            attachment_service.serialize_attachment(attachment) for attachment in prepared_message.attachments
        ]
        workflow_input = input_params.get("workflow_input") if isinstance(input_params.get("workflow_input"), dict) else {}
        input_params["workflow_input"] = {
            **workflow_input,
            **RuntimeInputPreparationService.build_workflow_input_payload(
                input_text=input_params.get("input") if isinstance(input_params.get("input"), str) else None,
                attachments=input_params["attachments"],
            ),
        }
        self._assert_workflow_inputs_allowed(
            graph_definition=agent.graph_definition or {},
            workflow_input=input_params["workflow_input"],
        )

        policy_service = ResourcePolicyService(self.db)
        policy_snapshot = self._safe_policy_snapshot_from_context(runtime_context)
        if policy_snapshot is None:
            policy_snapshot = await policy_service.resolve_execution_snapshot(
                tenant_id=agent.tenant_id,
                agent_id=agent.id,
                user_id=effective_initiator_id,
                published_app_id=published_app_id,
                published_app_account_id=published_app_account_id,
                external_user_id=external_user_id,
            )
        await policy_service.assert_agent_access(snapshot=policy_snapshot, agent_id=agent.id)
        requested_model_target = self._resolve_requested_model_target(runtime_context, agent.graph_definition or {})
        requested_model_id = requested_model_target.logical_model_id
        requested_model_ref = requested_model_target.ref

        if self._is_platform_architect(agent):
            architect_mode_service = ArchitectModeService(self.db)
            try:
                effective_mode = await architect_mode_service.resolve_effective_mode(
                    tenant_id=agent.tenant_id,
                    user_id=effective_initiator_id,
                    requested_mode=runtime_context.get("architect_mode"),
                )
            except ArchitectModeError as exc:
                raise ValueError(str(exc)) from exc
            context_payload_mode = runtime_context.get("architect_mode")
            runtime_context["requested_architect_mode"] = str(context_payload_mode or "").strip() or None
            runtime_context["architect_mode"] = effective_mode.value
            runtime_context["architect_effective_scopes"] = architect_mode_service.scopes_for_mode(effective_mode)

        # Reserve quota (if enabled) before creating the run record.
        quota_metadata = {"max_output_cap": None}
        if runtime_surface not in {"published_app_coding_agent", "artifact_coding_agent"}:
            try:
                quota_service = UsageQuotaService(self.db)
                quota_metadata = await quota_service.reserve_for_run(
                    run_id=run_id,
                    tenant_id=agent.tenant_id,
                    user_id=effective_initiator_id,
                    input_params=input_params,
                )
                resource_policy_quota = await ResourcePolicyQuotaService(self.db).reserve_for_run(
                    run_id=run_id,
                    tenant_id=agent.tenant_id,
                    snapshot=policy_snapshot,
                    model_id=requested_model_id,
                    input_params=input_params,
                )
                quota_metadata["max_output_cap"] = self._merge_quota_caps(
                    quota_metadata.get("max_output_cap"),
                    resource_policy_quota.max_output_cap,
                )
            except (ResourcePolicyAccessDenied, ResourcePolicyQuotaExceeded):
                await self.db.rollback()
                raise
            except Exception:
                await self.db.rollback()
                raise
        context_payload = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
        context_payload = dict(context_payload)
        context_payload["thread_id"] = str(thread_result.thread.id)
        context_payload["surface"] = surface.value if hasattr(surface, "value") else str(surface)
        if requested_model_ref:
            context_payload["requested_model_id"] = requested_model_ref
        if policy_snapshot is not None:
            context_payload["resource_policy_snapshot"] = policy_snapshot.to_payload()
            if policy_snapshot.principal is not None:
                context_payload["resource_policy_principal"] = policy_snapshot.principal.to_payload()
        if quota_metadata.get("max_output_cap"):
            context_payload["quota_max_output_tokens"] = int(quota_metadata["max_output_cap"])
        context_payload["execution_mode"] = mode.value
        pre_run_receipt: ResolvedModelBindingReceipt | None = None
        if requested_model_ref:
            try:
                pre_run_receipt = await ModelResolver(self.db, agent.tenant_id).resolve_receipt(
                    requested_model_ref,
                    policy_snapshot=policy_snapshot,
                )
            except ModelResolverError:
                logger.warning("Failed to resolve pre-run context receipt for run %s", run_id, exc_info=True)
        context_window = await ContextWindowService(self.db).build_pre_run_window(
            tenant_id=agent.tenant_id,
            model_id=(
                str(pre_run_receipt.logical_model.id)
                if pre_run_receipt is not None
                else requested_model_ref or (str(requested_model_id) if requested_model_id else None)
            ),
            resolved_provider=pre_run_receipt.resolved_provider if pre_run_receipt is not None else None,
            resolved_provider_model_id=pre_run_receipt.binding.provider_model_id if pre_run_receipt is not None else None,
            api_key=pre_run_receipt.api_key if pre_run_receipt is not None else None,
            input_params=input_params,
            runtime_context=context_payload,
        )
        input_params["context"] = context_payload
        input_params["thread_id"] = str(thread_result.thread.id)

        run = AgentRun(
            id=run_id,
            agent_id=agent_id,
            tenant_id=agent.tenant_id,
            user_id=effective_initiator_id,
            thread_id=thread_result.thread.id,
            initiator_user_id=effective_initiator_id,
            published_app_id=published_app_id,
            published_app_account_id=published_app_account_id,
            external_user_id=external_user_id,
            surface=runtime_surface or None,
            input_params=input_params,
            context_window_json=context_window,
            requested_model_id=pre_run_receipt.logical_model.id if pre_run_receipt is not None else requested_model_id,
            resolved_model_id=pre_run_receipt.logical_model.id if pre_run_receipt is not None else None,
            resolved_binding_id=pre_run_receipt.binding.id if pre_run_receipt is not None else None,
            resolved_provider=pre_run_receipt.resolved_provider if pre_run_receipt is not None else None,
            resolved_provider_model_id=pre_run_receipt.binding.provider_model_id if pre_run_receipt is not None else None,
            status=RunStatus.queued,
            root_run_id=root_run_id,
            parent_run_id=parent_run_id,
            parent_node_id=parent_node_id,
            depth=depth,
            spawn_key=spawn_key,
            orchestration_group_id=orchestration_group_id,
            started_at=None,
            completed_at=None
        )
        self.db.add(run)
        await self.db.flush()

        await self.db.commit()
        await self.db.refresh(run)

        # Root runs self-reference for efficient run-tree queries.
        if run.root_run_id is None:
            run.root_run_id = run.id
            await self.db.commit()
            await self.db.refresh(run)
        record_run_lineage(run.id, root_run_id=run.root_run_id or run.id, parent_run_id=run.parent_run_id)

        if background:
            await self._enqueue_background_run(run.id)
        
        return run.id

    async def _execute_with_new_session(self, run_id: UUID, resume_payload: Optional[Dict[str, Any]] = None, mode: ExecutionMode = ExecutionMode.DEBUG):
        """Wrapper to provide a fresh session for inline execution."""
        from app.db.postgres.engine import sessionmaker as get_session
        async with get_session() as session:
            try:
                await self._execute(run_id, db=session, resume_payload=resume_payload, mode=mode)
            except Exception as e:
                logger.error(f"Background execution wrapper failed: {e}")

    @classmethod
    async def execute_sync_with_new_session(
        cls,
        *,
        agent_id: UUID,
        input_params: Dict[str, Any],
        user_id: Optional[UUID] = None,
        mode: ExecutionMode = ExecutionMode.DEBUG,
        requested_scopes: Optional[list[str]] = None,
        root_run_id: Optional[UUID] = None,
        parent_run_id: Optional[UUID] = None,
        parent_node_id: Optional[str] = None,
        depth: int = 0,
        spawn_key: Optional[str] = None,
        orchestration_group_id: Optional[UUID] = None,
        thread_id: Optional[UUID] = None,
        timeout_s: float | None = None,
        on_run_created: Callable[[UUID], Any] | None = None,
    ) -> SyncRunExecutionResult:
        from app.db.postgres.engine import sessionmaker as get_session

        async with get_session() as session:
            executor = cls(db=session)
            run_id = await executor.start_run(
                agent_id=agent_id,
                input_params=input_params,
                user_id=user_id,
                background=False,
                mode=mode,
                requested_scopes=requested_scopes,
                root_run_id=root_run_id,
                parent_run_id=parent_run_id,
                parent_node_id=parent_node_id,
                depth=depth,
                spawn_key=spawn_key,
                orchestration_group_id=orchestration_group_id,
                thread_id=thread_id,
            )
            if on_run_created is not None:
                callback_result = on_run_created(run_id)
                if inspect.isawaitable(callback_result):
                    await callback_result
            child_task: asyncio.Task[None] | None = None

            try:
                async def _run_sync() -> None:
                    async for _ in executor.run_and_stream(run_id, session, None, mode):
                        pass

                child_task = asyncio.create_task(_run_sync(), name=f"sync-agent-call:{run_id}")
                if timeout_s is None:
                    await child_task
                else:
                    await asyncio.wait_for(child_task, timeout=timeout_s)
            except asyncio.TimeoutError:
                await cls._drain_task(child_task)
                await cls._rollback_quietly(session)
                run = await session.get(AgentRun, run_id)
                if run is not None:
                    run.status = RunStatus.failed
                    run.error_message = f"agent_call timed out after {int(timeout_s)}s"
                    run.completed_at = datetime.now(timezone.utc)
                    await session.commit()
                    await session.refresh(run)
                    return SyncRunExecutionResult(
                        run_id=run_id,
                        status=str(getattr(run.status, "value", run.status)),
                        output_result=run.output_result if isinstance(run.output_result, dict) else {},
                        error_message=run.error_message,
                    )
                raise
            except asyncio.CancelledError:
                await cls._drain_task(child_task)
                await cls._rollback_quietly(session)
                current_task = asyncio.current_task()
                if current_task and current_task.cancelling():
                    raise
                run = await session.get(AgentRun, run_id)
                if run is not None:
                    await session.refresh(run)
                    return SyncRunExecutionResult(
                        run_id=run_id,
                        status=str(getattr(run.status, "value", run.status)),
                        output_result=run.output_result if isinstance(run.output_result, dict) else {},
                        error_message=run.error_message,
                    )
                raise
            except Exception:
                await cls._drain_task(child_task)
                await cls._rollback_quietly(session)
                raise

            run = await session.get(AgentRun, run_id)
            if run is None:
                raise RuntimeError("Child run missing after synchronous execution")
            await session.refresh(run)
            return SyncRunExecutionResult(
                run_id=run_id,
                status=str(getattr(run.status, "value", run.status)),
                output_result=run.output_result if isinstance(run.output_result, dict) else {},
                error_message=run.error_message,
            )

    async def resume_run(self, run_id: UUID, user_input: Dict[str, Any], background: bool = True) -> None:
        """
        Resumes a paused agent execution run with user input.
        """
        run = await self.db.get(AgentRun, run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        
        if run.status != RunStatus.paused:
            raise ValueError(f"Run {run_id} is not paused (status: {run.status})")
        
        input_params = dict(run.input_params or {}) if isinstance(run.input_params, dict) else {}
        context = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
        context = dict(context)
        if background and isinstance(user_input, dict):
            context["pending_resume_payload"] = dict(user_input)
        else:
            context.pop("pending_resume_payload", None)
        input_params["context"] = context
        run.input_params = input_params
        run.status = RunStatus.queued
        run.execution_owner_id = None
        run.execution_lease_expires_at = None
        run.execution_heartbeat_at = None
        await self.db.commit()

        if background:
            await self._enqueue_background_run(run.id)

    async def _execute(self, run_id: UUID, db: AsyncSession, resume_payload: Optional[Dict[str, Any]] = None, mode: ExecutionMode = ExecutionMode.DEBUG):
        """
        Core execution logic. This runs the LangGraph workflow.
        """
        try:
            async for _ in self.run_and_stream(run_id, db, resume_payload, mode):
                pass
        except Exception as e:
            # Error handling is inside run_and_stream or wrapped there
            logger.error(f"Execution run {run_id} failed: {e}")
        finally:
            run = await db.get(AgentRun, run_id)
            if run is not None and self._status_text(run.status) == RunStatus.running.value:
                if not isinstance(run.output_result, dict):
                    run.output_result = {}
                run.status = RunStatus.completed
                run.completed_at = run.completed_at or datetime.utcnow()
                await db.commit()

    async def run_and_stream(
        self, 
        run_id: UUID, 
        db: AsyncSession, 
        resume_payload: Optional[Dict[str, Any]] = None,
        mode: ExecutionMode = ExecutionMode.DEBUG
    ) -> AsyncGenerator[ExecutionEvent, None]:
        """
        Executes the agent and yields TAGGED ExecutionEvents.
        DB persistence is handled asynchronously (Fire-and-Forget).
        
        Architecture:
        - Creates an event queue for explicit emissions from node executors.
        - Sets active_emitter ContextVar for implicit access in nodes.
        - Runs LangGraph execution and queue consumption concurrently.
        - Normalizes ALL events (both LangGraph and explicit) to ExecutionEvent.
        """
        run = await db.get(AgentRun, run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        register_run_task(
            run_id,
            root_run_id=run.root_run_id or run.id,
            parent_run_id=run.parent_run_id,
        )
        try:
            if self._is_cancelled_status(run.status) or is_run_cancel_requested(
                run_id=run.id,
                root_run_id=run.root_run_id or run.id,
                parent_run_id=run.parent_run_id,
            ):
                return

            agent = await db.get(Agent, run.agent_id)
            if not agent:
                raise ValueError(f"Agent {run.agent_id} not found")

            run_input_params = run.input_params

            runtime_context = {}
            if isinstance(run_input_params, dict):
                runtime_context = dict(run_input_params.get("context") or {})
            if run.initiator_user_id:
                runtime_context["initiator_user_id"] = str(run.initiator_user_id)
            runtime_context["run_id"] = str(run.id)
            if run.root_run_id:
                runtime_context["root_run_id"] = str(run.root_run_id)
            if run.parent_run_id:
                runtime_context["parent_run_id"] = str(run.parent_run_id)
            if run.parent_node_id:
                runtime_context["parent_node_id"] = str(run.parent_node_id)
            if run.thread_id:
                runtime_context["thread_id"] = str(run.thread_id)
            runtime_context["depth"] = int(run.depth or 0)
            if run.spawn_key:
                runtime_context["spawn_key"] = run.spawn_key
            if run.orchestration_group_id:
                runtime_context["orchestration_group_id"] = str(run.orchestration_group_id)
            if run.tenant_id:
                runtime_context["tenant_id"] = str(run.tenant_id)
            runtime_context["agent_id"] = str(agent.id)
            if getattr(agent, "slug", None):
                runtime_context["agent_slug"] = str(agent.slug)
            if run.resolved_model_id:
                runtime_context["resolved_model_id"] = str(run.resolved_model_id)
            runtime_context["orchestration_surface"] = "option_a_graphspec_v2"
            if isinstance(run_input_params, dict):
                run_input_params = dict(run_input_params)
                run_input_params["context"] = runtime_context
                workflow_input = run_input_params.get("workflow_input")
                if not isinstance(workflow_input, dict):
                    workflow_input = {}
                workflow_input = {
                    "text": str(run_input_params.get("input") or workflow_input.get("text") or workflow_input.get("input_as_text") or ""),
                    "input_as_text": str(run_input_params.get("input") or workflow_input.get("text") or workflow_input.get("input_as_text") or ""),
                    **workflow_input,
                }
                run_input_params["workflow_input"] = workflow_input
                existing_state = run_input_params.get("state")
                if not isinstance(existing_state, dict):
                    existing_state = {}
                existing_state = dict(existing_state)
                existing_state["context"] = dict(runtime_context)
                run_input_params["state"] = existing_state
            else:
                run_input_params = {
                    "context": runtime_context,
                    "workflow_input": {"text": "", "input_as_text": ""},
                    "state": {"context": dict(runtime_context)},
                }

            resolved_execution = await self._resolve_run_model_receipt(
                db=db,
                run=run,
                agent=agent,
                runtime_context=runtime_context,
            )
            if resolved_execution is not None:
                runtime_context["resolved_model_id"] = str(resolved_execution.logical_model.id)
                runtime_context["resolved_binding_id"] = str(resolved_execution.binding.id)
                runtime_context["resolved_provider"] = resolved_execution.resolved_provider
                runtime_context["resolved_provider_model_id"] = resolved_execution.binding.provider_model_id

            run.status = RunStatus.running
            if not run.started_at:
                run.started_at = datetime.utcnow()
            await db.commit()

            event_sequence = 0

            def persist_event(event: ExecutionEvent | dict[str, Any]) -> None:
                nonlocal event_sequence
                event_sequence += 1
                self.trace_recorder.schedule_persist(run_id, event, sequence=event_sequence)

            persist_event(
                ExecutionEvent(
                    event="run.lifecycle",
                    data={
                        "phase": "started",
                        "agent_id": str(agent.id),
                        "agent_slug": getattr(agent, "slug", None),
                        "mode": mode.value,
                    },
                    run_id=str(run_id),
                    span_id=str(run_id),
                    name="AgentRun",
                    visibility=EventVisibility.INTERNAL,
                    metadata={"category": "lifecycle", "mode": mode.value},
                )
            )

            try:
                persist_event(
                    ExecutionEvent(
                        event="run.lifecycle",
                        data={"phase": "compile_graph_started"},
                        run_id=str(run_id),
                        span_id=str(run_id),
                        name="AgentRun",
                        visibility=EventVisibility.INTERNAL,
                        metadata={"category": "lifecycle"},
                    )
                )
                compiler = AgentCompiler(db=db, tenant_id=agent.tenant_id)
                resolved_model_id = str(run.resolved_model_id) if run.resolved_model_id else None
                if not resolved_model_id:
                    candidate = runtime_context.get("resolved_model_id")
                    if candidate:
                        resolved_model_id = str(candidate)
                graph_payload = agent.graph_definition if isinstance(agent.graph_definition, dict) else {}
                graph_payload = self._apply_run_scoped_model_override(graph_payload, resolved_model_id)
                graph_payload = await PromptReferenceResolver(db, agent.tenant_id).resolve_graph_definition(graph_payload)
                graph_def = AgentGraph(**graph_payload)
                compile_input_params = run_input_params
                if resume_payload and isinstance(resume_payload, dict) and "approval" in resume_payload:
                    compile_input_params = dict(run_input_params or {})
                    compile_input_params["approval"] = resume_payload.get("approval")
                graph_ir = await compiler.compile(
                    agent.id,
                    agent.version,
                    graph_def,
                    config={"mode": mode.value},
                    input_params=compile_input_params,
                )
                persist_event(
                    ExecutionEvent(
                        event="run.lifecycle",
                        data={
                            "phase": "compile_graph_completed",
                            "node_count": len(graph_def.nodes),
                            "edge_count": len(graph_def.edges),
                        },
                        run_id=str(run_id),
                        span_id=str(run_id),
                        name="AgentRun",
                        visibility=EventVisibility.INTERNAL,
                        metadata={"category": "lifecycle"},
                    )
                )
                analysis = graph_ir.metadata.get("analysis") if isinstance(graph_ir.metadata, dict) else {}
                inventory = analysis.get("inventory") if isinstance(analysis, dict) else {}
                persist_event(
                    ExecutionEvent(
                        event="workflow.inventory_snapshot",
                        data={
                            "workflow_input_count": len(inventory.get("workflow_input") or []),
                            "state_count": len(inventory.get("state") or []),
                            "node_output_group_count": len(inventory.get("node_outputs") or []),
                        },
                        run_id=str(run_id),
                        span_id=str(run_id),
                        name="AgentRun",
                        visibility=EventVisibility.INTERNAL,
                        metadata={"category": "workflow_contract", "mode": mode.value},
                    )
                )

                adapter_cls = RuntimeAdapterRegistry.get_default()
                adapter = adapter_cls(tenant_id=agent.tenant_id, db=db)
                executable = await adapter.compile(graph_ir, checkpointer=self._checkpointer)
                persist_event(
                    ExecutionEvent(
                        event="run.lifecycle",
                        data={"phase": "adapter_ready", "adapter": adapter_cls.__name__},
                        run_id=str(run_id),
                        span_id=str(run_id),
                        name="AgentRun",
                        visibility=EventVisibility.INTERNAL,
                        metadata={"category": "lifecycle"},
                    )
                )

                config = {
                    "thread_id": str(run_id),
                    "run_id": str(run_id),
                    "mode": mode.value,
                    "resume_payload": resume_payload,
                    "architect_mode": runtime_context.get("architect_mode"),
                    "initiator_user_id": str(run.initiator_user_id) if run.initiator_user_id else None,
                    "tenant_id": str(run.tenant_id) if run.tenant_id else None,
                    "user_id": str(run.user_id) if run.user_id else None,
                    "agent_id": str(agent.id),
                    "agent_slug": str(getattr(agent, "slug", "")) or None,
                    "auth_token": runtime_context.get("token"),
                    "root_run_id": str(run.root_run_id) if run.root_run_id else None,
                    "parent_run_id": str(run.parent_run_id) if run.parent_run_id else None,
                    "parent_node_id": run.parent_node_id,
                    "depth": int(run.depth or 0),
                    "spawn_key": run.spawn_key,
                    "orchestration_group_id": str(run.orchestration_group_id) if run.orchestration_group_id else None,
                    "orchestration_surface": runtime_context.get("orchestration_surface"),
                }
            except Exception as e:
                await db.rollback()
                logger.error(f"Execution setup failed for run {run_id}: {e}")
                traceback.print_exc()
                persist_event(
                    ExecutionEvent(
                        event="run.lifecycle",
                        data={"phase": "setup_failed", "error": str(e)},
                        run_id=str(run_id),
                        span_id=str(run_id),
                        name="AgentRun",
                        visibility=EventVisibility.INTERNAL,
                        metadata={"category": "lifecycle"},
                    )
                )
                error_event = ExecutionEvent(
                    event="error",
                    data={"error": str(e)},
                    run_id=str(run_id),
                    visibility=EventVisibility.CLIENT_SAFE,
                )
                persist_event(error_event)
                yield error_event
                await self._mark_run_failed(run_id, e, mode=mode)
                return

            try:
                turn = None
                if run.thread_id:
                    thread_service = ThreadService(db)
                    turn = await thread_service.start_turn(
                        thread_id=run.thread_id,
                        run_id=run_id,
                        user_input_text=(
                            run_input_params.get("input_display_text")
                            if isinstance(run_input_params, dict)
                            else None
                        ) or (
                            run_input_params.get("input")
                            if isinstance(run_input_params, dict)
                            else None
                        ),
                        attachment_ids=[
                            UUID(str(item))
                            for item in ((run_input_params.get("attachment_ids") or []) if isinstance(run_input_params, dict) else [])
                            if str(item).strip()
                        ],
                        metadata={
                            "mode": mode.value,
                            "context_window": ContextWindowService.read_from_run(run),
                        },
                    )

                persist_event(
                    ExecutionEvent(
                        event="run.lifecycle",
                        data={"phase": "stream_started"},
                        run_id=str(run_id),
                        span_id=str(run_id),
                        name="AgentRun",
                        visibility=EventVisibility.INTERNAL,
                        metadata={"category": "lifecycle"},
                    )
                )
                await self._refresh_run_record(db, run)
                invocation_service = RunInvocationService(db)
                async for event in adapter.stream(executable, run_input_params, config):
                    persist_event(event)
                    yield event
                    invocation_payload = self._extract_invocation_payload(event)
                    if invocation_payload is not None:
                        await invocation_service.append_from_payload(run=run, payload=invocation_payload)
                        _, context_window = await invocation_service.recompute_run_aggregates(run)
                        if turn is not None:
                            next_metadata = dict(turn.metadata_ or {})
                            next_metadata["context_window"] = ContextWindowService.read_from_run(run)
                            turn.metadata_ = next_metadata
                        await db.flush()
                        usage_event = ExecutionEvent(
                            event="run_usage.updated",
                            data={"run_usage": self._serialize_run_usage_event(run)},
                            run_id=str(run_id),
                            visibility=EventVisibility.CLIENT_SAFE,
                            metadata={"category": "usage", "mode": mode.value},
                        )
                        persist_event(usage_event)
                        yield usage_event
                        context_event = ExecutionEvent(
                            event="context_window.updated",
                            data={"context_window": context_window or ContextWindowService.read_from_run(run)},
                            run_id=str(run_id),
                            visibility=EventVisibility.CLIENT_SAFE,
                            metadata={"category": "context", "mode": mode.value},
                        )
                        persist_event(context_event)
                        yield context_event
                    await self._refresh_run_record(db, run)
                    if run.status == RunStatus.cancelled or is_run_cancel_requested(
                        run_id=run.id,
                        root_run_id=run.root_run_id or run.id,
                        parent_run_id=run.parent_run_id,
                    ):
                        if run.status != RunStatus.cancelled:
                            run.status = RunStatus.cancelled
                            run.completed_at = run.completed_at or datetime.utcnow()
                        persist_event(
                            ExecutionEvent(
                                event="run.lifecycle",
                                data={"phase": "cancelled_during_stream"},
                                run_id=str(run_id),
                                span_id=str(run_id),
                                name="AgentRun",
                                visibility=EventVisibility.INTERNAL,
                                metadata={"category": "lifecycle", "mode": mode.value},
                            )
                        )
                        break

                await self._refresh_run_record(db, run)
                output_result: Dict[str, Any] | Any = run.output_result if isinstance(run.output_result, dict) else {}
                snapshot_next = None
                final_status = RunStatus.completed
                if run.status == RunStatus.cancelled or is_run_cancel_requested(
                    run_id=run.id,
                    root_run_id=run.root_run_id or run.id,
                    parent_run_id=run.parent_run_id,
                ):
                    run.status = RunStatus.cancelled
                    final_status = RunStatus.cancelled
                    if not isinstance(run.output_result, dict):
                        run.output_result = {}
                        output_result = run.output_result
                    run.completed_at = run.completed_at or datetime.utcnow()
                else:
                    snapshot: RuntimeState = adapter.get_state(executable, config)
                    snapshot_next = snapshot.next
                    output_result = self._serialize_state(snapshot.values)
                    terminal_failure = output_result.get("_run_failure") if isinstance(output_result, dict) else None
                    terminal_failure_message = ""
                    if isinstance(terminal_failure, dict):
                        terminal_failure_message = str(
                            terminal_failure.get("message")
                            or output_result.get("error")
                            or ""
                        ).strip()

                    if snapshot_next:
                        final_status = RunStatus.paused
                        run.status = RunStatus.paused
                        run.checkpoint = output_result
                    elif terminal_failure_message:
                        final_status = RunStatus.failed
                        run.status = RunStatus.failed
                        run.output_result = output_result
                        run.error_message = terminal_failure_message
                        run.completed_at = datetime.utcnow()
                    else:
                        run.status = RunStatus.completed
                        run.output_result = output_result
                        run.completed_at = datetime.utcnow()

                await self._finalize_run_accounting(
                    run=run,
                    resolved_execution=resolved_execution,
                    observed_usage=None,
                    observed_usage_source=None,
                    input_params=run_input_params if isinstance(run_input_params, dict) else {},
                    output_result=run.output_result if isinstance(run.output_result, dict) else output_result if isinstance(output_result, dict) else None,
                )

                next_nodes = []
                if snapshot_next:
                    next_ids = snapshot_next if isinstance(snapshot_next, list) else [snapshot_next]
                    node_index = {n.id: n for n in graph_def.nodes}
                    for next_id in next_ids:
                        node = node_index.get(next_id)
                        if node:
                            next_nodes.append(
                                self._build_paused_node_payload(
                                    node=node.model_dump(),
                                    state=snapshot.values if isinstance(snapshot.values, dict) else {},
                                )
                            )
                        else:
                            next_nodes.append({"id": next_id})

                run_status_event = ExecutionEvent(
                    event="run_status",
                    data={
                        "status": final_status.value,
                        "next": snapshot_next,
                        "next_nodes": next_nodes or None,
                        "final_output": (
                            run.output_result.get("final_output")
                            if final_status == RunStatus.completed and isinstance(run.output_result, dict)
                            else None
                        ),
                        "error": (
                            run.error_message
                            if final_status == RunStatus.failed
                            else None
                        ),
                        "context_window": ContextWindowService.read_from_run(run),
                        "run_usage": self._serialize_run_usage_event(run),
                    },
                    run_id=str(run_id),
                    visibility=EventVisibility.CLIENT_SAFE,
                    metadata={"mode": mode.value},
                )
                persist_event(run_status_event)
                persist_event(
                    ExecutionEvent(
                        event="run.lifecycle",
                        data={
                            "phase": "finished",
                            "status": final_status.value,
                            "next": snapshot_next,
                        },
                        run_id=str(run_id),
                        span_id=str(run_id),
                        name="AgentRun",
                        visibility=EventVisibility.INTERNAL,
                        metadata={"category": "lifecycle", "mode": mode.value},
                    )
                )

                quota_service = UsageQuotaService(db)
                await quota_service.settle_for_run(
                    run_id=run_id,
                    actual_usage_tokens=billable_total_tokens(run),
                )
                await ResourcePolicyQuotaService(db).settle_for_run(run=run)
                if run.thread_id:
                    thread_service = ThreadService(db)
                    assistant_output_text, thread_metadata = await self._build_thread_turn_payload(db=db, run=run)
                    await thread_service.complete_turn(
                        run_id=run_id,
                        status=self._thread_turn_status_for_run(run),
                        assistant_output_text=assistant_output_text,
                        metadata=thread_metadata,
                    )
                await db.commit()
                yield run_status_event

            except asyncio.CancelledError:
                await self._rollback_quietly(db)
                raise
            except Exception as e:
                await db.rollback()
                logger.error(f"Streaming execution failed for run {run_id}: {e}")
                traceback.print_exc()
                persist_event(
                    ExecutionEvent(
                        event="run.lifecycle",
                        data={"phase": "stream_failed", "error": str(e)},
                        run_id=str(run_id),
                        span_id=str(run_id),
                        name="AgentRun",
                        visibility=EventVisibility.INTERNAL,
                        metadata={"category": "lifecycle"},
                    )
                )

                error_event = ExecutionEvent(
                    event="error",
                    data={"error": str(e)},
                    run_id=str(run_id),
                    visibility=EventVisibility.CLIENT_SAFE,
                )
                persist_event(error_event)
                yield error_event
                await self._mark_run_failed(run_id, e, mode=mode)
        finally:
            await self.trace_recorder.drain()
            unregister_run_task(run_id)

    async def _mark_run_failed(self, run_id: UUID, error: Exception, *, mode: ExecutionMode | None = None) -> None:
        error_text = str(error)
        assistant_error_text = f"Execution failed: {error_text}"
        try:
            from app.db.postgres.engine import sessionmaker as get_session
            async with get_session() as err_db:
                err_run = await err_db.get(AgentRun, run_id)
                if not err_run:
                    return

                err_run.status = RunStatus.failed
                err_run.error_message = error_text
                err_run.completed_at = datetime.utcnow()

                output_result: Dict[str, Any] = {}
                if isinstance(err_run.output_result, dict):
                    output_result = dict(err_run.output_result)
                messages = output_result.get("messages")
                if not isinstance(messages, list):
                    messages = []
                messages.append({"role": "assistant", "content": assistant_error_text})
                output_result["messages"] = messages
                output_result["error"] = error_text
                err_run.output_result = output_result
                if err_run.usage_source is None:
                    await self._finalize_run_accounting(
                        run=err_run,
                        resolved_execution=None,
                        observed_usage=build_usage_from_total(getattr(err_run, "total_tokens", None) or err_run.usage_tokens),
                        observed_usage_source=(
                            USAGE_SOURCE_ESTIMATED
                            if (getattr(err_run, "total_tokens", None) or err_run.usage_tokens)
                            else USAGE_SOURCE_UNKNOWN
                        ),
                        input_params=err_run.input_params if isinstance(err_run.input_params, dict) else {},
                        output_result=err_run.output_result if isinstance(err_run.output_result, dict) else None,
                    )

                quota_service = UsageQuotaService(err_db)
                await quota_service.settle_for_run(
                    run_id=run_id,
                    actual_usage_tokens=billable_total_tokens(err_run),
                )
                await ResourcePolicyQuotaService(err_db).settle_for_run(run=err_run)

                if err_run.thread_id:
                    thread_service = ThreadService(err_db)
                    input_text = None
                    if isinstance(err_run.input_params, dict):
                        raw_input = err_run.input_params.get("input")
                        if isinstance(raw_input, str):
                            input_text = raw_input
                    start_meta: Dict[str, Any] = {"error": error_text}
                    if mode is not None:
                        start_meta["mode"] = mode.value
                    await thread_service.start_turn(
                        thread_id=err_run.thread_id,
                        run_id=run_id,
                        user_input_text=input_text,
                        metadata=start_meta,
                    )
                    assistant_output_text, thread_metadata = await self._build_thread_turn_payload(db=err_db, run=err_run)
                    merged_metadata = dict(thread_metadata or {})
                    merged_metadata["error"] = error_text
                    await thread_service.complete_turn(
                        run_id=run_id,
                        status=AgentThreadTurnStatus.failed,
                        assistant_output_text=assistant_output_text,
                        metadata=merged_metadata,
                    )
                await err_db.commit()
        except Exception as se:
            logger.error(f"Failed to save error status for {run_id}: {se}")

    def _serialize_state(self, state: Any) -> Any:
        """Helper to make state JSON serializable (handling LangChain messages)."""
        if isinstance(state, dict):
            return {k: self._serialize_state(v) for k, v in state.items()}
        if isinstance(state, list):
            return [self._serialize_state(v) for v in state]
        if isinstance(state, tuple):
            return [self._serialize_state(v) for v in state]
        
        # Handle LangChain messages
        if hasattr(state, "type") and hasattr(state, "content") and not isinstance(state, dict):
            # This is likely a BaseMessage (HumanMessage, AIMessage, etc.)
            return {
                "role": getattr(state, "type"),
                "content": getattr(state, "content"),
                "additional_kwargs": getattr(state, "additional_kwargs", {}),
                "name": getattr(state, "name", None)
            }
        
        # Fallback for other non-serializable objects (like UUIDs)
        if isinstance(state, UUID):
            return str(state)
        if isinstance(state, datetime):
            return state.isoformat()
        if callable(state):
            name = getattr(state, "__name__", state.__class__.__name__)
            return f"<callable:{name}>"
        if isinstance(state, (str, int, float, bool)) or state is None:
            return state
        if hasattr(state, "isoformat"):
            try:
                return state.isoformat()
            except Exception:
                pass
            
        return str(state)
