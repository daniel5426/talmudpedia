from __future__ import annotations

from typing import Any
from uuid import UUID

from app.services.control_plane.contracts import OperationResult
from app.services.control_plane.errors import not_found, validation
from app.services.orchestration_kernel_service import OrchestrationKernelService


class OrchestrationAdminService:
    def __init__(self, db):
        self.db = db
        self.kernel = OrchestrationKernelService(db)

    async def spawn_run(
        self,
        *,
        caller_run_id: UUID | None,
        parent_node_id: str | None,
        target_agent_id: UUID | None,
        target_agent_slug: str | None,
        mapped_input_payload: dict[str, Any],
        failure_policy: str | None,
        timeout_s: int | None,
        scope_subset: list[str],
        idempotency_key: str | None,
        start_background: bool,
    ) -> dict[str, Any]:
        if caller_run_id is None:
            raise validation("caller_run_id is required", field="caller_run_id")
        if not str(idempotency_key or "").strip():
            raise validation("idempotency_key is required", field="idempotency_key")
        return await self.kernel.spawn_run(
            caller_run_id=caller_run_id,
            parent_node_id=parent_node_id,
            target_agent_id=target_agent_id,
            target_agent_slug=target_agent_slug,
            mapped_input_payload=mapped_input_payload,
            failure_policy=failure_policy,
            timeout_s=timeout_s,
            scope_subset=scope_subset,
            idempotency_key=str(idempotency_key),
            start_background=start_background,
        )

    async def spawn_group(
        self,
        *,
        caller_run_id: UUID | None,
        parent_node_id: str | None,
        targets: list[dict[str, Any]],
        failure_policy: str | None,
        join_mode: str,
        quorum_threshold: int | None,
        timeout_s: int | None,
        scope_subset: list[str],
        idempotency_key_prefix: str | None,
        start_background: bool,
    ) -> dict[str, Any]:
        if caller_run_id is None:
            raise validation("caller_run_id is required", field="caller_run_id")
        if not str(idempotency_key_prefix or "").strip():
            raise validation("idempotency_key_prefix is required", field="idempotency_key_prefix")
        return await self.kernel.spawn_group(
            caller_run_id=caller_run_id,
            parent_node_id=parent_node_id,
            targets=targets,
            failure_policy=failure_policy,
            join_mode=join_mode,
            quorum_threshold=quorum_threshold,
            timeout_s=timeout_s,
            scope_subset=scope_subset,
            idempotency_key_prefix=str(idempotency_key_prefix),
            start_background=start_background,
        )

    async def join(
        self,
        *,
        caller_run_id: UUID | None,
        orchestration_group_id: UUID | None,
        mode: str | None,
        quorum_threshold: int | None,
        timeout_s: int | None,
    ) -> dict[str, Any]:
        if caller_run_id is None:
            raise validation("caller_run_id is required", field="caller_run_id")
        if orchestration_group_id is None:
            raise validation("orchestration_group_id is required", field="orchestration_group_id")
        result = await self.kernel.join(
            caller_run_id=caller_run_id,
            orchestration_group_id=orchestration_group_id,
            mode=mode,
            quorum_threshold=quorum_threshold,
            timeout_s=timeout_s,
        )
        return OperationResult(
            operation_id=str(orchestration_group_id),
            kind="orchestration_group",
            status=str(result.get("status") or "unknown"),
            result=result,
        ).to_dict()

    async def cancel_subtree(
        self,
        *,
        caller_run_id: UUID | None,
        run_id: UUID | None,
        include_root: bool,
        reason: str | None,
    ) -> dict[str, Any]:
        if caller_run_id is None:
            raise validation("caller_run_id is required", field="caller_run_id")
        if run_id is None:
            raise validation("run_id is required", field="run_id")
        result = await self.kernel.cancel_subtree(
            caller_run_id=caller_run_id,
            run_id=run_id,
            include_root=include_root,
            reason=reason,
        )
        return OperationResult(
            operation_id=str(run_id),
            kind="agent_run",
            status="cancel_requested",
            result=result,
        ).to_dict()

    async def evaluate_and_replan(
        self,
        *,
        caller_run_id: UUID | None,
        run_id: UUID | None,
    ) -> dict[str, Any]:
        if caller_run_id is None:
            raise validation("caller_run_id is required", field="caller_run_id")
        if run_id is None:
            raise validation("run_id is required", field="run_id")
        result = await self.kernel.evaluate_and_replan(
            caller_run_id=caller_run_id,
            run_id=run_id,
        )
        return OperationResult(
            operation_id=str(run_id),
            kind="agent_run",
            status=str(result.get("status") or "unknown"),
            result=result,
        ).to_dict()

    async def query_tree(self, *, run_id: UUID | None) -> dict[str, Any]:
        if run_id is None:
            raise not_found("Run not found")
        return await self.kernel.query_tree(run_id=run_id)
