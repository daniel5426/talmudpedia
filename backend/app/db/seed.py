from typing import Optional
from datetime import datetime
from bson import ObjectId

from app.db.models.tenant import Tenant, TenantStatus
from app.db.models.org_unit import OrgUnit, OrgUnitType, OrgMembership
from app.db.models.rbac import Role, Permission, Action, ResourceType, RoleAssignment, ActorType
from app.db.connection import MongoDatabase


SYSTEM_ROLES = [
    {
        "name": "Tenant Admin",
        "description": "Full access to all tenant resources",
        "permissions": [
            {"resource_type": rt, "action": a}
            for rt in ResourceType
            for a in Action
        ],
        "is_system": True,
    },
    {
        "name": "Organization Admin",
        "description": "Manage organization units and members",
        "permissions": [
            {"resource_type": ResourceType.ORG_UNIT.value, "action": Action.READ.value},
            {"resource_type": ResourceType.ORG_UNIT.value, "action": Action.WRITE.value},
            {"resource_type": ResourceType.ORG_UNIT.value, "action": Action.DELETE.value},
            {"resource_type": ResourceType.MEMBERSHIP.value, "action": Action.READ.value},
            {"resource_type": ResourceType.MEMBERSHIP.value, "action": Action.WRITE.value},
            {"resource_type": ResourceType.MEMBERSHIP.value, "action": Action.DELETE.value},
            {"resource_type": ResourceType.INDEX.value, "action": Action.READ.value},
            {"resource_type": ResourceType.INDEX.value, "action": Action.WRITE.value},
            {"resource_type": ResourceType.INDEX.value, "action": Action.DELETE.value},
            {"resource_type": ResourceType.PIPELINE.value, "action": Action.READ.value},
            {"resource_type": ResourceType.PIPELINE.value, "action": Action.WRITE.value},
            {"resource_type": ResourceType.JOB.value, "action": Action.READ.value},
            {"resource_type": ResourceType.JOB.value, "action": Action.EXECUTE.value},
            {"resource_type": ResourceType.AUDIT.value, "action": Action.READ.value},
        ],
        "is_system": True,
    },
    {
        "name": "RAG Manager",
        "description": "Manage RAG indices, pipelines, and jobs",
        "permissions": [
            {"resource_type": ResourceType.INDEX.value, "action": Action.READ.value},
            {"resource_type": ResourceType.INDEX.value, "action": Action.WRITE.value},
            {"resource_type": ResourceType.INDEX.value, "action": Action.DELETE.value},
            {"resource_type": ResourceType.PIPELINE.value, "action": Action.READ.value},
            {"resource_type": ResourceType.PIPELINE.value, "action": Action.WRITE.value},
            {"resource_type": ResourceType.PIPELINE.value, "action": Action.DELETE.value},
            {"resource_type": ResourceType.JOB.value, "action": Action.READ.value},
            {"resource_type": ResourceType.JOB.value, "action": Action.EXECUTE.value},
        ],
        "is_system": True,
    },
    {
        "name": "RAG Editor",
        "description": "Create and update RAG resources",
        "permissions": [
            {"resource_type": ResourceType.INDEX.value, "action": Action.READ.value},
            {"resource_type": ResourceType.INDEX.value, "action": Action.WRITE.value},
            {"resource_type": ResourceType.PIPELINE.value, "action": Action.READ.value},
            {"resource_type": ResourceType.PIPELINE.value, "action": Action.WRITE.value},
            {"resource_type": ResourceType.JOB.value, "action": Action.READ.value},
            {"resource_type": ResourceType.JOB.value, "action": Action.EXECUTE.value},
        ],
        "is_system": True,
    },
    {
        "name": "Viewer",
        "description": "Read-only access to RAG resources",
        "permissions": [
            {"resource_type": ResourceType.INDEX.value, "action": Action.READ.value},
            {"resource_type": ResourceType.PIPELINE.value, "action": Action.READ.value},
            {"resource_type": ResourceType.JOB.value, "action": Action.READ.value},
        ],
        "is_system": True,
    },
]


