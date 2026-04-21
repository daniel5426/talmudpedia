from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.session import get_db
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.errors import ControlPlaneError
from app.services.control_plane.orchestration_admin_service import OrchestrationAdminService
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
    target_agent_id: UUID
    mapped_input_payload: dict[str, Any] = Field(default_factory=dict)
    failure_policy: Optional[str] = None
    timeout_s: Optional[int] = None
    scope_subset: list[str] = Field(default_factory=list)
    idempotency_key: str
    start_background: bool = True


class SpawnGroupTarget(BaseModel):
    target_agent_id: UUID
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


def _assert_tenant(principal: dict[str, Any], organization_id: UUID | str) -> None:
    principal_tenant = principal.get("organization_id")
    principal_scopes = set(principal.get("scopes") or [])
    if "*" in principal_scopes:
        return
    if str(principal_tenant) != str(organization_id):
        raise HTTPException(status_code=403, detail="Organization mismatch")


def _assert_option_b_enabled(organization_id: UUID | str) -> None:
    if is_orchestration_surface_enabled(
        surface=ORCHESTRATION_SURFACE_OPTION_B,
        organization_id=organization_id,
    ):
        return
    raise HTTPException(
        status_code=403,
        detail="Runtime orchestration primitives are disabled by feature flag for this organization",
    )


def _control_plane_ctx(principal: dict[str, Any], organization_id: UUID | str) -> ControlPlaneContext:
    user = principal.get("user")
    return ControlPlaneContext(
        organization_id=UUID(str(organization_id)),
        user=user,
        user_id=getattr(user, "id", None),
        auth_token=principal.get("auth_token"),
        scopes=tuple(principal.get("scopes") or ()),
        is_service=bool(principal.get("type") == "workload"),
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
        _assert_tenant(principal, caller.organization_id)
        _assert_option_b_enabled(caller.organization_id)

        return await OrchestrationAdminService(db).spawn_run(
            caller_run_id=request.caller_run_id,
            parent_node_id=request.parent_node_id,
            target_agent_id=request.target_agent_id,
            mapped_input_payload=request.mapped_input_payload,
            failure_policy=request.failure_policy,
            timeout_s=request.timeout_s,
            scope_subset=request.scope_subset,
            idempotency_key=request.idempotency_key,
            start_background=request.start_background,
        )
    except OrchestrationPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc
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
        _assert_tenant(principal, caller.organization_id)
        _assert_option_b_enabled(caller.organization_id)

        return await OrchestrationAdminService(db).spawn_group(
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
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc
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
        _assert_tenant(principal, caller.organization_id)
        _assert_option_b_enabled(caller.organization_id)

        operation = await OrchestrationAdminService(db).join(
            caller_run_id=request.caller_run_id,
            orchestration_group_id=request.orchestration_group_id,
            mode=request.mode,
            quorum_threshold=request.quorum_threshold,
            timeout_s=request.timeout_s,
        )
        return operation["result"]
    except OrchestrationPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc
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
        _assert_tenant(principal, caller.organization_id)
        _assert_option_b_enabled(caller.organization_id)

        operation = await OrchestrationAdminService(db).cancel_subtree(
            caller_run_id=request.caller_run_id,
            run_id=request.run_id,
            include_root=request.include_root,
            reason=request.reason,
        )
        return operation["result"]
    except OrchestrationPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc
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
        _assert_tenant(principal, caller.organization_id)
        _assert_option_b_enabled(caller.organization_id)

        operation = await OrchestrationAdminService(db).evaluate_and_replan(
            caller_run_id=request.caller_run_id,
            run_id=request.run_id,
        )
        return operation["result"]
    except OrchestrationPolicyError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/runs/{run_id}/tree")
async def query_tree(
    run_id: UUID,
    principal: dict[str, Any] = Depends(get_current_principal),
    _: dict[str, Any] = Depends(require_scopes("agents.execute")),
    db: AsyncSession = Depends(get_db),
):
    try:
        kernel = OrchestrationKernelService(db)
        run = await kernel._require_run(run_id)
        _assert_tenant(principal, run.organization_id)
        _assert_option_b_enabled(run.organization_id)
        return await OrchestrationAdminService(db).query_tree(run_id=run_id)
    except ControlPlaneError as exc:
        raise exc.to_http_exception() from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
