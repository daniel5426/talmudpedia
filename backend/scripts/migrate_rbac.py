import asyncio
import os
import uuid
from typing import Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

# Import models
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.postgres.models.identity import User as PGUser, Tenant as PGTenant
from app.db.postgres.models.rbac import Role as PGRole, RolePermission as PGRolePermission, RoleAssignment as PGRoleAssignment, Action, ResourceType, ActorType
from app.db.connection import uri as MONGO_URI

async def migrate():
    # 1. Setup connections
    mongo_client = AsyncIOMotorClient(MONGO_URI)
    mongo_db = mongo_client["sefaria"]
    
    from app.db.postgres.engine import DATABASE_URL
    engine = create_async_engine(DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://"))
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as pg_session:
        # 2. Build Mappings
        print("Building user mapping by email...")
        res = await pg_session.execute(select(PGUser))
        pg_users = res.scalars().all()
        email_to_pg_user_id = {u.email: u.id for u in pg_users}
        
        print("Building tenant mapping by slug...")
        res = await pg_session.execute(select(PGTenant))
        pg_tenants = res.scalars().all()
        slug_to_pg_tenant_id = {t.slug: t.id for t in pg_tenants}
        
        # We also need a way to map MongoDB IDs to PostgreSQL IDs if possible, 
        # but since we don't have a direct link, we'll try to find the "default" tenant.
        # Most roles in Mongo seem to belong to one tenant.
        
        # 3. Migrate Roles
        print("Migrating Roles...")
        mongo_roles = await mongo_db.roles.find().to_list(length=1000)
        mongo_to_pg_role_id = {}
        
        for m_role in mongo_roles:
            # Try to find matching tenant in Postgres. 
            # If we don't know the tenant, we'll assign it to the first one for now or a 'default' one.
            # Usually there's only one tenant in a dev env.
            tenant_id = None
            if pg_tenants:
                tenant_id = pg_tenants[0].id # Fallback to first tenant
                
            pg_role = PGRole(
                name=m_role["name"],
                description=m_role.get("description"),
                is_system=m_role.get("is_system", False),
                tenant_id=tenant_id
            )
            pg_session.add(pg_role)
            await pg_session.flush()
            mongo_to_pg_role_id[str(m_role["_id"])] = pg_role.id
            
            # Migrate Permissions
            for m_perm in m_role.get("permissions", []):
                pg_perm = PGRolePermission(
                    role_id=pg_role.id,
                    resource_type=ResourceType(m_perm["resource_type"]),
                    action=Action(m_perm["action"])
                )
                pg_session.add(pg_perm)
        
        # 4. Migrate Role Assignments
        print("Migrating Role Assignments...")
        mongo_assignments = await mongo_db.role_assignments.find().to_list(length=1000)
        
        # We need a way to map MongoDB user IDs to PostgreSQL user IDs.
        # Let's fetch MongoDB users to get their emails.
        mongo_users = await mongo_db.users.find().to_list(length=1000)
        mongo_user_id_to_email = {str(u["_id"]): u["email"] for u in mongo_users}
        
        for m_ass in mongo_assignments:
            m_user_id = str(m_ass["user_id"])
            m_email = mongo_user_id_to_email.get(m_user_id)
            pg_user_id = email_to_pg_user_id.get(m_email)
            
            pg_role_id = mongo_to_pg_role_id.get(str(m_ass["role_id"]))
            
            if pg_user_id and pg_role_id:
                # Scope mapping: if it was a tenant-level assignment in Mongo, 
                # use the current tenant in Postgres.
                scope_id = pg_user_id # Default to user ID if scope is weird
                if m_ass.get("scope_type") == "tenant":
                    scope_id = pg_tenants[0].id if pg_tenants else pg_user_id
                    
                pg_ass = PGRoleAssignment(
                    tenant_id=pg_tenants[0].id if pg_tenants else uuid.uuid4(),
                    role_id=pg_role_id,
                    user_id=pg_user_id,
                    actor_type=ActorType.USER,
                    scope_id=scope_id,
                    scope_type=m_ass.get("scope_type", "tenant"),
                    assigned_by=pg_user_id # Self-assigned for migration purposes
                )
                pg_session.add(pg_ass)
        
        await pg_session.commit()
        print("Migration completed successfully!")

if __name__ == "__main__":
    asyncio.run(migrate())
