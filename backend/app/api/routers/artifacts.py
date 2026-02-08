from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.postgres.session import get_db
from app.db.postgres.models.identity import User, Tenant, OrgMembership
from app.db.postgres.models.operators import CustomOperator, OperatorCategory
from app.api.dependencies import get_current_principal, require_scopes, ensure_sensitive_action_approved
from app.services.artifact_registry import get_artifact_registry
from app.api.schemas.artifacts import (
    ArtifactSchema, 
    ArtifactCreate, 
    ArtifactUpdate, 
    ArtifactType, 
    ArtifactScope,
    ArtifactTestRequest,
    ArtifactTestResponse,
    ArtifactPromoteRequest
)
from app.rag.pipeline.operator_executor import PythonOperatorExecutor, OperatorInput, ExecutionContext
from app.rag.pipeline.registry import OperatorSpec, DataType, OperatorCategory as RegistryCategory

router = APIRouter(prefix="/admin/artifacts", tags=["artifacts"])


async def get_artifact_context(
    tenant_slug: Optional[str] = None,
    context: Dict[str, Any] = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
):
    if context.get("type") == "workload":
        tenant_id = context.get("tenant_id")
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Tenant context required")
        try:
            tenant_uuid = UUID(str(tenant_id))
        except Exception:
            raise HTTPException(status_code=403, detail="Invalid tenant context")
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_uuid))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return tenant, None, db

    current_user = context.get("user")
    if current_user is None:
        raise HTTPException(status_code=403, detail="Not authorized")

    if not tenant_slug:
        if current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Tenant context required")
        return None, current_user, db

    result = await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    membership_result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.tenant_id == tenant.id,
            OrgMembership.user_id == current_user.id,
        )
    )
    membership = membership_result.scalar_one_or_none()
    if not membership and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not a member of this tenant")

    return tenant, current_user, db

def spec_to_schema(spec: OperatorSpec, atype: ArtifactType, path: Optional[str] = None, code: Optional[str] = None) -> ArtifactSchema:
    """Helper to convert Registry Spec to Unified Schema."""
    scope = ArtifactScope(spec.scope) if hasattr(spec, "scope") and spec.scope in ArtifactScope.__members__.values() else ArtifactScope.RAG
    
    # Check manifest for scope if we could load it... 
    # For now, let's assume default is RAG unless specified.
    
    config_schema = []
    # Convert ConfigFieldSpec to dict
    for cfg in (spec.required_config + spec.optional_config):
        config_schema.append({
            "name": cfg.name,
            "type": cfg.field_type.value if hasattr(cfg.field_type, 'value') else str(cfg.field_type),
            "required": cfg.required,
            "default": cfg.default,
            "description": cfg.description,
            "options": cfg.options
        })

    return ArtifactSchema(
        id=spec.operator_id,
        name=spec.operator_id.split("/")[-1] if "/" in spec.operator_id else spec.operator_id,
        display_name=spec.display_name,
        description=spec.description,
        category=spec.category.value,
        input_type=spec.input_type.value,
        output_type=spec.output_type.value,
        version=spec.version,
        type=atype,
        scope=scope,
        author=spec.author,
        tags=spec.tags or [],
        config_schema=config_schema,
        python_code=code,
        path=path,
        reads=getattr(spec, "reads", []),
        writes=getattr(spec, "writes", []),
        updated_at=datetime.utcnow()
    )

def draft_to_schema(op: CustomOperator) -> ArtifactSchema:
    """Helper to convert DB model to Unified Schema."""
    return ArtifactSchema(
        id=str(op.id),
        name=op.name,
        display_name=op.display_name,
        description=op.description,
        category=op.category.value,
        input_type=op.input_type,
        output_type=op.output_type,
        version=op.version,
        type=ArtifactType.DRAFT,
        scope=ArtifactScope(op.scope) if hasattr(op, "scope") and op.scope else ArtifactScope.RAG,
        reads=getattr(op, "reads", []),
        writes=getattr(op, "writes", []),
        author=None,
        tags=["draft"],
        config_schema=op.config_schema if isinstance(op.config_schema, list) else [],
        created_at=op.created_at,
        updated_at=op.updated_at,
        python_code=op.python_code
    )

@router.get("", response_model=List[ArtifactSchema])
async def list_artifacts(
    tenant_slug: Optional[str] = None,
    artifact_ctx=Depends(get_artifact_context),
):
    """List all artifacts (File-based and DB drafts)."""
    tenant, user, db = artifact_ctx
    
    results = []
    
    # 1. Fetch File-based Artifacts
    registry = get_artifact_registry()
    artifacts = registry.get_all_artifacts()
    for aid, spec in artifacts.items():
        path = str(registry.get_artifact_path(aid))
        results.append(spec_to_schema(spec, ArtifactType.BUILTIN if "builtin/" in aid else ArtifactType.PROMOTED, path))
    
    # 2. Fetch DB Drafts
    query = select(CustomOperator)
    if tenant:
        query = query.where(CustomOperator.tenant_id == tenant.id)
    
    res = await db.execute(query)
    drafts = res.scalars().all()
    for draft in drafts:
        results.append(draft_to_schema(draft))
        
    return results

