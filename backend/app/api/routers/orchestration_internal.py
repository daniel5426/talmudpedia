from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.session import get_db
from app.services.orchestration_kernel_service import (
    OrchestrationKernelService,
    OrchestrationPolicyError,
)
from app.services.orchestration_policy_service import (
    ORCHESTRATION_SURFACE_OPTION_B,
    is_orchestration_surface_enabled,
)


router = APIRouter(prefix="/internal/orchestration", tags=["internal-orchestration"])


class SpawnRunRequest(BaseModel):
    caller_run_id: UUID
    parent_node_id: Optional[str] = None
    target_agent_id: Optional[UUID] = None
    target_agent_slug: Optional[str] = None
    mapped_input_payload: dict[str, Any] = Field(default_factory=dict)
    failure_policy: Optional[str] = None
    timeout_s: Optional[int] = None
    scope_subset: list[str] = Field(default_factory=list)
    idempotency_key: str
    start_background: bool = True


class SpawnGroupTarget(BaseModel):
    target_agent_id: Optional[UUID] = None
    target_agent_slug: Optional[str] = None
    mapped_input_payload: dict[str, Any] = Field(default_factory=dict)


class SpawnGroupRequest(BaseModel):
    caller_run_id: UUID
    parent_node_id: Optional[str] = None
    targets: list[SpawnGroupTarget] = Field(default_factory=list)
    failure_policy: Optional[str] = None
    join_mode: str = "all"
    quorum_threshold: Optional[int] = None
    timeout_s: Optional[int] = None
    scope_subset: list[str] = Field(default_factory=list)
    idempotency_key_prefix: str
    start_background: bool = True


class JoinRequest(BaseModel):
    caller_run_id: UUID
    orchestration_group_id: UUID
    mode: Optional[str] = None
    quorum_threshold: Optional[int] = None
    timeout_s: Optional[int] = None


class CancelSubtreeRequest(BaseModel):
    caller_run_id: UUID
    run_id: UUID
    include_root: bool = True
    reason: Optional[str] = None


class EvaluateAndReplanRequest(BaseModel):
    caller_run_id: UUID
    run_id: UUID


def _assert_tenant(principal: dict[str, Any], tenant_id: UUID | str) -> None:
    principal_tenant = principal.get("tenant_id")
    principal_scopes = set(principal.get("scopes") or [])
    if "*" in principal_scopes:
        return
    if str(principal_tenant) != str(tenant_id):
        raise HTTPException(status_code=403, detail="Tenant mismatch")


def _assert_option_b_enabled(tenant_id: UUID | str) -> None:
    if is_orchestration_surface_enabled(
        surface=ORCHESTRATION_SURFACE_OPTION_B,
        tenant_id=tenant_id,
    ):
        return
    raise HTTPException(
        status_code=403,
        detail="Runtime orchestration primitives are disabled by feature flag for this tenant",
    )


@router.post("/spawn-run")
async def spawn_run(
    request: SpawnRunRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("agents.execute")),
    db: AsyncSession = Depends(get_db),
):
    kernel = OrchestrationKernelService(db)
    try:
        caller = await kernel._require_run(request.caller_run_id)
        _assert_tenant(principal, caller.tenant_id)
        _assert_option_b_enabled(caller.tenant_id)

        return await kernel.spawn_run(
            caller_run_id=request.caller_run_id,
            parent_node_id=request.parent_node_id,
            target_agent_id=request.target_agent_id,
            target_agent_slug=request.target_agent_slug,
            mapped_input_payload=request.mapped_input_payload,
            failure_policy=request.failure_policy,
            timeout_s=request.timeout_s,
            scope_subset=request.scope_subset,
            idempotency_key=request.idempotency_key,
            start_background=request.start_background,
        )
    except OrchestrationPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/spawn-group")
async def spawn_group(
    request: SpawnGroupRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("agents.execute")),
    db: AsyncSession = Depends(get_db),
):
    kernel = OrchestrationKernelService(db)
    try:
        caller = await kernel._require_run(request.caller_run_id)
        _assert_tenant(principal, caller.tenant_id)
        _assert_option_b_enabled(caller.tenant_id)

        return await kernel.spawn_group(
            caller_run_id=request.caller_run_id,
            parent_node_id=request.parent_node_id,
            targets=[t.model_dump() for t in request.targets],
            failure_policy=request.failure_policy,
            join_mode=request.join_mode,
            quorum_threshold=request.quorum_threshold,
            timeout_s=request.timeout_s,
            scope_subset=request.scope_subset,
            idempotency_key_prefix=request.idempotency_key_prefix,
            start_background=request.start_background,
        )
    except OrchestrationPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/join")
async def join(
    request: JoinRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("agents.execute")),
    db: AsyncSession = Depends(get_db),
):
    kernel = OrchestrationKernelService(db)
    try:
        caller = await kernel._require_run(request.caller_run_id)
        _assert_tenant(principal, caller.tenant_id)
        _assert_option_b_enabled(caller.tenant_id)

        return await kernel.join(
            caller_run_id=request.caller_run_id,
            orchestration_group_id=request.orchestration_group_id,
            mode=request.mode,
            quorum_threshold=request.quorum_threshold,
            timeout_s=request.timeout_s,
        )
    except OrchestrationPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/cancel-subtree")
async def cancel_subtree(
    request: CancelSubtreeRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("agents.execute")),
    db: AsyncSession = Depends(get_db),
):
    kernel = OrchestrationKernelService(db)
    try:
        caller = await kernel._require_run(request.caller_run_id)
        _assert_tenant(principal, caller.tenant_id)
        _assert_option_b_enabled(caller.tenant_id)

        return await kernel.cancel_subtree(
            caller_run_id=request.caller_run_id,
            run_id=request.run_id,
            include_root=request.include_root,
            reason=request.reason,
        )
    except OrchestrationPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/evaluate-and-replan")
async def evaluate_and_replan(
    request: EvaluateAndReplanRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("agents.execute")),
    db: AsyncSession = Depends(get_db),
):
    kernel = OrchestrationKernelService(db)
    try:
        caller = await kernel._require_run(request.caller_run_id)
        _assert_tenant(principal, caller.tenant_id)
        _assert_option_b_enabled(caller.tenant_id)

        return await kernel.evaluate_and_replan(
            caller_run_id=request.caller_run_id,
            run_id=request.run_id,
        )
    except OrchestrationPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/runs/{run_id}/tree")
async def query_tree(
    run_id: UUID,
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("agents.execute")),
    db: AsyncSession = Depends(get_db),
):
    kernel = OrchestrationKernelService(db)
    try:
        run = await kernel._require_run(run_id)
        _assert_tenant(principal, run.tenant_id)
        _assert_option_b_enabled(run.tenant_id)
        return await kernel.query_tree(run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
