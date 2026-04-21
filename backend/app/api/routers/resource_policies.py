from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_principal, require_scopes
from app.db.postgres.models.agents import Agent
from app.db.postgres.models.identity import OrgMembership
from app.db.postgres.models.published_apps import PublishedApp, PublishedAppAccount
from app.db.postgres.models.resource_policies import (
    ResourcePolicyAssignment,
    ResourcePolicyPrincipalType,
    ResourcePolicyQuotaUnit,
    ResourcePolicyQuotaWindow,
    ResourcePolicyResourceType,
    ResourcePolicyRule,
    ResourcePolicyRuleType,
    ResourcePolicySet,
    ResourcePolicySetInclude,
)
from app.db.postgres.session import get_db
from app.services.resource_policy_service import ResourcePolicyError, ResourcePolicyService


router = APIRouter(prefix="/admin/security/resource-policies", tags=["resource-policies"])


class ResourcePolicySetCreateRequest(BaseModel):
    name: str
    description: str | None = None
    is_active: bool = True


class ResourcePolicySetUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class ResourcePolicyIncludeRequest(BaseModel):
    included_policy_set_id: UUID


class ResourcePolicyRuleCreateRequest(BaseModel):
    resource_type: ResourcePolicyResourceType
    resource_id: str
    rule_type: ResourcePolicyRuleType
    quota_unit: ResourcePolicyQuotaUnit | None = None
    quota_window: ResourcePolicyQuotaWindow | None = None
    quota_limit: int | None = None


class ResourcePolicyRuleUpdateRequest(BaseModel):
    resource_id: str | None = None
    quota_unit: ResourcePolicyQuotaUnit | None = None
    quota_window: ResourcePolicyQuotaWindow | None = None
    quota_limit: int | None = None


class ResourcePolicyAssignmentUpsertRequest(BaseModel):
    principal_type: ResourcePolicyPrincipalType
    policy_set_id: UUID
    user_id: UUID | None = None
    published_app_account_id: UUID | None = None
    embedded_agent_id: UUID | None = None
    external_user_id: str | None = None


class DefaultPolicySetUpdateRequest(BaseModel):
    policy_set_id: UUID | None = None


class ResourcePolicyRuleResponse(BaseModel):
    id: UUID
    resource_type: ResourcePolicyResourceType
    resource_id: str
    rule_type: ResourcePolicyRuleType
    quota_unit: ResourcePolicyQuotaUnit | None = None
    quota_window: ResourcePolicyQuotaWindow | None = None
    quota_limit: int | None = None
    created_at: datetime
    updated_at: datetime


class ResourcePolicySetResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_active: bool
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    included_policy_set_ids: list[UUID] = Field(default_factory=list)
    rules: list[ResourcePolicyRuleResponse] = Field(default_factory=list)


class ResourcePolicyAssignmentResponse(BaseModel):
    id: UUID
    principal_type: ResourcePolicyPrincipalType
    policy_set_id: UUID
    user_id: UUID | None = None
    published_app_account_id: UUID | None = None
    embedded_agent_id: UUID | None = None
    external_user_id: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


def _principal_organization_id(principal: dict[str, Any]) -> UUID:
    if principal.get("type") != "user":
        raise HTTPException(status_code=403, detail="Only users can manage resource policies")
    try:
        return UUID(str(principal["organization_id"]))
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Organization context required") from exc


