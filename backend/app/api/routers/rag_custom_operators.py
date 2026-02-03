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
from app.db.postgres.models.identity import User, Tenant, OrgMembership
from app.db.postgres.models.rag import CustomOperator, OperatorCategory
from app.db.postgres.models.rbac import Action, ResourceType, ActorType
from app.api.routers.auth import get_current_user
from app.core.rbac import check_permission
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

async def get_tenant_context(
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get tenant context with user info."""
    if not tenant_slug:
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Tenant context required")
        return None, current_user, db

    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
        
    # Check membership
    membership_result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.tenant_id == tenant.id,
            OrgMembership.user_id == current_user.id
        )
    )
    membership = membership_result.scalar_one_or_none()
    if not membership and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not a member of this tenant")
        
    return tenant, current_user, db

@router.get("", response_model=List[CustomOperatorResponse])
async def list_custom_operators(
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List custom operators for the tenant."""
    tenant, user, db = await get_tenant_context(tenant_slug, current_user, db)
    
    query = select(CustomOperator)
    if tenant:
        query = query.where(CustomOperator.tenant_id == tenant.id)
    
    query = query.order_by(CustomOperator.updated_at.desc())
    result = await db.execute(query)
    operators = result.scalars().all()
    return operators

@router.post("", response_model=CustomOperatorResponse)
async def create_custom_operator(
    request: CustomOperatorCreate,
    http_request: Request,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new custom operator."""
    tenant, user, db = await get_tenant_context(tenant_slug, current_user, db)
    if not tenant:
         raise HTTPException(status_code=400, detail="Tenant context required")
    
    # Check duplicate name in tenant
    stmt = select(CustomOperator).where(
        CustomOperator.tenant_id == tenant.id,
        CustomOperator.name == request.name
    )
    existing = await db.scalar(stmt)
    if existing:
        raise HTTPException(status_code=400, detail="Operator with this name already exists")

    operator = CustomOperator(
        tenant_id=tenant.id,
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
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a custom operator by ID."""
    tenant, user, db = await get_tenant_context(tenant_slug, current_user, db)
    
    query = select(CustomOperator).where(CustomOperator.id == operator_id)
    if tenant:
        query = query.where(CustomOperator.tenant_id == tenant.id)
        
    operator = await db.scalar(query)
    if not operator:
        raise HTTPException(status_code=404, detail="Operator not found")
        
    return operator

@router.put("/{operator_id}", response_model=CustomOperatorResponse)
async def update_custom_operator(
    operator_id: UUID,
    update_data: CustomOperatorUpdate,
    http_request: Request,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a custom operator."""
    tenant, user, db = await get_tenant_context(tenant_slug, current_user, db)
    
    query = select(CustomOperator).where(CustomOperator.id == operator_id)
    if tenant:
        query = query.where(CustomOperator.tenant_id == tenant.id)
        
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
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a custom operator."""
    tenant, user, db = await get_tenant_context(tenant_slug, current_user, db)
    
    query = select(CustomOperator).where(CustomOperator.id == operator_id)
    if tenant:
        query = query.where(CustomOperator.tenant_id == tenant.id)
        
    operator = await db.scalar(query)
    if not operator:
        raise HTTPException(status_code=404, detail="Operator not found")
        
    await db.delete(operator)
    await db.commit()
    
    return {"status": "deleted"}

@router.post("/test", response_model=CustomOperatorTestResponse)
async def test_custom_operator(
    request: CustomOperatorTestRequest,
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
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
        tenant_id=str(current_user.id) # Use user ID as tenant ID for testing if no tenant
    )
    
    # Injected tenant if provided
    if tenant_slug:
        tenant_result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        tenant = tenant_result.scalar_one_or_none()
        if tenant:
            context.tenant_id = str(tenant.id)

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
    tenant_slug: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Promote a custom operator to a file-based artifact.
    
    This writes the operator's code and metadata to the /backend/artifacts 
    directory, allowing it to be managed as a first-class code entity.
    """
    # Get tenant context
    tenant, user, db = await get_tenant_context(tenant_slug, current_user, db)
    
    # Fetch operator
    query = select(CustomOperator).where(CustomOperator.id == operator_id)
    if tenant:
        query = query.where(CustomOperator.tenant_id == tenant.id)
        
    operator = await db.scalar(query)
    if not operator:
        raise HTTPException(status_code=404, detail="Operator not found")
        
    # Prepare manifest for artifact.yaml
    artifact_id = f"{namespace}/{operator.name}"
    
    # Convert config schema to list of dicts if needed
    config_list = operator.config_schema if isinstance(operator.config_schema, list) else []
    
    manifest = {
        "id": artifact_id,
        "version": operator.version or "1.0.0",
        "display_name": operator.display_name,
        "category": operator.category.value,
        "description": operator.description,
        "input_type": operator.input_type,
        "output_type": operator.output_type,
        "config": config_list,
        "author": f"{user.full_name} ({user.email})" if hasattr(user, "full_name") and user.full_name else user.email,
        "tags": ["promoted", "custom"]
    }
    
    # Use the Registry Service to save it
    from app.services.artifact_registry import get_artifact_registry
    registry = get_artifact_registry()
    
    try:
        path = registry.promote_to_artifact(namespace, operator.name, manifest, operator.python_code)
        
        # Log action
        log_simple_action(
            db, 
            current_user.id, 
            "promote_artifact", 
            "custom_operator", 
            str(operator.id),
            {"artifact_id": artifact_id}
        )
        
        return {
            "status": "promoted",
            "artifact_id": artifact_id,
            "path": str(path),
            "version": manifest["version"]
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Promotion failed: {str(e)}")

