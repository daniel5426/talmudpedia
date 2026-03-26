import logging
import asyncio
import traceback
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Dict, Any, Optional, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.postgres.models.agents import Agent, AgentRun, RunStatus
from app.agent.graph.compiler import AgentCompiler
from app.agent.graph.schema import AgentGraph
from app.agent.runtime.registry import RuntimeAdapterRegistry
from app.agent.runtime.base import RuntimeState
from app.agent.execution.types import ExecutionEvent, EventVisibility, ExecutionMode
from app.agent.execution.durable_checkpointer import DurableMemorySaver
from app.agent.cel_engine import evaluate_template
from app.agent.execution.trace_recorder import ExecutionTraceRecorder
from app.db.postgres.models.agent_threads import AgentThreadSurface, AgentThreadTurnStatus
from app.services.prompt_reference_resolver import PromptReferenceResolver
from app.services.runtime_attachment_service import RuntimeAttachmentOwner, RuntimeAttachmentService
from app.services.thread_service import ThreadAccessError, ThreadService
from app.services.usage_quota_service import UsageQuotaService
from app.services.model_accounting import (
    COST_SOURCE_UNKNOWN,
    USAGE_SOURCE_ESTIMATED,
    USAGE_SOURCE_PROVIDER_REPORTED,
    USAGE_SOURCE_SDK_REPORTED,
    USAGE_SOURCE_UNKNOWN,
    NormalizedUsage,
    billable_total_tokens,
    binding_pricing_snapshot,
    build_legacy_usage_from_total,
    compute_cost_from_snapshot,
)
from app.services.model_resolver import ModelResolver, ModelResolverError, ResolvedModelExecution

logger = logging.getLogger(__name__)