async def seed_system_roles(tenant_id: ObjectId) -> dict:
    db = MongoDatabase.get_db()
    
    created_roles = {}
    
    for role_data in SYSTEM_ROLES:
        existing = await db.roles.find_one({
            "tenant_id": tenant_id,
            "name": role_data["name"],
            "is_system": True,
        })
        
        if existing:
            created_roles[role_data["name"]] = existing["_id"]
            continue
        
        permissions = []
        for p in role_data["permissions"]:
            if isinstance(p["resource_type"], ResourceType):
                permissions.append({
                    "resource_type": p["resource_type"].value,
                    "action": p["action"].value if isinstance(p["action"], Action) else p["action"],
                })
            else:
                permissions.append(p)
        
        role = Role(
            tenant_id=tenant_id,
            name=role_data["name"],
            description=role_data.get("description"),
            permissions=[Permission(**p) for p in permissions],
            is_system=True,
        )
        
        result = await db.roles.insert_one(role.model_dump(by_alias=True))
        created_roles[role_data["name"]] = result.inserted_id
    
    return created_roles


async def create_default_tenant(
    name: str = "Default",
    slug: str = "default",
    admin_user_id: Optional[ObjectId] = None,
) -> dict:
    db = MongoDatabase.get_db()
    
    existing = await db.tenants.find_one({"slug": slug})
    if existing:
        tenant_id = existing["_id"]
        
        roles = await seed_system_roles(tenant_id)
        
        return {
            "tenant_id": tenant_id,
            "status": "existing",
            "roles": roles,
        }
    
    tenant = Tenant(
        name=name,
        slug=slug,
        status=TenantStatus.ACTIVE,
    )
    
    result = await db.tenants.insert_one(tenant.model_dump(by_alias=True))
    tenant_id = result.inserted_id
    
    root_org = OrgUnit(
        tenant_id=tenant_id,
        parent_id=None,
        name=name,
        slug=slug,
        type=OrgUnitType.ORG,
    )
    org_result = await db.org_units.insert_one(root_org.model_dump(by_alias=True))
    org_unit_id = org_result.inserted_id
    
    roles = await seed_system_roles(tenant_id)
    
    if admin_user_id:
        membership = OrgMembership(
            tenant_id=tenant_id,
            user_id=admin_user_id,
            org_unit_id=org_unit_id,
        )
        await db.org_memberships.insert_one(membership.model_dump(by_alias=True))
        
        admin_role_id = roles.get("Tenant Admin")
        if admin_role_id:
            assignment = RoleAssignment(
                tenant_id=tenant_id,
                user_id=admin_user_id,
                actor_type=ActorType.USER,
                role_id=admin_role_id,
                scope_id=tenant_id,
                scope_type="tenant",
                assigned_by=admin_user_id,
            )
            await db.role_assignments.insert_one(assignment.model_dump(by_alias=True))
    
    return {
        "tenant_id": tenant_id,
        "org_unit_id": org_unit_id,
        "status": "created",
        "roles": roles,
    }


async def migrate_existing_rag_resources(tenant_id: ObjectId, owner_id: ObjectId) -> dict:
    db = MongoDatabase.get_db()
    
    indices_result = await db.rag_indices.update_many(
        {"tenant_id": {"$exists": False}},
        {"$set": {"tenant_id": tenant_id, "owner_id": owner_id}},
    )
    
    jobs_result = await db.rag_jobs.update_many(
        {"tenant_id": {"$exists": False}},
        {"$set": {"tenant_id": tenant_id, "owner_id": owner_id}},
    )
    
    pipelines_result = await db.rag_pipelines.update_many(
        {"tenant_id": {"$exists": False}},
        {"$set": {"tenant_id": tenant_id, "owner_id": owner_id}},
    )
    
    return {
        "indices_migrated": indices_result.modified_count,
        "jobs_migrated": jobs_result.modified_count,
        "pipelines_migrated": pipelines_result.modified_count,
    }


async def run_full_migration(admin_user_id: Optional[ObjectId] = None) -> dict:
    tenant_result = await create_default_tenant(admin_user_id=admin_user_id)
    
    tenant_id = tenant_result["tenant_id"]
    org_unit_id = tenant_result.get("org_unit_id", tenant_id)
    
    migration_result = await migrate_existing_rag_resources(tenant_id, org_unit_id)
    
    return {
        "tenant": tenant_result,
        "migration": migration_result,
    }
