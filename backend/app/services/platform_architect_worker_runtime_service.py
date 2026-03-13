from __future__ import annotations

from hashlib import sha256
import json
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

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


class PlatformArchitectWorkerRuntimeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.kernel = OrchestrationKernelService(db)
        self.bindings = PlatformArchitectWorkerBindingService(db)

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

    async def prepare_binding(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime_context = self.parse_runtime_context(payload)
        binding_type = str(payload.get("binding_type") or "").strip()
        if not binding_type:
            raise ValueError("binding_type is required")
        binding_payload = payload.get("binding_payload") if isinstance(payload.get("binding_payload"), dict) else {}
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

    async def spawn_worker(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime_context = self.parse_runtime_context(payload)
        task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
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
            )
            worker_agent_slug = worker_agent_slug or str(binding_context.get("worker_agent_slug") or "").strip()
        if not worker_agent_slug:
            raise ValueError("worker_agent_slug is required")

        child_context = {
            **(binding_context.get("context") if isinstance(binding_context.get("context"), dict) else {}),
            "architect_worker_task": task,
        }
        result = await self.kernel.spawn_run(
            caller_run_id=runtime_context["caller_run_id"],
            parent_node_id="architect_worker_spawn",
            target_agent_id=None,
            target_agent_slug=worker_agent_slug,
            mapped_input_payload={
                "input": prompt,
                "messages": [],
                "context": child_context,
            },
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
        )
        run_id = UUID(result["spawned_run_ids"][0])
        if binding_ref is not None:
            adapter = self.bindings.adapter_for_ref(binding_ref)
            await adapter.register_spawned_run(
                tenant_id=runtime_context["tenant_id"],
                user_id=runtime_context["user_id"],
                binding_ref=binding_ref,
                run_id=run_id,
                user_prompt=prompt,
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
            task = raw_target.get("task") if isinstance(raw_target.get("task"), dict) else {}
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
                    "mapped_input_payload": {
                        "input": prompt,
                        "messages": [],
                        "context": {
                            **(binding_context.get("context") if isinstance(binding_context.get("context"), dict) else {}),
                            "architect_worker_task": task,
                        },
                    },
                }
            )

        result = await self.kernel.spawn_group(
            caller_run_id=runtime_context["caller_run_id"],
            parent_node_id="architect_worker_spawn_group",
            targets=[
                {
                    "target_agent_slug": target["worker_agent_slug"],
                    "mapped_input_payload": target["mapped_input_payload"],
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
                user_prompt=target["prompt"],
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
        run = await self.db.get(AgentRun, UUID(str(run_id_raw)))
        if run is None or run.tenant_id != runtime_context["tenant_id"]:
            raise ValueError("Run not found")
        caller_run = await self.db.get(AgentRun, runtime_context["caller_run_id"])
        if caller_run is None:
            raise ValueError("Caller run not found")
        valid_root = caller_run.root_run_id or caller_run.id
        if (run.root_run_id or run.id) != valid_root and run.parent_run_id != caller_run.id:
            raise ValueError("Run is outside caller orchestration tree")
        input_context = run.input_params.get("context") if isinstance(run.input_params, dict) else {}
        binding_ref = input_context.get("architect_worker_binding_ref") if isinstance(input_context, dict) else None
        return {
            "run_id": str(run.id),
            "status": str(getattr(run.status, "value", run.status)),
            "worker_agent_id": str(run.agent_id),
            "binding_ref": binding_ref if isinstance(binding_ref, dict) else None,
            "error": run.error_message,
            "completed_at": run.completed_at,
            "created_at": run.created_at,
            "output": run.output_result if isinstance(run.output_result, dict) else None,
            "lineage": self.kernel._serialize_lineage(run),
        }

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