class AgentExecutorService:
    _checkpointer = DurableMemorySaver()

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        # Initial compiler for non-execution tasks if needed, 
        # but _execute will create its own local compiler.
        self.compiler = AgentCompiler(db=db) if db else None
        self.trace_recorder = ExecutionTraceRecorder(serializer=self._serialize_state)

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
            if node_type in {"agent", "llm", "llm_call", "classify"} and isinstance(config, dict):
                config = dict(config)
                if "model_id" in config:
                    config["model_id"] = resolved_model_id
                node["config"] = config
            patched_nodes.append(node)

        patched = dict(graph_definition)
        patched["nodes"] = patched_nodes
        return patched

    @staticmethod
    def _estimate_usage_tokens_from_payload(input_params: Dict[str, Any], output_result: Dict[str, Any] | None) -> int:
        total_chars = 0
        if isinstance(input_params, dict):
            raw_input = input_params.get("input")
            if isinstance(raw_input, str):
                total_chars += len(raw_input)
            messages = input_params.get("messages")
            if isinstance(messages, list):
                for msg in messages:
                    if isinstance(msg, dict):
                        total_chars += AgentExecutorService._content_text_length(msg.get("content"))
        if isinstance(output_result, dict):
            messages = output_result.get("messages")
            if isinstance(messages, list):
                for msg in messages:
                    if isinstance(msg, dict):
                        total_chars += AgentExecutorService._content_text_length(msg.get("content"))
            text = output_result.get("final_output")
            if isinstance(text, str):
                total_chars += len(text)
        return max(0, int(total_chars // 4))

    @staticmethod
    def _content_text_length(content: Any) -> int:
        if isinstance(content, str):
            return len(content)
        if isinstance(content, list):
            total = 0
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    total += len(str(item.get("text") or ""))
            return total
        return 0

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
            if node_type not in {"agent", "llm", "llm_call", "classify"}:
                continue
            config = raw_node.get("config")
            if not isinstance(config, dict):
                continue
            model_id = str(config.get("model_id") or "").strip()
            if model_id:
                model_ids.append(model_id)
        return model_ids

    @staticmethod
    def _extract_usage_tokens_from_event(event: ExecutionEvent) -> int:
        payload = event.data if isinstance(event.data, dict) else {}
        candidates: list[Any] = []
        for key in ("usage_tokens", "total_tokens", "tokens"):
            candidates.append(payload.get(key))
        usage = payload.get("usage")
        if isinstance(usage, dict):
            for key in ("total_tokens", "tokens", "usage_tokens"):
                candidates.append(usage.get(key))
        for candidate in candidates:
            try:
                parsed = int(candidate)
                if parsed > 0:
                    return parsed
            except Exception:
                continue
        return 0

    @staticmethod
    def _extract_usage_candidate(event: ExecutionEvent) -> tuple[NormalizedUsage | None, str | None]:
        payload = event.data if isinstance(event.data, dict) else {}
        usage = payload.get("usage")
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
        source = payload.get("usage_source")
        if source in {USAGE_SOURCE_PROVIDER_REPORTED, USAGE_SOURCE_SDK_REPORTED}:
            return normalized, str(source)
        if normalized.input_tokens is not None or normalized.output_tokens is not None:
            return normalized, USAGE_SOURCE_PROVIDER_REPORTED
        if normalized.total_tokens is not None:
            return normalized, USAGE_SOURCE_SDK_REPORTED
        return normalized, None

    @staticmethod
    def _maybe_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except Exception:
            return None

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
            USAGE_SOURCE_PROVIDER_REPORTED: 4,
            USAGE_SOURCE_SDK_REPORTED: 3,
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
    ) -> ResolvedModelExecution | None:
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
            execution = await ModelResolver(db, agent.tenant_id).resolve_for_execution(str(raw_requested_model_id))
        except ModelResolverError:
            logger.warning("Failed to resolve accounting receipt for run %s", run.id, exc_info=True)
            return None

        run.requested_model_id = execution.logical_model.id
        run.resolved_model_id = execution.logical_model.id
        run.resolved_binding_id = execution.binding.id
        run.resolved_provider = execution.resolved_provider
        run.resolved_provider_model_id = execution.binding.provider_model_id
        return execution

    def _finalize_run_accounting(
        self,
        *,
        run: AgentRun,
        resolved_execution: ResolvedModelExecution | None,
        observed_usage: NormalizedUsage | None,
        observed_usage_source: str | None,
        input_params: dict[str, Any],
        output_result: dict[str, Any] | None,
    ) -> None:
        usage = observed_usage.finalize() if observed_usage is not None else None
        usage_source = observed_usage_source
        if usage is None or not usage.to_json():
            estimated_total = self._estimate_usage_tokens_from_payload(input_params, output_result)
            if estimated_total > 0:
                usage = build_legacy_usage_from_total(estimated_total)
                usage_source = USAGE_SOURCE_ESTIMATED
            else:
                usage = NormalizedUsage().finalize()
                usage_source = USAGE_SOURCE_UNKNOWN

        usage_payload = usage.to_json()
        run.usage_source = usage_source or USAGE_SOURCE_UNKNOWN
        run.input_tokens = usage.input_tokens
        run.output_tokens = usage.output_tokens
        run.total_tokens = usage.total_tokens
        run.cached_input_tokens = usage.cached_input_tokens
        run.cached_output_tokens = usage.cached_output_tokens
        run.reasoning_tokens = usage.reasoning_tokens
        run.usage_breakdown_json = usage_payload or None
        if usage.total_tokens is not None:
            run.usage_tokens = int(usage.total_tokens)
        elif run.usage_tokens is None:
            run.usage_tokens = 0

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

    @staticmethod
    def _extract_assistant_output_text(output_result: Dict[str, Any] | None) -> str | None:
        if not isinstance(output_result, dict):
            return None
        final_output = output_result.get("final_output")
        if isinstance(final_output, str) and final_output.strip():
            return final_output.strip()
        messages = output_result.get("messages")
        if isinstance(messages, list):
            # Runtime state usually carries full conversation history.
            # Persist only the latest assistant turn to avoid cumulative replay.
            last_assistant: str | None = None
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                role = str(msg.get("role") or msg.get("type") or "").strip().lower()
                content = msg.get("content")
                if role in {"assistant", "ai"} and isinstance(content, str):
                    text = content.strip()
                    if text:
                        last_assistant = text
            if last_assistant:
                return last_assistant
        return None

    @staticmethod
    def _extract_turn_metadata(output_result: Dict[str, Any] | None) -> Dict[str, Any] | None:
        if not isinstance(output_result, dict):
            return None
        metadata: Dict[str, Any] = {}
        if "final_output" in output_result:
            metadata["final_output"] = output_result.get("final_output")
        return metadata or None

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
        agent = await self.db.get(Agent, agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Create Run record
        runtime_context = {}
        if isinstance(input_params, dict):
            runtime_context = dict(input_params.get("context") or {})

        delegation_grant_id = runtime_context.get("grant_id")
        workload_principal_id = runtime_context.get("principal_id")
        initiator_user_id = runtime_context.get("initiator_user_id")

        parsed_grant_id = None
        parsed_principal_id = None
        parsed_initiator_id = None
        try:
            parsed_grant_id = UUID(str(delegation_grant_id)) if delegation_grant_id else None
        except Exception:
            parsed_grant_id = None
        try:
            parsed_principal_id = UUID(str(workload_principal_id)) if workload_principal_id else None
        except Exception:
            parsed_principal_id = None
        try:
            parsed_initiator_id = UUID(str(initiator_user_id)) if initiator_user_id else None
        except Exception:
            parsed_initiator_id = None

        run_id = uuid4()
        effective_initiator_id = user_id or parsed_initiator_id

        # Strict workload delegation: runtime cannot create principal/policy intent.
        # Runs must mint grants only from pre-provisioned, approved policies.
        resolved_principal_id = parsed_principal_id
        resolved_grant_id = parsed_grant_id
        maybe_context = input_params.get("context") if isinstance(input_params, dict) else {}

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
        prepared_message = await attachment_service.prepare_for_run(
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
            except Exception:
                await self.db.rollback()
                raise
        context_payload = input_params.get("context") if isinstance(input_params.get("context"), dict) else {}
        context_payload = dict(context_payload)
        context_payload["thread_id"] = str(thread_result.thread.id)
        if quota_metadata.get("max_output_cap"):
            context_payload["quota_max_output_tokens"] = int(quota_metadata["max_output_cap"])
        input_params["context"] = context_payload
        input_params["thread_id"] = str(thread_result.thread.id)

        requested_model_id: Optional[UUID] = None
        raw_requested_model_id = context_payload.get("requested_model_id")
        try:
            requested_model_id = UUID(str(raw_requested_model_id)) if raw_requested_model_id else None
        except Exception:
            requested_model_id = None

        run = AgentRun(
            id=run_id,
            agent_id=agent_id,
            tenant_id=agent.tenant_id,
            user_id=effective_initiator_id,
            thread_id=thread_result.thread.id,
            initiator_user_id=effective_initiator_id,
            workload_principal_id=resolved_principal_id,
            delegation_grant_id=resolved_grant_id,
            published_app_id=published_app_id,
            published_app_account_id=published_app_account_id,
            surface=runtime_surface or None,
            input_params=input_params,
            requested_model_id=requested_model_id,
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

        if effective_initiator_id is not None and resolved_grant_id is None:
            from app.services.delegation_service import DelegationService, DelegationPolicyError

            delegation = DelegationService(self.db)
            try:
                principal, grant, _approval_required = await delegation.create_agent_run_grant(
                    agent=agent,
                    initiator_user_id=effective_initiator_id,
                    run_id=run_id,
                    requested_scopes=requested_scopes or ((maybe_context or {}).get("requested_scopes") if isinstance(maybe_context, dict) else None),
                )
            except DelegationPolicyError as exc:
                raise ValueError(f"{exc.code}: {exc.message}") from exc

            run.workload_principal_id = principal.id
            run.delegation_grant_id = grant.id

        await self.db.commit()
        await self.db.refresh(run)

        # Root runs self-reference for efficient run-tree queries.
        if run.root_run_id is None:
            run.root_run_id = run.id
            await self.db.commit()
            await self.db.refresh(run)

        # Trigger background execution if requested
        if background:
            asyncio.create_task(self._execute_with_new_session(run.id, mode=mode))
        
        return run.id

    async def _execute_with_new_session(self, run_id: UUID, resume_payload: Optional[Dict[str, Any]] = None, mode: ExecutionMode = ExecutionMode.DEBUG):
        """Wrapper to provide a fresh session for background execution."""
        from app.db.postgres.engine import sessionmaker as get_session
        async with get_session() as session:
            try:
                await self._execute(run_id, db=session, resume_payload=resume_payload, mode=mode)
            except Exception as e:
                logger.error(f"Background execution wrapper failed: {e}")

    async def resume_run(self, run_id: UUID, user_input: Dict[str, Any], background: bool = True) -> None:
        """
        Resumes a paused agent execution run with user input.
        """
        run = await self.db.get(AgentRun, run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        
        if run.status != RunStatus.paused:
            raise ValueError(f"Run {run_id} is not paused (status: {run.status})")
        
        # Set status back to running/queued to prevent double resume
        run.status = RunStatus.queued
        await self.db.commit()

        if background:
            asyncio.create_task(self._execute_with_new_session(run.id, resume_payload=user_input))

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
        # 1. Fetch Run & Agent
        run = await db.get(AgentRun, run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        agent = await db.get(Agent, run.agent_id)
        if not agent:
            raise ValueError(f"Agent {run.agent_id} not found")

        if (run.user_id is not None or run.initiator_user_id is not None) and run.delegation_grant_id is None:
            raise ValueError("WORKLOAD_PRINCIPAL_MISSING: Run is missing delegation grant context")

        # Capture input params before commit to avoid async lazy-loads
        run_input_params = run.input_params

        # Propagate delegation context into runtime state for node executors.
        runtime_context = {}
        if isinstance(run_input_params, dict):
            runtime_context = dict(run_input_params.get("context") or {})
        if run.delegation_grant_id:
            runtime_context["grant_id"] = str(run.delegation_grant_id)
        if run.workload_principal_id:
            runtime_context["principal_id"] = str(run.workload_principal_id)
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
                "input_as_text": str(run_input_params.get("input") or workflow_input.get("input_as_text") or ""),
                **workflow_input,
            }
            run_input_params["workflow_input"] = workflow_input
            # Keep auth/runtime context in persistent state bag too.
            # Top-level `context` is used by workflow logic and may be overwritten.
            existing_state = run_input_params.get("state")
            if not isinstance(existing_state, dict):
                existing_state = {}
            existing_state = dict(existing_state)
            existing_state["context"] = dict(runtime_context)
            run_input_params["state"] = existing_state
        else:
            run_input_params = {
                "context": runtime_context,
                "workflow_input": {"input_as_text": ""},
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

        # Update status
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
            # 2. Compile Graph to GraphIR
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
            if resume_payload and isinstance(resume_payload, dict):
                if "approval" in resume_payload:
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

            # 3. Create Runtime Adapter + Executable
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

            # 4. Prepare Config
            config = {
                "thread_id": str(run_id),
                "run_id": str(run_id),
                "mode": mode.value,
                "resume_payload": resume_payload,
                "grant_id": str(run.delegation_grant_id) if run.delegation_grant_id else None,
                "principal_id": str(run.workload_principal_id) if run.workload_principal_id else None,
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
                visibility=EventVisibility.CLIENT_SAFE
            )
            persist_event(error_event)
            yield error_event
            await self._mark_run_failed(run_id, e, mode=mode)
            return

        try:
            max_observed_usage_tokens = 0
            best_usage: NormalizedUsage | None = None
            best_usage_source: str | None = None
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
                    metadata={"mode": mode.value},
                )
            # 5. Stream Execution Events (Platform-normalized)
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
            async for event in adapter.stream(executable, run_input_params, config):
                max_observed_usage_tokens = max(
                    max_observed_usage_tokens,
                    self._extract_usage_tokens_from_event(event),
                )
                candidate_usage, candidate_usage_source = self._extract_usage_candidate(event)
                best_usage, best_usage_source = self._select_better_usage(
                    best_usage,
                    best_usage_source,
                    candidate_usage,
                    candidate_usage_source,
                )
                persist_event(event)
                yield event

            # 6. Post-Execution Check
            snapshot: RuntimeState = adapter.get_state(executable, config)

            output_result = self._serialize_state(snapshot.values)
            terminal_failure = output_result.get("_run_failure") if isinstance(output_result, dict) else None
            terminal_failure_message = ""
            if isinstance(terminal_failure, dict):
                terminal_failure_message = str(
                    terminal_failure.get("message")
                    or output_result.get("error")
                    or ""
                ).strip()

            final_status = RunStatus.completed
            if snapshot.next:
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

            if best_usage is None and max_observed_usage_tokens > 0:
                best_usage = build_legacy_usage_from_total(max_observed_usage_tokens)
                best_usage_source = USAGE_SOURCE_SDK_REPORTED
            self._finalize_run_accounting(
                run=run,
                resolved_execution=resolved_execution,
                observed_usage=best_usage,
                observed_usage_source=best_usage_source,
                input_params=run_input_params if isinstance(run_input_params, dict) else {},
                output_result=run.output_result if isinstance(run.output_result, dict) else output_result if isinstance(output_result, dict) else None,
            )

            # Emit final status event
            next_nodes = []
            if snapshot.next:
                next_ids = snapshot.next if isinstance(snapshot.next, list) else [snapshot.next]
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
                    "next": snapshot.next,
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
                },
                run_id=str(run_id),
                visibility=EventVisibility.CLIENT_SAFE,
                metadata={"mode": mode.value}
            )
            persist_event(run_status_event)
            yield run_status_event
            persist_event(
                ExecutionEvent(
                    event="run.lifecycle",
                    data={
                        "phase": "finished",
                        "status": final_status.value,
                        "next": snapshot.next,
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
            if run.thread_id:
                thread_service = ThreadService(db)
                await thread_service.complete_turn(
                    run_id=run_id,
                    status=(
                        AgentThreadTurnStatus.paused
                        if run.status == RunStatus.paused
                        else AgentThreadTurnStatus.failed
                        if run.status == RunStatus.failed
                        else AgentThreadTurnStatus.completed
                    ),
                    assistant_output_text=self._extract_assistant_output_text(
                        run.output_result if isinstance(run.output_result, dict) else None
                    ),
                    usage_tokens=billable_total_tokens(run),
                    metadata=self._extract_turn_metadata(
                        run.output_result if isinstance(run.output_result, dict) else None
                    ),
                )
            await db.commit()

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

            # Emit error event
            error_event = ExecutionEvent(
                event="error",
                data={"error": str(e)},
                run_id=str(run_id),
                visibility=EventVisibility.CLIENT_SAFE
            )
            persist_event(error_event)
            yield error_event
            await self._mark_run_failed(run_id, e, mode=mode)

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
                    self._finalize_run_accounting(
                        run=err_run,
                        resolved_execution=None,
                        observed_usage=build_legacy_usage_from_total(getattr(err_run, "total_tokens", None) or err_run.usage_tokens),
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
                    await thread_service.complete_turn(
                        run_id=run_id,
                        status=AgentThreadTurnStatus.failed,
                        assistant_output_text=self._extract_assistant_output_text(err_run.output_result),
                        usage_tokens=billable_total_tokens(err_run),
                        metadata={"error": error_text},
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
