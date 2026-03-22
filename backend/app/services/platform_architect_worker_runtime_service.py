from __future__ import annotations

import asyncio
from hashlib import sha256
import json
from typing import Any
from uuid import UUID

from app.agent.execution.trace_recorder import ExecutionTraceRecorder
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.execution.service import AgentExecutorService
from app.db.postgres.models.agents import AgentRun, RunStatus
from app.services.orchestration_kernel_service import OrchestrationKernelService
from app.services.platform_architect_worker_bindings import (
    PlatformArchitectWorkerBindingService,
    WorkerBindingRef,
    parse_binding_ref,
)


TERMINAL_RUN_STATUSES = {
    RunStatus.completed.value,
    RunStatus.failed.value,
    RunStatus.cancelled.value,
    RunStatus.paused.value,
}

BLOCKING_QUESTION_PREFIX = "BLOCKING QUESTION:"


class PlatformArchitectWorkerRuntimeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.kernel = OrchestrationKernelService(db)
        self.bindings = PlatformArchitectWorkerBindingService(db)
        self.trace_recorder = ExecutionTraceRecorder(serializer=lambda value: value)

    def _record_trace_event(self, run_id: UUID, name: str, data: dict[str, Any]) -> None:
        self.trace_recorder.schedule_persist(
            run_id,
            {
                "event": name,
                "name": name,
                "visibility": "debug",
                "tags": ["platform_architect", "worker_respond"],
                "data": data,
            },
            sequence=0,
        )

    @staticmethod
    def parse_runtime_context(payload: dict[str, Any]) -> dict[str, Any]:
        raw = payload.get("__tool_runtime_context__")
        if not isinstance(raw, dict):
            raw = payload.get("context")
        if not isinstance(raw, dict):
            raise ValueError("Missing tool runtime context")

        def _required_uuid(key: str) -> UUID:
            value = raw.get(key)
            if key == "user_id" and value in (None, ""):
                value = raw.get("initiator_user_id")
            if value in (None, ""):
                raise ValueError(f"Missing runtime context '{key}'")
            try:
                return UUID(str(value))
            except Exception as exc:
                raise ValueError(f"Invalid runtime context '{key}'") from exc

        tenant_id = _required_uuid("tenant_id")
        user_id = _required_uuid("user_id")
        caller_run_id = _required_uuid("run_id")

        requested_scopes = raw.get("requested_scopes")
        scope_subset = []
        if isinstance(requested_scopes, list):
            scope_subset = [str(item) for item in requested_scopes if isinstance(item, str) and item.strip()]
        return {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "caller_run_id": caller_run_id,
            "requested_scopes": scope_subset,
        }

    @staticmethod
    def _clean_payload(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        return {key: value for key, value in payload.items() if key != "__tool_runtime_context__"}

    @staticmethod
    def _task_prompt(task: dict[str, Any]) -> str:
        objective = str(task.get("objective") or "").strip()
        if not objective:
            raise ValueError("task.objective is required")
        parts = [objective]

        constraints = task.get("constraints")
        if isinstance(constraints, list):
            normalized = [str(item).strip() for item in constraints if str(item).strip()]
            if normalized:
                parts.append("Constraints:\n" + "\n".join(f"- {item}" for item in normalized))

        success_criteria = task.get("success_criteria")
        if isinstance(success_criteria, list):
            normalized = [str(item).strip() for item in success_criteria if str(item).strip()]
            if normalized:
                parts.append("Success criteria:\n" + "\n".join(f"- {item}" for item in normalized))

        context = task.get("context")
        if isinstance(context, dict) and context:
            parts.append("Task context JSON:\n" + json.dumps(context, sort_keys=True))

        return "\n\n".join(parts)

    @staticmethod
    def _default_scope_subset(runtime_context: dict[str, Any], payload_scope_subset: Any) -> list[str]:
        if isinstance(payload_scope_subset, list):
            normalized = [str(item).strip() for item in payload_scope_subset if str(item).strip()]
            if normalized:
                return normalized
        from_runtime = list(runtime_context.get("requested_scopes") or [])
        if from_runtime:
            return from_runtime
        return ["agents.execute"]

    @staticmethod
    def _stable_idempotency_key(
        *,
        caller_run_id: UUID,
        worker_agent_slug: str,
        task: dict[str, Any],
        binding_ref: WorkerBindingRef | None,
        explicit_key: str | None,
        suffix: str | None = None,
    ) -> str:
        cleaned = str(explicit_key or "").strip()
        if cleaned:
            return cleaned
        payload = {
            "caller_run_id": str(caller_run_id),
            "worker_agent_slug": worker_agent_slug,
            "objective": str(task.get("objective") or ""),
            "binding_ref": binding_ref.as_dict() if binding_ref else None,
            "suffix": suffix,
        }
        digest = sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        return f"architect-worker:{digest[:20]}"

    @staticmethod
    def _extract_assistant_output_text(output_result: dict[str, Any] | None) -> str | None:
        if not isinstance(output_result, dict):
            return None
        final_output = output_result.get("final_output")
        if isinstance(final_output, str) and final_output.strip():
            return final_output.strip()
        messages = output_result.get("messages")
        if isinstance(messages, list):
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
        state = output_result.get("state")
        if isinstance(state, dict):
            last_output = state.get("last_agent_output")
            if isinstance(last_output, str) and last_output.strip():
                return last_output.strip()
        return None

    @staticmethod
    def _extract_waiting_state(run: AgentRun) -> dict[str, Any] | None:
        output_result = run.output_result if isinstance(run.output_result, dict) else {}

        explicit_waiting = output_result.get("worker_waiting_state")
        if isinstance(explicit_waiting, dict):
            waiting = bool(explicit_waiting.get("waiting_for_input"))
            if waiting:
                return {
                    "waiting_for_input": True,
                    "waiting_for_input_from": str(explicit_waiting.get("waiting_for_input_from") or "orchestrator"),
                    "blocking_question": str(explicit_waiting.get("blocking_question") or "").strip() or None,
                    "blocking_context": explicit_waiting.get("blocking_context")
                    if isinstance(explicit_waiting.get("blocking_context"), dict)
                    else None,
                    "source": "explicit_state",
                }

        assistant_text = PlatformArchitectWorkerRuntimeService._extract_assistant_output_text(output_result)
        if assistant_text:
            stripped = assistant_text.strip()
            if stripped.upper().startswith(BLOCKING_QUESTION_PREFIX):
                question = stripped[len(BLOCKING_QUESTION_PREFIX) :].strip()
                return {
                    "waiting_for_input": True,
                    "waiting_for_input_from": "orchestrator",
                    "blocking_question": question or None,
                    "blocking_context": None,
                    "source": "assistant_output_prefix",
                }

        if str(getattr(run.status, "value", run.status)) == RunStatus.paused.value:
            checkpoint = run.checkpoint if isinstance(run.checkpoint, dict) else {}
            next_nodes = checkpoint.get("next")
            return {
                "waiting_for_input": True,
                "waiting_for_input_from": "user",
                "blocking_question": None,
                "blocking_context": {
                    "next": next_nodes,
                } if next_nodes is not None else None,
                "source": "paused_checkpoint",
            }

        return None

    async def _resolve_child_run(
        self,
        *,
        tenant_id: UUID,
        caller_run_id: UUID,
        run_id: UUID,
    ) -> AgentRun:
        run = await self.db.get(AgentRun, run_id)
        if run is None or run.tenant_id != tenant_id:
            raise ValueError("Run not found")
        if hasattr(self.db, "refresh"):
            await self.db.refresh(run)
        caller_run = await self.db.get(AgentRun, caller_run_id)
        if caller_run is None:
            raise ValueError("Caller run not found")
        valid_root = caller_run.root_run_id or caller_run.id
        if (run.root_run_id or run.id) != valid_root and run.parent_run_id != caller_run.id:
            raise ValueError("Run is outside caller orchestration tree")
        return run

    async def _serialize_run_view(self, run: AgentRun) -> dict[str, Any]:
        input_context = run.input_params.get("context") if isinstance(run.input_params, dict) else {}
        binding_ref = input_context.get("architect_worker_binding_ref") if isinstance(input_context, dict) else None
        waiting_state = self._extract_waiting_state(run)
        status = str(getattr(run.status, "value", run.status))
        lifecycle_state = "running"
        next_action_hint = "poll_or_await"
        if waiting_state is not None:
            lifecycle_state = "waiting_for_input"
            next_action_hint = "respond_or_surface_blocker"
        elif status == RunStatus.completed.value:
            lifecycle_state = "completed"
            next_action_hint = "binding_get_state_then_persist"
        elif status in {RunStatus.failed.value, RunStatus.cancelled.value}:
            lifecycle_state = "terminal_error"
            next_action_hint = "handle_failure"

        return {
            "run_id": str(run.id),
            "status": status,
            "lifecycle_state": lifecycle_state,
            "worker_agent_id": str(run.agent_id),
            "binding_ref": binding_ref if isinstance(binding_ref, dict) else None,
            "error": run.error_message,
            "completed_at": run.completed_at,
            "created_at": run.created_at,
            "output": run.output_result if isinstance(run.output_result, dict) else None,
            "lineage": self.kernel._serialize_lineage(run),
            "waiting_state": waiting_state,
            "next_action_hint": next_action_hint,
        }

    async def _continue_binding_conversation(
        self,
        *,
        runtime_context: dict[str, Any],
        prior_run: AgentRun,
        response: str,
    ) -> dict[str, Any]:
        input_context = prior_run.input_params.get("context") if isinstance(prior_run.input_params, dict) else {}
        if not isinstance(input_context, dict):
            input_context = {}
        binding_ref_raw = input_context.get("architect_worker_binding_ref")
        binding_ref = parse_binding_ref(binding_ref_raw) if isinstance(binding_ref_raw, dict) else None
        if binding_ref is None:
            raise ValueError("WORKER_CONTINUATION_UNSUPPORTED")

        adapter = self.bindings.adapter_for_ref(binding_ref)

        self._record_trace_event(
            runtime_context["caller_run_id"],
            "architect.worker_respond.native_continuation_requested",
            {
                "prior_run_id": str(prior_run.id),
                "prior_run_status": str(getattr(prior_run.status, "value", prior_run.status)),
                "prior_thread_id": str(prior_run.thread_id) if prior_run.thread_id else None,
                "binding_ref": binding_ref.as_dict(),
            },
        )
        self._record_trace_event(
            prior_run.id,
            "architect.worker_respond.native_continuation_requested",
            {
                "caller_run_id": str(runtime_context["caller_run_id"]),
                "prior_thread_id": str(prior_run.thread_id) if prior_run.thread_id else None,
            },
        )

        task = input_context.get("architect_worker_task") if isinstance(input_context.get("architect_worker_task"), dict) else None
        prepared = await adapter.build_spawn_payload(
            tenant_id=runtime_context["tenant_id"],
            user_id=runtime_context["user_id"],
            binding_ref=binding_ref,
            prompt=response.strip(),
            prompt_role="user",
            task=task,
        )
        continued_result = await self.kernel.spawn_run(
            caller_run_id=runtime_context["caller_run_id"],
            parent_node_id="architect_worker_respond",
            target_agent_id=None,
            target_agent_slug=str(prepared.get("worker_agent_slug") or "").strip() or None,
            mapped_input_payload=prepared.get("mapped_input_payload") if isinstance(prepared.get("mapped_input_payload"), dict) else {},
            failure_policy=None,
            timeout_s=None,
            scope_subset=self._default_scope_subset(runtime_context, None),
            idempotency_key=self._stable_idempotency_key(
                caller_run_id=runtime_context["caller_run_id"],
                worker_agent_slug=str(prepared.get("worker_agent_slug") or "").strip() or "artifact-coding-agent",
                task={"objective": response.strip()},
                binding_ref=binding_ref,
                explicit_key=None,
                suffix=f"respond:{prior_run.id}",
            ),
            start_background=True,
            thread_id=UUID(str(prepared["thread_id"])) if prepared.get("thread_id") else None,
        )
        continued_run = await self.db.get(AgentRun, UUID(str(continued_result["spawned_run_ids"][0])))
        if continued_run is None:
            raise RuntimeError("Continued worker run was not created")
        await adapter.register_spawned_run(
            tenant_id=runtime_context["tenant_id"],
            user_id=runtime_context["user_id"],
            binding_ref=binding_ref,
            run_id=continued_run.id,
            prompt=response.strip(),
            prompt_role="user",
        )
        self._record_trace_event(
            runtime_context["caller_run_id"],
            "architect.worker_respond.native_continuation_started",
            {
                "prior_run_id": str(prior_run.id),
                "new_run_id": str(continued_run.id),
                "prior_thread_id": str(prior_run.thread_id) if prior_run.thread_id else None,
                "new_thread_id": str(continued_run.thread_id) if continued_run.thread_id else None,
            },
        )
        self._record_trace_event(
            continued_run.id,
            "architect.worker_respond.native_continuation_started",
            {
                "prior_run_id": str(prior_run.id),
                "caller_run_id": str(runtime_context["caller_run_id"]),
                "prior_thread_id": str(prior_run.thread_id) if prior_run.thread_id else None,
                "new_thread_id": str(continued_run.thread_id) if continued_run.thread_id else None,
            },
        )
        view = await self._serialize_run_view(continued_run)
        view["next_action_hint"] = "await_latest_child_then_persist"
        view["continuation_of_run_id"] = str(prior_run.id)
        return view

    async def prepare_binding(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime_context = self.parse_runtime_context(payload)
        binding_type = str(payload.get("binding_type") or "").strip()
        if not binding_type:
            raise ValueError("binding_type is required")
        prepare_mode = str(payload.get("prepare_mode") or "").strip()
        if not prepare_mode:
            raise ValueError("prepare_mode is required")
        binding_payload = {
            "prepare_mode": prepare_mode,
            "binding_id": payload.get("binding_id"),
            "artifact_id": payload.get("artifact_id"),
            "draft_key": payload.get("draft_key"),
            "title_prompt": payload.get("title_prompt"),
            "draft_seed": payload.get("draft_seed"),
            "draft_snapshot": payload.get("draft_snapshot"),
        }
        replace_snapshot = bool(payload.get("replace_snapshot"))
        adapter = self.bindings.adapter_for_type(binding_type)
        return await adapter.prepare(
            tenant_id=runtime_context["tenant_id"],
            user_id=runtime_context["user_id"],
            binding_payload=binding_payload,
            replace_snapshot=replace_snapshot,
        )

    async def get_binding_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime_context = self.parse_runtime_context(payload)
        binding_ref = parse_binding_ref(payload.get("binding_ref"))
        run_id_raw = payload.get("run_id")
        reconcile_run_id = UUID(str(run_id_raw)) if run_id_raw else None
        adapter = self.bindings.adapter_for_ref(binding_ref)
        return await adapter.get_state(
            tenant_id=runtime_context["tenant_id"],
            user_id=runtime_context["user_id"],
            binding_ref=binding_ref,
            reconcile_run_id=reconcile_run_id,
        )

    async def persist_binding_artifact(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime_context = self.parse_runtime_context(payload)
        binding_ref = parse_binding_ref(payload.get("binding_ref"))
        mode = str(payload.get("mode") or "auto").strip() or "auto"
        adapter = self.bindings.adapter_for_ref(binding_ref)
        return await adapter.persist_artifact(
            tenant_id=runtime_context["tenant_id"],
            user_id=runtime_context["user_id"],
            binding_ref=binding_ref,
            mode=mode,
        )

    async def spawn_worker(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime_context = self.parse_runtime_context(payload)
        task = {
            "objective": payload.get("objective"),
            "context": payload.get("context"),
            "constraints": payload.get("constraints"),
            "success_criteria": payload.get("success_criteria"),
        }
        prompt = self._task_prompt(task)
        binding_ref = parse_binding_ref(payload.get("binding_ref")) if payload.get("binding_ref") is not None else None

        worker_agent_slug = str(payload.get("worker_agent_slug") or "").strip()
        binding_context: dict[str, Any] = {}
        if binding_ref is not None:
            adapter = self.bindings.adapter_for_ref(binding_ref)
            binding_context = await adapter.build_spawn_payload(
                tenant_id=runtime_context["tenant_id"],
                user_id=runtime_context["user_id"],
                binding_ref=binding_ref,
                prompt=prompt,
                prompt_role="user",
                task=task,
            )
            worker_agent_slug = worker_agent_slug or str(binding_context.get("worker_agent_slug") or "").strip()
        if not worker_agent_slug:
            raise ValueError("worker_agent_slug is required")
        result = await self.kernel.spawn_run(
            caller_run_id=runtime_context["caller_run_id"],
            parent_node_id="architect_worker_spawn",
            target_agent_id=None,
            target_agent_slug=worker_agent_slug,
            mapped_input_payload=(
                binding_context.get("mapped_input_payload")
                if isinstance(binding_context.get("mapped_input_payload"), dict)
                else {
                    "input": prompt,
                    "messages": [],
                    "context": {"architect_worker_task": task},
                }
            ),
            failure_policy=str(payload.get("failure_policy") or "").strip() or None,
            timeout_s=int(payload.get("timeout_s")) if payload.get("timeout_s") is not None else None,
            scope_subset=self._default_scope_subset(runtime_context, payload.get("scope_subset")),
            idempotency_key=self._stable_idempotency_key(
                caller_run_id=runtime_context["caller_run_id"],
                worker_agent_slug=worker_agent_slug,
                task=task,
                binding_ref=binding_ref,
                explicit_key=str(payload.get("idempotency_key") or "").strip() or None,
            ),
            start_background=True,
            thread_id=UUID(str(binding_context["thread_id"])) if binding_context.get("thread_id") else None,
        )
        run_id = UUID(result["spawned_run_ids"][0])
        if binding_ref is not None:
            adapter = self.bindings.adapter_for_ref(binding_ref)
            await adapter.register_spawned_run(
                tenant_id=runtime_context["tenant_id"],
                user_id=runtime_context["user_id"],
                binding_ref=binding_ref,
                run_id=run_id,
                prompt=prompt,
                prompt_role="user",
            )
        return {
            "mode": "async",
            "run_id": str(run_id),
            "status": "queued",
            "worker_agent_slug": worker_agent_slug,
            "binding_ref": binding_ref.as_dict() if binding_ref else None,
            "lineage": result.get("lineage"),
            "effective_scope_subset": result.get("effective_scope_subset"),
        }

    async def spawn_group(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime_context = self.parse_runtime_context(payload)
        targets_raw = payload.get("targets")
        if not isinstance(targets_raw, list) or not targets_raw:
            raise ValueError("targets is required")

        prepared_targets: list[dict[str, Any]] = []
        seen_binding_refs: set[tuple[str, str]] = set()
        for index, raw_target in enumerate(targets_raw):
            if not isinstance(raw_target, dict):
                raise ValueError(f"targets[{index}] must be an object")
            task = {
                "objective": raw_target.get("objective"),
                "context": raw_target.get("context"),
                "constraints": raw_target.get("constraints"),
                "success_criteria": raw_target.get("success_criteria"),
            }
            prompt = self._task_prompt(task)
            binding_ref = parse_binding_ref(raw_target.get("binding_ref")) if raw_target.get("binding_ref") is not None else None
            worker_agent_slug = str(raw_target.get("worker_agent_slug") or "").strip()
            binding_context: dict[str, Any] = {}
            if binding_ref is not None:
                key = (binding_ref.binding_type, binding_ref.binding_id)
                if key in seen_binding_refs:
                    raise RuntimeError("BINDING_RUN_ACTIVE")
                seen_binding_refs.add(key)
                adapter = self.bindings.adapter_for_ref(binding_ref)
                binding_context = await adapter.build_spawn_payload(
                    tenant_id=runtime_context["tenant_id"],
                    user_id=runtime_context["user_id"],
                    binding_ref=binding_ref,
                    prompt=prompt,
                    prompt_role="user",
                    task=task,
                )
                worker_agent_slug = worker_agent_slug or str(binding_context.get("worker_agent_slug") or "").strip()
            if not worker_agent_slug:
                raise ValueError(f"targets[{index}].worker_agent_slug is required")
            prepared_targets.append(
                {
                    "worker_agent_slug": worker_agent_slug,
                    "binding_ref": binding_ref,
                    "prompt": prompt,
                    "task": task,
                    "thread_id": binding_context.get("thread_id"),
                    "mapped_input_payload": (
                        binding_context.get("mapped_input_payload")
                        if isinstance(binding_context.get("mapped_input_payload"), dict)
                        else {
                            "input": prompt,
                            "messages": [],
                            "context": {"architect_worker_task": task},
                        }
                    ),
                }
            )

        result = await self.kernel.spawn_group(
            caller_run_id=runtime_context["caller_run_id"],
            parent_node_id="architect_worker_spawn_group",
            targets=[
                {
                    "target_agent_slug": target["worker_agent_slug"],
                    "mapped_input_payload": target["mapped_input_payload"],
                    "thread_id": target.get("thread_id"),
                }
                for target in prepared_targets
            ],
            failure_policy=str(payload.get("failure_policy") or "").strip() or None,
            join_mode=str(payload.get("join_mode") or "all").strip() or "all",
            quorum_threshold=int(payload.get("quorum_threshold")) if payload.get("quorum_threshold") is not None else None,
            timeout_s=int(payload.get("timeout_s")) if payload.get("timeout_s") is not None else None,
            scope_subset=self._default_scope_subset(runtime_context, payload.get("scope_subset")),
            idempotency_key_prefix=str(payload.get("idempotency_key_prefix") or "").strip()
            or self._stable_idempotency_key(
                caller_run_id=runtime_context["caller_run_id"],
                worker_agent_slug="group",
                task={"objective": "group"},
                binding_ref=None,
                explicit_key=None,
            ),
            start_background=True,
        )
        for run_id_raw, target in zip(result.get("spawned_run_ids") or [], prepared_targets):
            if target["binding_ref"] is None:
                continue
            adapter = self.bindings.adapter_for_ref(target["binding_ref"])
            await adapter.register_spawned_run(
                tenant_id=runtime_context["tenant_id"],
                user_id=runtime_context["user_id"],
                binding_ref=target["binding_ref"],
                run_id=UUID(str(run_id_raw)),
                prompt=target["prompt"],
                prompt_role="user",
            )
        return {
            "mode": "async",
            "orchestration_group_id": result.get("orchestration_group_id"),
            "run_ids": result.get("spawned_run_ids") or [],
            "join_mode": result.get("join_mode"),
            "lineage": result.get("lineage"),
            "effective_scope_subset": result.get("effective_scope_subset"),
        }

    async def get_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime_context = self.parse_runtime_context(payload)
        run_id_raw = payload.get("run_id")
        if run_id_raw in (None, ""):
            raise ValueError("run_id is required")
        run = await self._resolve_child_run(
            tenant_id=runtime_context["tenant_id"],
            caller_run_id=runtime_context["caller_run_id"],
            run_id=UUID(str(run_id_raw)),
        )
        return await self._serialize_run_view(run)

    async def await_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime_context = self.parse_runtime_context(payload)
        run_id_raw = payload.get("run_id")
        if run_id_raw in (None, ""):
            raise ValueError("run_id is required")
        timeout_s = float(payload.get("timeout_s") or 45)
        timeout_s = max(1.0, min(timeout_s, 300.0))
        poll_interval_s = float(payload.get("poll_interval_s") or 1.5)
        poll_interval_s = max(0.2, min(poll_interval_s, 10.0))
        deadline = asyncio.get_running_loop().time() + timeout_s

        while True:
            run = await self._resolve_child_run(
                tenant_id=runtime_context["tenant_id"],
                caller_run_id=runtime_context["caller_run_id"],
                run_id=UUID(str(run_id_raw)),
            )
            view = await self._serialize_run_view(run)
            if view["lifecycle_state"] in {"completed", "terminal_error", "waiting_for_input"}:
                view["await_timed_out"] = False
                return view
            if asyncio.get_running_loop().time() >= deadline:
                view["await_timed_out"] = True
                return view
            await asyncio.sleep(poll_interval_s)

    async def respond_to_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime_context = self.parse_runtime_context(payload)
        run_id_raw = payload.get("run_id")
        if run_id_raw in (None, ""):
            raise ValueError("run_id is required")
        response = str(payload.get("response") or "").strip()
        if not response:
            raise ValueError("response is required")

        run = await self._resolve_child_run(
            tenant_id=runtime_context["tenant_id"],
            caller_run_id=runtime_context["caller_run_id"],
            run_id=UUID(str(run_id_raw)),
        )
        waiting_state = self._extract_waiting_state(run)
        self._record_trace_event(
            runtime_context["caller_run_id"],
            "architect.worker_respond.received",
            {
                "target_run_id": str(run.id),
                "target_run_status": str(getattr(run.status, "value", run.status)),
                "target_thread_id": str(run.thread_id) if run.thread_id else None,
                "waiting_state": waiting_state,
            },
        )
        self._record_trace_event(
            run.id,
            "architect.worker_respond.received",
            {
                "caller_run_id": str(runtime_context["caller_run_id"]),
                "target_run_status": str(getattr(run.status, "value", run.status)),
                "target_thread_id": str(run.thread_id) if run.thread_id else None,
            },
        )
        status = str(getattr(run.status, "value", run.status))
        if status == RunStatus.paused.value:
            if waiting_state is None:
                raise ValueError("Paused run is not waiting for input")
            self._record_trace_event(
                runtime_context["caller_run_id"],
                "architect.worker_respond.resume_requested",
                {
                    "target_run_id": str(run.id),
                    "target_thread_id": str(run.thread_id) if run.thread_id else None,
                },
            )
            self._record_trace_event(
                run.id,
                "architect.worker_respond.resume_requested",
                {
                    "caller_run_id": str(runtime_context["caller_run_id"]),
                    "target_thread_id": str(run.thread_id) if run.thread_id else None,
                },
            )
            await AgentExecutorService(self.db).resume_run(
                run.id,
                {"input": response, "message": response},
                background=True,
            )
            refreshed = await self.db.get(AgentRun, run.id)
            return await self._serialize_run_view(refreshed or run)

        if status in {
            RunStatus.completed.value,
            RunStatus.failed.value,
            RunStatus.cancelled.value,
        }:
            return await self._continue_binding_conversation(
                runtime_context=runtime_context,
                prior_run=run,
                response=response,
            )

        if waiting_state is None:
            raise ValueError("Run is not waiting for input")

        return await self._continue_binding_conversation(
            runtime_context=runtime_context,
            prior_run=run,
            response=response,
        )

    async def join_group(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime_context = self.parse_runtime_context(payload)
        group_id_raw = payload.get("orchestration_group_id")
        if group_id_raw in (None, ""):
            raise ValueError("orchestration_group_id is required")
        return await self.kernel.join(
            caller_run_id=runtime_context["caller_run_id"],
            orchestration_group_id=UUID(str(group_id_raw)),
            mode=str(payload.get("mode") or "").strip() or None,
            quorum_threshold=int(payload.get("quorum_threshold")) if payload.get("quorum_threshold") is not None else None,
            timeout_s=int(payload.get("timeout_s")) if payload.get("timeout_s") is not None else None,
        )

    async def cancel(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime_context = self.parse_runtime_context(payload)
        run_id_raw = payload.get("run_id")
        if run_id_raw in (None, ""):
            raise ValueError("run_id is required")
        return await self.kernel.cancel_subtree(
            caller_run_id=runtime_context["caller_run_id"],
            run_id=UUID(str(run_id_raw)),
            include_root=bool(payload.get("include_root", True)),
            reason=str(payload.get("reason") or "").strip() or None,
        )