def _serialize_rule(rule: ResourcePolicyRule) -> ResourcePolicyRuleResponse:
    return ResourcePolicyRuleResponse(
        id=rule.id,
        resource_type=rule.resource_type,
        resource_id=rule.resource_id,
        rule_type=rule.rule_type,
        quota_unit=rule.quota_unit,
        quota_window=rule.quota_window,
        quota_limit=rule.quota_limit,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _serialize_assignment(assignment: ResourcePolicyAssignment) -> ResourcePolicyAssignmentResponse:
    return ResourcePolicyAssignmentResponse(
        id=assignment.id,
        principal_type=assignment.principal_type,
        policy_set_id=assignment.policy_set_id,
        user_id=assignment.user_id,
        published_app_account_id=assignment.published_app_account_id,
        embedded_agent_id=assignment.embedded_agent_id,
        external_user_id=assignment.external_user_id,
        created_by=assignment.created_by,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
    )


async def _get_policy_set_or_404(db: AsyncSession, *, organization_id: UUID, policy_set_id: UUID) -> ResourcePolicySet:
    policy_set = await db.get(ResourcePolicySet, policy_set_id)
    if policy_set is None or policy_set.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Policy set not found")
    return policy_set


async def _serialize_policy_set(db: AsyncSession, policy_set: ResourcePolicySet) -> ResourcePolicySetResponse:
    include_result = await db.execute(
        select(ResourcePolicySetInclude).where(ResourcePolicySetInclude.parent_policy_set_id == policy_set.id)
    )
    rule_result = await db.execute(select(ResourcePolicyRule).where(ResourcePolicyRule.policy_set_id == policy_set.id))
    return ResourcePolicySetResponse(
        id=policy_set.id,
        name=policy_set.name,
        description=policy_set.description,
        is_active=policy_set.is_active,
        created_by=policy_set.created_by,
        created_at=policy_set.created_at,
        updated_at=policy_set.updated_at,
        included_policy_set_ids=[row.included_policy_set_id for row in include_result.scalars().all()],
        rules=[_serialize_rule(rule) for rule in rule_result.scalars().all()],
    )


def _apply_assignment_scope_filters(stmt, request: ResourcePolicyAssignmentUpsertRequest):
    if request.principal_type == ResourcePolicyPrincipalType.ORGANIZATION_USER:
        if request.user_id is None:
            raise HTTPException(status_code=400, detail="user_id is required for organization_user assignments")
        return stmt.where(ResourcePolicyAssignment.user_id == request.user_id)
    if request.principal_type == ResourcePolicyPrincipalType.PUBLISHED_APP_ACCOUNT:
        if request.published_app_account_id is None:
            raise HTTPException(status_code=400, detail="published_app_account_id is required for published_app_account assignments")
        return stmt.where(ResourcePolicyAssignment.published_app_account_id == request.published_app_account_id)
    if request.embedded_agent_id is None or not str(request.external_user_id or "").strip():
        raise HTTPException(status_code=400, detail="embedded_agent_id and external_user_id are required for embedded assignments")
    return stmt.where(
        ResourcePolicyAssignment.embedded_agent_id == request.embedded_agent_id,
        ResourcePolicyAssignment.external_user_id == str(request.external_user_id).strip(),
    )


async def _validate_assignment_principal_scope(
    db: AsyncSession,
    *,
    organization_id: UUID,
    request: ResourcePolicyAssignmentUpsertRequest,
) -> None:
    if request.principal_type == ResourcePolicyPrincipalType.ORGANIZATION_USER:
        membership_id = await db.scalar(
            select(OrgMembership.id).where(
                OrgMembership.organization_id == organization_id,
                OrgMembership.user_id == request.user_id,
            ).limit(1)
        )
        if membership_id is None:
            raise HTTPException(status_code=404, detail="Organization user not found")
        return

    if request.principal_type == ResourcePolicyPrincipalType.PUBLISHED_APP_ACCOUNT:
        account_id = await db.scalar(
            select(PublishedAppAccount.id)
            .join(PublishedApp, PublishedApp.id == PublishedAppAccount.published_app_id)
            .where(
                PublishedAppAccount.id == request.published_app_account_id,
                PublishedApp.organization_id == organization_id,
            )
            .limit(1)
        )
        if account_id is None:
            raise HTTPException(status_code=404, detail="Published app account not found")
        return

    agent_id = await db.scalar(
        select(Agent.id).where(
            Agent.id == request.embedded_agent_id,
            Agent.organization_id == organization_id,
        ).limit(1)
    )
    if agent_id is None:
        raise HTTPException(status_code=404, detail="Embedded agent not found")


@router.get("/sets", response_model=list[ResourcePolicySetResponse], dependencies=[Depends(require_scopes("roles.read"))])
async def list_policy_sets(
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[ResourcePolicySetResponse]:
    organization_id= _principal_organization_id(principal)
    result = await db.execute(
        select(ResourcePolicySet)
        .where(ResourcePolicySet.organization_id == organization_id)
        .order_by(ResourcePolicySet.created_at.asc())
    )
    return [await _serialize_policy_set(db, policy_set) for policy_set in result.scalars().all()]


@router.post("/sets", response_model=ResourcePolicySetResponse, dependencies=[Depends(require_scopes("roles.write"))], status_code=status.HTTP_201_CREATED)
async def create_policy_set(
    request: ResourcePolicySetCreateRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> ResourcePolicySetResponse:
    organization_id= _principal_organization_id(principal)
    actor_user_id = UUID(str(principal["user_id"]))
    policy_set = ResourcePolicySet(
        organization_id=organization_id,
        name=request.name.strip(),
        description=request.description,
        is_active=request.is_active,
        created_by=actor_user_id,
    )
    db.add(policy_set)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Policy set name already exists") from exc
    await db.refresh(policy_set)
    return await _serialize_policy_set(db, policy_set)


@router.get("/sets/{policy_set_id}", response_model=ResourcePolicySetResponse, dependencies=[Depends(require_scopes("roles.read"))])
async def get_policy_set(
    policy_set_id: UUID,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> ResourcePolicySetResponse:
    organization_id= _principal_organization_id(principal)
    return await _serialize_policy_set(db, await _get_policy_set_or_404(db, organization_id=organization_id, policy_set_id=policy_set_id))


@router.patch("/sets/{policy_set_id}", response_model=ResourcePolicySetResponse, dependencies=[Depends(require_scopes("roles.write"))])
async def update_policy_set(
    policy_set_id: UUID,
    request: ResourcePolicySetUpdateRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> ResourcePolicySetResponse:
    organization_id= _principal_organization_id(principal)
    policy_set = await _get_policy_set_or_404(db, organization_id=organization_id, policy_set_id=policy_set_id)
    if request.name is not None:
        policy_set.name = request.name.strip()
    if request.description is not None:
        policy_set.description = request.description
    if request.is_active is not None:
        policy_set.is_active = request.is_active
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Policy set name already exists") from exc
    await db.refresh(policy_set)
    return await _serialize_policy_set(db, policy_set)


@router.delete("/sets/{policy_set_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_scopes("roles.write"))])
async def delete_policy_set(
    policy_set_id: UUID,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    organization_id= _principal_organization_id(principal)
    policy_set = await _get_policy_set_or_404(db, organization_id=organization_id, policy_set_id=policy_set_id)
    await db.delete(policy_set)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sets/{policy_set_id}/includes", response_model=ResourcePolicySetResponse, dependencies=[Depends(require_scopes("roles.write"))])
async def add_policy_set_include(
    policy_set_id: UUID,
    request: ResourcePolicyIncludeRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> ResourcePolicySetResponse:
    organization_id= _principal_organization_id(principal)
    await _get_policy_set_or_404(db, organization_id=organization_id, policy_set_id=policy_set_id)
    await _get_policy_set_or_404(db, organization_id=organization_id, policy_set_id=request.included_policy_set_id)
    include = ResourcePolicySetInclude(
        parent_policy_set_id=policy_set_id,
        included_policy_set_id=request.included_policy_set_id,
    )
    db.add(include)
    service = ResourcePolicyService(db)
    try:
        await db.flush()
        await service.validate_policy_set_graph(organization_id=organization_id, policy_set_id=policy_set_id)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Policy include already exists") from exc
    except ResourcePolicyError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _serialize_policy_set(db, await _get_policy_set_or_404(db, organization_id=organization_id, policy_set_id=policy_set_id))


@router.delete("/sets/{policy_set_id}/includes/{included_policy_set_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_scopes("roles.write"))])
async def remove_policy_set_include(
    policy_set_id: UUID,
    included_policy_set_id: UUID,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    organization_id= _principal_organization_id(principal)
    await _get_policy_set_or_404(db, organization_id=organization_id, policy_set_id=policy_set_id)
    result = await db.execute(
        select(ResourcePolicySetInclude).where(
            and_(
                ResourcePolicySetInclude.parent_policy_set_id == policy_set_id,
                ResourcePolicySetInclude.included_policy_set_id == included_policy_set_id,
            )
        )
    )
    include = result.scalar_one_or_none()
    if include is None:
        raise HTTPException(status_code=404, detail="Policy include not found")
    await db.delete(include)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sets/{policy_set_id}/rules", response_model=ResourcePolicyRuleResponse, dependencies=[Depends(require_scopes("roles.write"))], status_code=status.HTTP_201_CREATED)
async def create_policy_rule(
    policy_set_id: UUID,
    request: ResourcePolicyRuleCreateRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> ResourcePolicyRuleResponse:
    organization_id= _principal_organization_id(principal)
    await _get_policy_set_or_404(db, organization_id=organization_id, policy_set_id=policy_set_id)
    service = ResourcePolicyService(db)
    try:
        await service.validate_policy_rule(
            resource_type=request.resource_type,
            rule_type=request.rule_type,
            quota_limit=request.quota_limit,
            quota_unit=request.quota_unit,
            quota_window=request.quota_window,
        )
    except ResourcePolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    rule = ResourcePolicyRule(
        policy_set_id=policy_set_id,
        resource_type=request.resource_type,
        resource_id=request.resource_id.strip(),
        rule_type=request.rule_type,
        quota_unit=request.quota_unit,
        quota_window=request.quota_window,
        quota_limit=request.quota_limit,
    )
    db.add(rule)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Conflicting rule already exists") from exc
    await db.refresh(rule)
    return _serialize_rule(rule)


@router.patch("/rules/{rule_id}", response_model=ResourcePolicyRuleResponse, dependencies=[Depends(require_scopes("roles.write"))])
async def update_policy_rule(
    rule_id: UUID,
    request: ResourcePolicyRuleUpdateRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> ResourcePolicyRuleResponse:
    organization_id= _principal_organization_id(principal)
    result = await db.execute(
        select(ResourcePolicyRule, ResourcePolicySet)
        .join(ResourcePolicySet, ResourcePolicySet.id == ResourcePolicyRule.policy_set_id)
        .where(ResourcePolicyRule.id == rule_id, ResourcePolicySet.organization_id == organization_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Policy rule not found")
    rule = row[0]
    if request.resource_id is not None:
        rule.resource_id = request.resource_id.strip()
    if request.quota_unit is not None:
        rule.quota_unit = request.quota_unit
    if request.quota_window is not None:
        rule.quota_window = request.quota_window
    if request.quota_limit is not None:
        rule.quota_limit = request.quota_limit
    service = ResourcePolicyService(db)
    try:
        await service.validate_policy_rule(
            resource_type=rule.resource_type,
            rule_type=rule.rule_type,
            quota_limit=rule.quota_limit,
            quota_unit=rule.quota_unit,
            quota_window=rule.quota_window,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Conflicting rule already exists") from exc
    except ResourcePolicyError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.refresh(rule)
    return _serialize_rule(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_scopes("roles.write"))])
async def delete_policy_rule(
    rule_id: UUID,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    organization_id= _principal_organization_id(principal)
    result = await db.execute(
        select(ResourcePolicyRule, ResourcePolicySet)
        .join(ResourcePolicySet, ResourcePolicySet.id == ResourcePolicyRule.policy_set_id)
        .where(ResourcePolicyRule.id == rule_id, ResourcePolicySet.organization_id == organization_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Policy rule not found")
    await db.delete(row[0])
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/assignments", response_model=list[ResourcePolicyAssignmentResponse], dependencies=[Depends(require_scopes("roles.read"))])
async def list_assignments(
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[ResourcePolicyAssignmentResponse]:
    organization_id= _principal_organization_id(principal)
    result = await db.execute(
        select(ResourcePolicyAssignment)
        .where(ResourcePolicyAssignment.organization_id == organization_id)
        .order_by(ResourcePolicyAssignment.created_at.asc())
    )
    return [_serialize_assignment(item) for item in result.scalars().all()]


@router.put("/assignments", response_model=ResourcePolicyAssignmentResponse, dependencies=[Depends(require_scopes("roles.write"))])
async def upsert_assignment(
    request: ResourcePolicyAssignmentUpsertRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> ResourcePolicyAssignmentResponse:
    organization_id= _principal_organization_id(principal)
    actor_user_id = UUID(str(principal["user_id"]))
    await _get_policy_set_or_404(db, organization_id=organization_id, policy_set_id=request.policy_set_id)
    await _validate_assignment_principal_scope(db, organization_id=organization_id, request=request)
    stmt = select(ResourcePolicyAssignment).where(
        ResourcePolicyAssignment.organization_id == organization_id,
        ResourcePolicyAssignment.principal_type == request.principal_type,
    )
    stmt = _apply_assignment_scope_filters(stmt, request)
    result = await db.execute(stmt.limit(1))
    assignment = result.scalar_one_or_none()
    if assignment is None:
        assignment = ResourcePolicyAssignment(
            organization_id=organization_id,
            principal_type=request.principal_type,
            policy_set_id=request.policy_set_id,
            user_id=request.user_id,
            published_app_account_id=request.published_app_account_id,
            embedded_agent_id=request.embedded_agent_id,
            external_user_id=str(request.external_user_id).strip() if request.external_user_id else None,
            created_by=actor_user_id,
        )
        db.add(assignment)
    else:
        assignment.policy_set_id = request.policy_set_id
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Assignment already exists for that principal") from exc
    await db.refresh(assignment)
    return _serialize_assignment(assignment)


@router.delete("/assignments", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_scopes("roles.write"))])
async def delete_assignment(
    principal_type: ResourcePolicyPrincipalType = Query(...),
    user_id: UUID | None = Query(None),
    published_app_account_id: UUID | None = Query(None),
    embedded_agent_id: UUID | None = Query(None),
    external_user_id: str | None = Query(None),
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    organization_id= _principal_organization_id(principal)
    stmt = select(ResourcePolicyAssignment).where(
        ResourcePolicyAssignment.organization_id == organization_id,
        ResourcePolicyAssignment.principal_type == principal_type,
    )
    if principal_type == ResourcePolicyPrincipalType.ORGANIZATION_USER:
        stmt = stmt.where(ResourcePolicyAssignment.user_id == user_id)
    elif principal_type == ResourcePolicyPrincipalType.PUBLISHED_APP_ACCOUNT:
        stmt = stmt.where(ResourcePolicyAssignment.published_app_account_id == published_app_account_id)
    else:
        stmt = stmt.where(
            ResourcePolicyAssignment.embedded_agent_id == embedded_agent_id,
            ResourcePolicyAssignment.external_user_id == str(external_user_id or "").strip(),
        )
    result = await db.execute(stmt.limit(1))
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    await db.delete(assignment)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/published-apps/{published_app_id}/default-policy-set", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_scopes("roles.write"))])
async def set_published_app_default_policy(
    published_app_id: UUID,
    request: DefaultPolicySetUpdateRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    organization_id= _principal_organization_id(principal)
    app = await db.get(PublishedApp, published_app_id)
    if app is None or app.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Published app not found")
    if request.policy_set_id is not None:
        await _get_policy_set_or_404(db, organization_id=organization_id, policy_set_id=request.policy_set_id)
    app.default_policy_set_id = request.policy_set_id
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/embedded-agents/{agent_id}/default-policy-set", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_scopes("roles.write"))])
async def set_embedded_agent_default_policy(
    agent_id: UUID,
    request: DefaultPolicySetUpdateRequest,
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    organization_id= _principal_organization_id(principal)
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    if request.policy_set_id is not None:
        await _get_policy_set_or_404(db, organization_id=organization_id, policy_set_id=request.policy_set_id)
    agent.default_embed_policy_set_id = request.policy_set_id
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