@router.get("/{artifact_id:path}", response_model=ArtifactSchema)
async def get_artifact(
    artifact_id: str,
    tenant_slug: Optional[str] = None,
    artifact_ctx=Depends(get_artifact_context),
):
    """Get specialized artifact details."""
    tenant, user, db = artifact_ctx
    
    # Check if UUID (Draft)
    try:
        uid = UUID(artifact_id)
        query = select(CustomOperator).where(CustomOperator.id == uid)
        if tenant:
            query = query.where(CustomOperator.tenant_id == tenant.id)
        
        draft = await db.scalar(query)
        if draft:
            return draft_to_schema(draft)
    except ValueError:
        pass # Not a UUID
        
    # Check File-based
    registry = get_artifact_registry()
    spec = registry.get_artifact(artifact_id)
    if spec:
        path = str(registry.get_artifact_path(artifact_id))
        code = registry.get_artifact_code(artifact_id)
        return spec_to_schema(spec, ArtifactType.BUILTIN if "builtin/" in artifact_id else ArtifactType.PROMOTED, path, code)
        
    raise HTTPException(status_code=404, detail="Artifact not found")

@router.post("", response_model=ArtifactSchema)
async def create_artifact_draft(
    request: ArtifactCreate,
    tenant_slug: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    """Create a new artifact draft (DB)."""
    tenant, user, db = artifact_ctx
    if not tenant:
         raise HTTPException(status_code=400, detail="Tenant context required")

    operator = CustomOperator(
        tenant_id=tenant.id,
        name=request.name,
        display_name=request.display_name,
        category=OperatorCategory(request.category),
        description=request.description,
        python_code=request.python_code,
        input_type=request.input_type,
        output_type=request.output_type,
        config_schema=request.config_schema,
        scope=request.scope.value if request.scope else "rag",
        reads=request.reads or [],
        writes=request.writes or [],
        created_by=user.id if user else None
    )
    
    db.add(operator)
    await db.commit()
    await db.refresh(operator)
    
    return draft_to_schema(operator)

@router.put("/{artifact_id:path}", response_model=ArtifactSchema)
async def update_artifact(
    artifact_id: str,
    update_data: ArtifactUpdate,
    tenant_slug: Optional[str] = None,
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    """Update an artifact (Draft DB or File-based)."""
    tenant, user, db = artifact_ctx
    
    # Check if UUID (Draft)
    try:
        uid = UUID(artifact_id)
        query = select(CustomOperator).where(CustomOperator.id == uid)
        if tenant:
            query = query.where(CustomOperator.tenant_id == tenant.id)
            
        draft = await db.scalar(query)
        if draft:
            data = update_data.dict(exclude_unset=True)
            for field, value in data.items():
                if field == 'category' and value:
                    value = OperatorCategory(value)
                if field == 'scope' and value:
                    value = value.value if hasattr(value, 'value') else value
                setattr(draft, field, value)
            
            draft.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(draft)
            return draft_to_schema(draft)
    except ValueError:
        pass
        
    # Check File-based
    registry = get_artifact_registry()
    spec = registry.get_artifact(artifact_id)
    if spec:
        if "builtin/" in artifact_id and (not user or user.role != "admin"):
             raise HTTPException(status_code=403, detail="Cannot update builtin artifacts")
             
        # Prepare updated manifest
        manifest = {
            "id": artifact_id,
            "version": spec.version,
            "display_name": update_data.display_name or spec.display_name,
            "category": update_data.category or spec.category.value,
            "description": update_data.description or spec.description,
            "input_type": update_data.input_type or spec.input_type.value,
            "output_type": update_data.output_type or spec.output_type.value,
            "config": update_data.config_schema if update_data.config_schema is not None else (spec.required_config + spec.optional_config),
            "author": spec.author,
            "tags": spec.tags,
            "scope": update_data.scope.value if update_data.scope else (spec.scope if hasattr(spec, "scope") else "rag"),
            "reads": update_data.reads if update_data.reads is not None else getattr(spec, "reads", []),
            "writes": update_data.writes if update_data.writes is not None else getattr(spec, "writes", []),
        }
        
        # Ensure config is serializable (not Pydantic objects)
        if isinstance(manifest["config"], list):
            manifest["config"] = [c.dict(by_alias=True) if hasattr(c, "dict") else c for c in manifest["config"]]
        
        success = registry.update_artifact(artifact_id, manifest, update_data.python_code)
        if success:
            return await get_artifact(artifact_id, tenant_slug=tenant_slug, artifact_ctx=artifact_ctx)
            
    raise HTTPException(status_code=404, detail="Artifact not found or update failed")

@router.delete("/{artifact_id:path}")
async def delete_artifact(
    artifact_id: str,
    tenant_slug: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    """Delete an artifact."""
    tenant, user, db = artifact_ctx
    tenant_id = str(tenant.id) if tenant else principal.get("tenant_id")
    
    # Check if UUID (Draft)
    try:
        uid = UUID(artifact_id)
        query = select(CustomOperator).where(CustomOperator.id == uid)
        if tenant:
            query = query.where(CustomOperator.tenant_id == tenant.id)
            
        draft = await db.scalar(query)
        if draft:
            await ensure_sensitive_action_approved(
                principal=principal,
                tenant_id=tenant_id,
                subject_type="artifact",
                subject_id=str(draft.id),
                action_scope="artifacts.delete",
                db=db,
            )
            await db.delete(draft)
            await db.commit()
            return {"status": "deleted"}
    except ValueError:
        pass
        
    # Check File-based
    registry = get_artifact_registry()
    if registry.get_artifact(artifact_id):
        if "builtin/" in artifact_id:
            raise HTTPException(status_code=403, detail="Cannot delete builtin artifacts")
        await ensure_sensitive_action_approved(
            principal=principal,
            tenant_id=tenant_id,
            subject_type="artifact",
            subject_id=str(artifact_id),
            action_scope="artifacts.delete",
            db=db,
        )
            
        success = registry.delete_artifact(artifact_id)
        if success:
            return {"status": "deleted"}
            
    raise HTTPException(status_code=404, detail="Artifact not found")

@router.post("/{artifact_id:path}/promote")
async def promote_artifact(
    artifact_id: str,
    request: ArtifactPromoteRequest,
    tenant_slug: Optional[str] = None,
    principal: Dict[str, Any] = Depends(get_current_principal),
    _: Dict[str, Any] = Depends(require_scopes("artifacts.write")),
    artifact_ctx=Depends(get_artifact_context),
):
    """Promote a DB draft to a File artifact."""
    tenant, user, db = artifact_ctx
    
    try:
        uid = UUID(artifact_id)
        query = select(CustomOperator).where(CustomOperator.id == uid)
        if tenant:
            query = query.where(CustomOperator.tenant_id == tenant.id)
            
        draft = await db.scalar(query)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")

        await ensure_sensitive_action_approved(
            principal=principal,
            tenant_id=tenant.id if tenant else principal.get("tenant_id"),
            subject_type="artifact",
            subject_id=str(draft.id),
            action_scope="artifacts.promote",
            db=db,
        )
            
        # Re-use existing promotion logic from rag_custom_operators (or duplicate/move it)
        registry = get_artifact_registry()
        
        artifact_name = draft.name
        namespace = request.namespace
        promoted_id = f"{namespace}/{artifact_name}"
        
        manifest = {
            "id": promoted_id,
            "version": request.version or draft.version or "1.0.0",
            "display_name": draft.display_name,
            "category": draft.category.value,
            "description": draft.description,
            "input_type": draft.input_type,
            "output_type": draft.output_type,
            "config": draft.config_schema if isinstance(draft.config_schema, list) else [],
            "author": (
                f"{user.full_name} ({user.email})"
                if user and hasattr(user, "full_name") and user.full_name
                else (user.email if user else "platform-service")
            ),
            "scope": draft.scope or "rag",
            "reads": draft.reads or [],
            "writes": draft.writes or [],
            "tags": ["promoted", "custom"]
        }
        
        path = registry.promote_to_artifact(namespace, artifact_name, manifest, draft.python_code)
        
        # Delete the draft after successful promotion to avoid duplicates
        await db.delete(draft)
        await db.commit()
        
        return {
            "status": "promoted",
            "artifact_id": promoted_id,
            "path": str(path)
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Only drafts can be promoted")

@router.post("/test", response_model=ArtifactTestResponse)
async def test_artifact(
    request: ArtifactTestRequest,
    tenant_slug: Optional[str] = None,
    artifact_ctx=Depends(get_artifact_context),
):
    """Test an artifact execution."""
    tenant, user, db = artifact_ctx
    # Logic similar to CustomOperator.test
    code = request.python_code
    input_type = request.input_type
    output_type = request.output_type
    
    if request.artifact_id and not code:
        # Load code from existing artifact
        registry = get_artifact_registry()
        # Try as file-based first
        code = registry.get_artifact_code(request.artifact_id)
        if not code:
            # Try as draft
            try:
                uid = UUID(request.artifact_id)
                draft = await db.get(CustomOperator, uid)
                if draft:
                    code = draft.python_code
                    input_type = draft.input_type
                    output_type = draft.output_type
            except ValueError:
                pass
                
    if not code:
        raise HTTPException(status_code=400, detail="No code provided for testing")
        
    spec = OperatorSpec(
        operator_id="test_artifact",
        display_name="Test Artifact",
        category=RegistryCategory.CUSTOM,
        input_type=DataType(input_type),
        output_type=DataType(output_type),
        is_custom=True
    )
    
    executor = PythonOperatorExecutor(spec, code)
    
    input_obj = OperatorInput(
        data=request.input_data,
        metadata={}
    )
    
    context = ExecutionContext(
        step_id="test_step",
        config=request.config,
        tenant_id=str(tenant.id) if tenant else None,
    )

    output = await executor.safe_execute(input_obj, context)
    
    return ArtifactTestResponse(
        success=output.success,
        data=output.data,
        error_message=output.error_message,
        execution_time_ms=output.execution_time_ms
    )
