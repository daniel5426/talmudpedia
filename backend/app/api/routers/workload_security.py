from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.models.security import (
    DelegationGrant,
    DelegationGrantStatus,
    ApprovalDecision,
    ApprovalStatus,
)
from app.db.postgres.session import get_db
from app.services.workload_identity_service import WorkloadIdentityService
from app.services.token_broker_service import TokenBrokerService


router = APIRouter(prefix="/admin/security/workloads", tags=["workload-security"])


class PolicyApprovalRequest(BaseModel):
    approved_scopes: list[str] = Field(default_factory=list)


class ActionApprovalDecisionRequest(BaseModel):
    subject_type: str
    subject_id: str
    action_scope: str
    status: ApprovalStatus
    rationale: str | None = None


@router.get("/pending")
async def list_pending_scope_policies(
    _: dict[str, Any] = Depends(require_scopes("tools.write")),
    principal_ctx: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if principal_ctx.get("type") != "user":
        raise HTTPException(status_code=403, detail="Only users can manage workload approvals")

    identity = WorkloadIdentityService(db)
    tenant_id = UUID(principal_ctx["tenant_id"])
    pending = await identity.list_pending_policies(tenant_id)

    return [
        {
            "policy_id": str(item.id),
            "principal_id": str(item.principal_id),
            "requested_scopes": item.requested_scopes or [],
            "status": item.status,
            "version": item.version,
            "created_at": item.created_at,
        }
        for item in pending
    ]


@router.post("/principals/{principal_id}/approve")
async def approve_scope_policy(
    principal_id: UUID,
    request: PolicyApprovalRequest,
    _: dict[str, Any] = Depends(require_scopes("tools.write")),
    principal_ctx: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if principal_ctx.get("type") != "user":
        raise HTTPException(status_code=403, detail="Only users can approve policies")

    identity = WorkloadIdentityService(db)
    approver_id = UUID(principal_ctx["user_id"])
    policy = await identity.approve_policy(
        principal_id=principal_id,
        approved_by=approver_id,
        approved_scopes=request.approved_scopes,
    )

    broker = TokenBrokerService(db)
    grants_res = await db.execute(
        select(DelegationGrant).where(
            DelegationGrant.principal_id == principal_id,
            DelegationGrant.status == DelegationGrantStatus.ACTIVE,
        )
    )
    for grant in grants_res.scalars().all():
        await broker.revoke_grant(grant.id, reason="policy_approved_new_version")

    await db.commit()
    return {
        "status": "approved",
        "principal_id": str(principal_id),
        "policy_id": str(policy.id),
        "approved_scopes": policy.approved_scopes,
        "approved_at": policy.approved_at or datetime.now(timezone.utc),
    }


@router.post("/principals/{principal_id}/reject")
async def reject_scope_policy(
    principal_id: UUID,
    _: dict[str, Any] = Depends(require_scopes("tools.write")),
    principal_ctx: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if principal_ctx.get("type") != "user":
        raise HTTPException(status_code=403, detail="Only users can reject policies")

    identity = WorkloadIdentityService(db)
    approver_id = UUID(principal_ctx["user_id"])
    policy = await identity.reject_policy(principal_id=principal_id, approved_by=approver_id)

    broker = TokenBrokerService(db)
    grants_res = await db.execute(
        select(DelegationGrant).where(
            DelegationGrant.principal_id == principal_id,
            DelegationGrant.status == DelegationGrantStatus.ACTIVE,
        )
    )
    for grant in grants_res.scalars().all():
        await broker.revoke_grant(grant.id, reason="policy_rejected")

    await db.commit()
    return {
        "status": "rejected",
        "principal_id": str(principal_id),
        "policy_id": str(policy.id),
    }


@router.get("/approvals")
async def list_action_approvals(
    subject_type: str | None = None,
    subject_id: str | None = None,
    action_scope: str | None = None,
    _: dict[str, Any] = Depends(require_scopes("tools.write")),
    principal_ctx: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if principal_ctx.get("type") != "user":
        raise HTTPException(status_code=403, detail="Only users can list action approvals")

    tenant_id = UUID(principal_ctx["tenant_id"])
    query = select(ApprovalDecision).where(ApprovalDecision.tenant_id == tenant_id)
    if subject_type:
        query = query.where(ApprovalDecision.subject_type == subject_type)
    if subject_id:
        query = query.where(ApprovalDecision.subject_id == subject_id)
    if action_scope:
        query = query.where(ApprovalDecision.action_scope == action_scope)
    query = query.order_by(ApprovalDecision.created_at.desc())

    result = await db.execute(query)
    rows = result.scalars().all()
    return [
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "subject_type": row.subject_type,
            "subject_id": row.subject_id,
            "action_scope": row.action_scope,
            "status": row.status,
            "decided_by": str(row.decided_by) if row.decided_by else None,
            "rationale": row.rationale,
            "created_at": row.created_at,
            "decided_at": row.decided_at,
        }
        for row in rows
    ]


@router.post("/approvals/decide")
async def decide_action_approval(
    request: ActionApprovalDecisionRequest,
    _: dict[str, Any] = Depends(require_scopes("tools.write")),
    principal_ctx: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if principal_ctx.get("type") != "user":
        raise HTTPException(status_code=403, detail="Only users can decide action approvals")

    tenant_id = UUID(principal_ctx["tenant_id"])
    decider_id = UUID(principal_ctx["user_id"])
    existing_res = await db.execute(
        select(ApprovalDecision)
        .where(
            ApprovalDecision.tenant_id == tenant_id,
            ApprovalDecision.subject_type == request.subject_type,
            ApprovalDecision.subject_id == request.subject_id,
            ApprovalDecision.action_scope == request.action_scope,
        )
        .order_by(ApprovalDecision.created_at.desc())
        .limit(1)
    )
    decision = existing_res.scalar_one_or_none()
    if decision is None:
        decision = ApprovalDecision(
            tenant_id=tenant_id,
            subject_type=request.subject_type,
            subject_id=request.subject_id,
            action_scope=request.action_scope,
            status=request.status,
            decided_by=decider_id,
            rationale=request.rationale,
            decided_at=datetime.now(timezone.utc),
        )
        db.add(decision)
    else:
        decision.status = request.status
        decision.decided_by = decider_id
        decision.rationale = request.rationale
        decision.decided_at = datetime.now(timezone.utc)

    await db.commit()
    return {
        "id": str(decision.id),
        "subject_type": decision.subject_type,
        "subject_id": decision.subject_id,
        "action_scope": decision.action_scope,
        "status": decision.status,
        "decided_by": str(decision.decided_by) if decision.decided_by else None,
        "rationale": decision.rationale,
        "decided_at": decision.decided_at,
    }
