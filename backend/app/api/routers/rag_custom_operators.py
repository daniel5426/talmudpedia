"""
Custom Operators Router - PostgreSQL implementation.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.session import get_db
from app.db.postgres.models.identity import User, Organization, OrgMembership
from app.db.postgres.models.operators import CustomOperator, OperatorCategory
from app.api.dependencies import get_current_principal, require_scopes
from app.api.routers.auth import get_current_user
from app.core.audit import log_simple_action
from app.api.schemas.rag import (
    CustomOperatorCreate, 
    CustomOperatorUpdate, 
    CustomOperatorResponse,
    CustomOperatorTestRequest,
    CustomOperatorTestResponse
)
from app.rag.pipeline.operator_executor import PythonOperatorExecutor, OperatorInput, ExecutionContext
from app.rag.pipeline.registry import OperatorSpec, DataType, OperatorCategory as RegistryCategory

router = APIRouter()

async def get_organization_context(
    organization_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    principal: dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    """Get organization context with user info."""
    if not organization_id:
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Organization context required")
        return None, current_user, db

    organization = await db.get(Organization, organization_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
        
    # Check membership
    membership_result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.organization_id == organization.id,
            OrgMembership.user_id == current_user.id
        )
    )
    membership = membership_result.scalar_one_or_none()
    if not membership and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not a member of this organization")
    scopes = set(principal.get("scopes") or [])
    if "*" not in scopes and str(organization.id) != str(principal.get("organization_id")):
        raise HTTPException(status_code=403, detail="Active organization does not match requested organization")
        
    return organization, current_user, db

@router.get("", response_model=List[CustomOperatorResponse])
async def list_custom_operators(
    organization_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    _: dict = Depends(require_scopes("pipelines.catalog.read")),
    db: AsyncSession = Depends(get_db),
):
    """List custom operators for the organization."""
    organization, user, db = await get_organization_context(organization_id, current_user, db)
    
    query = select(CustomOperator)
    if organization:
        query = query.where(CustomOperator.organization_id == organization.id)
    
    query = query.order_by(CustomOperator.updated_at.desc())
    result = await db.execute(query)
    operators = result.scalars().all()
    return operators

@router.post("", response_model=CustomOperatorResponse)
async def create_custom_operator(
    request: CustomOperatorCreate,
    http_request: Request,
    organization_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    _: dict = Depends(require_scopes("pipelines.write")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new custom operator."""
    organization, user, db = await get_organization_context(organization_id, current_user, db)
    if not organization:
         raise HTTPException(status_code=400, detail="Organization context required")
    
    # Check duplicate name in organization
    stmt = select(CustomOperator).where(
        CustomOperator.organization_id == organization.id,
        CustomOperator.name == request.name
    )
    existing = await db.scalar(stmt)
    if existing:
        raise HTTPException(status_code=400, detail="Operator with this name already exists")

    operator = CustomOperator(
        organization_id=organization.id,
        name=request.name,
        display_name=request.display_name,
        category=OperatorCategory(request.category), # Ensure enum
        description=request.description,
        python_code=request.python_code,
        input_type=request.input_type,
        output_type=request.output_type,
        config_schema=request.config_schema,
        created_by=user.id
    )
    
    db.add(operator)
    await db.commit()
    await db.refresh(operator)
    
    return operator

@router.get("/{operator_id}", response_model=CustomOperatorResponse)
async def get_custom_operator(
    operator_id: UUID,
    organization_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    _: dict = Depends(require_scopes("pipelines.catalog.read")),
    db: AsyncSession = Depends(get_db),
):
    """Get a custom operator by ID."""
    organization, user, db = await get_organization_context(organization_id, current_user, db)
    
    query = select(CustomOperator).where(CustomOperator.id == operator_id)
    if organization:
        query = query.where(CustomOperator.organization_id == organization.id)
        
    operator = await db.scalar(query)
    if not operator:
        raise HTTPException(status_code=404, detail="Operator not found")
        
    return operator

@router.put("/{operator_id}", response_model=CustomOperatorResponse)
async def update_custom_operator(
    operator_id: UUID,
    update_data: CustomOperatorUpdate,
    http_request: Request,
    organization_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    _: dict = Depends(require_scopes("pipelines.write")),
    db: AsyncSession = Depends(get_db),
):
    """Update a custom operator."""
    organization, user, db = await get_organization_context(organization_id, current_user, db)
    
    query = select(CustomOperator).where(CustomOperator.id == operator_id)
    if organization:
        query = query.where(CustomOperator.organization_id == organization.id)
        
    operator = await db.scalar(query)
    if not operator:
        raise HTTPException(status_code=404, detail="Operator not found")
    
    # Update fields
    data = update_data.dict(exclude_unset=True)
    for field, value in data.items():
        if field == 'category':
             value = OperatorCategory(value)
        setattr(operator, field, value)
        
    # Bump version slightly (simple logic for now)
    # In real world, might parse semantic version
    operator.version = f"{operator.version}.1" 
    operator.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(operator)
    
    return operator

@router.delete("/{operator_id}")
async def delete_custom_operator(
    operator_id: UUID,
    http_request: Request,
    organization_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    _: dict = Depends(require_scopes("pipelines.write")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a custom operator."""
    organization, user, db = await get_organization_context(organization_id, current_user, db)
    
    query = select(CustomOperator).where(CustomOperator.id == operator_id)
    if organization:
        query = query.where(CustomOperator.organization_id == organization.id)
        
    operator = await db.scalar(query)
    if not operator:
        raise HTTPException(status_code=404, detail="Operator not found")
        
    await db.delete(operator)
    await db.commit()
    
    return {"status": "deleted"}

@router.post("/test", response_model=CustomOperatorTestResponse)
async def test_custom_operator(
    request: CustomOperatorTestRequest,
    organization_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    _: dict = Depends(require_scopes("pipelines.write")),
    db: AsyncSession = Depends(get_db),
):
    """Test a custom operator with provided code and input."""
    # Create a spec for the temporary executor
    spec = OperatorSpec(
        operator_id="test_operator",
        display_name="Test Operator",
        category=RegistryCategory.CUSTOM,
        input_type=DataType(request.input_type),
        output_type=DataType(request.output_type),
        is_custom=True
    )
    
    executor = PythonOperatorExecutor(spec, request.python_code)
    
    input_obj = OperatorInput(
        data=request.input_data,
        metadata={}
    )
    
    context = ExecutionContext(
        step_id="test_step",
        config=request.config,
        organization_id=str(current_user.id) # Use user ID as organization ID for testing if no organization
    )
    
    # Injected organization if provided
    if organization_id:
        organization = await db.get(Organization, organization_id)
        if organization:
            context.organization_id = str(organization.id)

    output = await executor.safe_execute(input_obj, context)
    
    return CustomOperatorTestResponse(
        success=output.success,
        data=output.data,
        error_message=output.error_message,
        execution_time_ms=output.execution_time_ms
    )

@router.post("/{operator_id}/promote")
async def promote_to_artifact(
    operator_id: UUID,
    namespace: str = "custom",
    organization_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(
        status_code=410,
        detail="Custom-operator promote has been removed. Create a rag_operator artifact through /admin/artifacts instead.",
    )
