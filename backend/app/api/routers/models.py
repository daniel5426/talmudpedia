"""
Models Registry API - CRUD operations for logical model definitions.
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from bson import ObjectId

from app.db.models.model_registry import (
    LogicalModel,
    ModelProvider,
    ModelCapabilityType,
    ModelProviderType,
    ModelStatus,
    ModelMetadata,
    ModelResolutionPolicy,
)
from app.db.connection import MongoDatabase
from app.api.dependencies import get_current_user, get_tenant_context

router = APIRouter(prefix="/models", tags=["models"])


# ============================================================================
# Request/Response Schemas
# ============================================================================

class CreateModelRequest(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    capability_type: ModelCapabilityType
    metadata: Optional[dict] = None
    default_resolution_policy: Optional[dict] = None


class UpdateModelRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[dict] = None
    default_resolution_policy: Optional[dict] = None
    status: Optional[ModelStatus] = None


class CreateProviderRequest(BaseModel):
    provider: ModelProviderType
    provider_model_id: str
    config: Optional[dict] = None
    credentials_ref: Optional[str] = None
    priority: int = 0


class ModelResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str]
    capability_type: str
    metadata: dict
    default_resolution_policy: dict
    version: int
    status: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime
    providers: list[dict] = []


class ModelListResponse(BaseModel):
    models: list[ModelResponse]
    total: int


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=ModelListResponse)
async def list_models(
    capability_type: Optional[ModelCapabilityType] = None,
    status: Optional[ModelStatus] = Query(default=ModelStatus.ACTIVE),
    skip: int = 0,
    limit: int = 50,
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """List all logical models for the current tenant."""
    db = MongoDatabase.get_db()
    collection = db["logical_models"]
    providers_collection = db["model_providers"]
    
    try:
        tenant_id_obj = ObjectId(tenant_ctx["tenant_id"])
    except Exception:
        # If we can't convert to ObjectId, it's likely a UUID from Postgres
        # For now, we'll try to find a tenant in Mongo with the same string ID or fail gracefully
        tenant_id_obj = str(tenant_ctx["tenant_id"])

    query = {"tenant_id": tenant_id_obj}
    
    total = await collection.count_documents(query)
    cursor = collection.find(query).skip(skip).limit(limit).sort("name", 1)
    models = await cursor.to_list(length=limit)
    
    # Fetch providers for each model
    result = []
    for model in models:
        providers = await providers_collection.find({
            "logical_model_id": model["_id"]
        }).to_list(length=10)
        
        result.append(ModelResponse(
            id=str(model["_id"]),
            name=model["name"],
            slug=model["slug"],
            description=model.get("description"),
            capability_type=model["capability_type"],
            metadata=model.get("metadata", {}),
            default_resolution_policy=model.get("default_resolution_policy", {}),
            version=model.get("version", 1),
            status=model.get("status", "active"),
            tenant_id=str(model["tenant_id"]),
            created_at=model["created_at"],
            updated_at=model["updated_at"],
            providers=[{
                "id": str(p["_id"]),
                "provider": p["provider"],
                "provider_model_id": p["provider_model_id"],
                "priority": p.get("priority", 0),
                "is_enabled": p.get("is_enabled", True),
            } for p in providers]
        ))
    
    return ModelListResponse(models=result, total=total)


@router.post("", response_model=ModelResponse)
async def create_model(
    request: CreateModelRequest,
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Create a new logical model."""
    db = MongoDatabase.get_db()
    collection = db["logical_models"]
    
    # Check for duplicate slug
    existing = await collection.find_one({
        "slug": request.slug,
        "tenant_id": ObjectId(tenant_ctx["tenant_id"])
    })
    if existing:
        raise HTTPException(status_code=400, detail=f"Model with slug '{request.slug}' already exists")
    
    model_doc = {
        "name": request.name,
        "slug": request.slug,
        "description": request.description,
        "capability_type": request.capability_type.value,
        "metadata": request.metadata or {},
        "default_resolution_policy": request.default_resolution_policy or {},
        "tenant_id": ObjectId(tenant_ctx["tenant_id"]),
        "version": 1,
        "status": ModelStatus.ACTIVE.value,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "created_by": ObjectId(current_user["id"]) if current_user.get("id") else None,
    }
    
    result = await collection.insert_one(model_doc)
    model_doc["_id"] = result.inserted_id
    
    return ModelResponse(
        id=str(model_doc["_id"]),
        name=model_doc["name"],
        slug=model_doc["slug"],
        description=model_doc.get("description"),
        capability_type=model_doc["capability_type"],
        metadata=model_doc["metadata"],
        default_resolution_policy=model_doc["default_resolution_policy"],
        version=model_doc["version"],
        status=model_doc["status"],
        tenant_id=str(model_doc["tenant_id"]),
        created_at=model_doc["created_at"],
        updated_at=model_doc["updated_at"],
        providers=[]
    )


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: str,
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Get a specific model by ID."""
    db = MongoDatabase.get_db()
    collection = db["logical_models"]
    providers_collection = db["model_providers"]
    
    model = await collection.find_one({
        "_id": ObjectId(model_id),
        "tenant_id": ObjectId(tenant_ctx["tenant_id"])
    })
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    providers = await providers_collection.find({
        "logical_model_id": model["_id"]
    }).to_list(length=10)
    
    return ModelResponse(
        id=str(model["_id"]),
        name=model["name"],
        slug=model["slug"],
        description=model.get("description"),
        capability_type=model["capability_type"],
        metadata=model.get("metadata", {}),
        default_resolution_policy=model.get("default_resolution_policy", {}),
        version=model.get("version", 1),
        status=model.get("status", "active"),
        tenant_id=str(model["tenant_id"]),
        created_at=model["created_at"],
        updated_at=model["updated_at"],
        providers=[{
            "id": str(p["_id"]),
            "provider": p["provider"],
            "provider_model_id": p["provider_model_id"],
            "priority": p.get("priority", 0),
            "is_enabled": p.get("is_enabled", True),
            "config": p.get("config", {}),
        } for p in providers]
    )


@router.put("/{model_id}", response_model=ModelResponse)
async def update_model(
    model_id: str,
    request: UpdateModelRequest,
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Update a logical model."""
    db = MongoDatabase.get_db()
    collection = db["logical_models"]
    
    model = await collection.find_one({
        "_id": ObjectId(model_id),
        "tenant_id": ObjectId(tenant_ctx["tenant_id"])
    })
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    update_doc = {"updated_at": datetime.utcnow()}
    if request.name is not None:
        update_doc["name"] = request.name
    if request.description is not None:
        update_doc["description"] = request.description
    if request.metadata is not None:
        update_doc["metadata"] = request.metadata
    if request.default_resolution_policy is not None:
        update_doc["default_resolution_policy"] = request.default_resolution_policy
    if request.status is not None:
        update_doc["status"] = request.status.value
    
    await collection.update_one({"_id": ObjectId(model_id)}, {"$set": update_doc})
    
    return await get_model(model_id, tenant_ctx, current_user)


