#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from bson import ObjectId
from app.db.connection import MongoDatabase
from app.db.seed import run_full_migration, create_default_tenant, seed_system_roles


async def main():
    print("Starting RBAC migration...")
    
    await MongoDatabase.connect()
    db = MongoDatabase.get_db()
    
    admin_user = await db.users.find_one({"role": "admin"})
    admin_user_id = admin_user["_id"] if admin_user else None
    
    if admin_user:
        print(f"Found admin user: {admin_user.get('email')}")
    else:
        print("No admin user found, proceeding without admin assignment")
    
    print("\nRunning full migration...")
    result = await run_full_migration(admin_user_id=admin_user_id)
    
    print("\n=== Migration Results ===")
    print(f"Tenant: {result['tenant']}")
    print(f"Migration stats: {result['migration']}")
    
    tenant_id = result['tenant']['tenant_id']
    roles = await db.roles.find({"tenant_id": tenant_id}).to_list(100)
    print(f"\nSystem roles created: {len(roles)}")
    for role in roles:
        print(f"  - {role['name']}: {len(role.get('permissions', []))} permissions")
    
    indices_count = await db.rag_indices.count_documents({"tenant_id": tenant_id})
    jobs_count = await db.rag_jobs.count_documents({"tenant_id": tenant_id})
    print(f"\nMigrated resources:")
    print(f"  - Indices: {indices_count}")
    print(f"  - Jobs: {jobs_count}")
    
    await MongoDatabase.close()
    print("\nMigration complete!")


if __name__ == "__main__":
    asyncio.run(main())
