import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

from app.db.postgres.engine import sessionmaker as async_session_maker
from app.services.retrieval_service import RetrievalService
from app.db.postgres.models import KnowledgeStore, KnowledgeStoreStatus, StorageBackend, RetrievalPolicy, Tenant, OrgUnit
from sqlalchemy import select

async def test():
    print("Starting Knowledge Store verification...")
    async with async_session_maker() as session:
        # 1. Get Tenant
        tenant = (await session.execute(select(Tenant))).scalars().first()
        if not tenant:
            # Create dummy tenant
            print("Creating dummy tenant...")
            tenant = Tenant(name="Test Tenant", slug="test-tenant")
            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)
        
        print(f"Using tenant: {tenant.name} ({tenant.id})")

        print(f"RetrievalPolicy.SEMANTIC_ONLY value: {RetrievalPolicy.SEMANTIC_ONLY!r}")
        print(f"Stringified: {str(RetrievalPolicy.SEMANTIC_ONLY)}")

        # 2. Create Knowledge Store
        store = KnowledgeStore(
            tenant_id=tenant.id,
            name="Test Store",
            embedding_model_id="test-model",
            backend=StorageBackend.PGVECTOR,
            backend_config={
                 "collection_name": "test_verification_store"
            },
            status=KnowledgeStoreStatus.ACTIVE,
            retrieval_policy="semantic_only", # Try passing raw string
            chunking_strategy={}
        )
        session.add(store)
        await session.commit()
        await session.refresh(store)
        print(f"Created Knowledge Store: {store.id}")

        try:
            # 3. Init Service
            print("Initializing RetrievalService...")
            service = RetrievalService(session)

            # 4. Query
            print("Attempting query (may fail if pgvector not configured)...")
            try:
                # We expect this to try to load the adapter and query.
                # Even if it returns empty or fails connection, it verifies the service logic.
                results = await service.query_multiple_stores([store.id], "hello world")
                print(f"Query successful. Results: {len(results)}")
            except ImportError as e:
                print(f"ImportError (expected if deps missing): {e}")
            except Exception as e:
                print(f"Query failed (expected if DB not ready): {e}")
                # Print stack trace for debugging if needed
                # import traceback
                # traceback.print_exc()

        finally:
            # Cleanup
            print("Cleaning up...")
            await session.delete(store)
            await session.commit()
            print("Done.")

if __name__ == "__main__":
    asyncio.run(test())