@router.delete("/{model_id}")
async def delete_model(
    model_id: str,
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Delete a logical model and its providers."""
    db = MongoDatabase.get_db()
    collection = db["logical_models"]
    providers_collection = db["model_providers"]
    
    model = await collection.find_one({
        "_id": ObjectId(model_id),
        "tenant_id": ObjectId(tenant_ctx["tenant_id"])
    })
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Delete providers first
    await providers_collection.delete_many({"logical_model_id": ObjectId(model_id)})
    
    # Delete model
    await collection.delete_one({"_id": ObjectId(model_id)})
    
    return {"status": "deleted", "id": model_id}


# ============================================================================
# Provider Endpoints
# ============================================================================

@router.post("/{model_id}/providers")
async def add_provider(
    model_id: str,
    request: CreateProviderRequest,
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Add a provider binding to a model."""
    db = MongoDatabase.get_db()
    models_collection = db["logical_models"]
    providers_collection = db["model_providers"]
    
    model = await models_collection.find_one({
        "_id": ObjectId(model_id),
        "tenant_id": ObjectId(tenant_ctx["tenant_id"])
    })
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    provider_doc = {
        "logical_model_id": ObjectId(model_id),
        "provider": request.provider.value,
        "provider_model_id": request.provider_model_id,
        "config": request.config or {},
        "credentials_ref": request.credentials_ref,
        "priority": request.priority,
        "is_enabled": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    
    result = await providers_collection.insert_one(provider_doc)
    
    return {
        "id": str(result.inserted_id),
        "provider": request.provider.value,
        "provider_model_id": request.provider_model_id,
        "priority": request.priority,
    }


@router.delete("/{model_id}/providers/{provider_id}")
async def remove_provider(
    model_id: str,
    provider_id: str,
    tenant_ctx=Depends(get_tenant_context),
    current_user=Depends(get_current_user),
):
    """Remove a provider binding from a model."""
    db = MongoDatabase.get_db()
    models_collection = db["logical_models"]
    providers_collection = db["model_providers"]
    
    model = await models_collection.find_one({
        "_id": ObjectId(model_id),
        "tenant_id": ObjectId(tenant_ctx["tenant_id"])
    })
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    result = await providers_collection.delete_one({
        "_id": ObjectId(provider_id),
        "logical_model_id": ObjectId(model_id)
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Provider not found")
    
    return {"status": "deleted", "id": provider_id}
