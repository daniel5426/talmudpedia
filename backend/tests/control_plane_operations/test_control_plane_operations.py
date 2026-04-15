from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.postgres.models.identity import Tenant, User
from app.db.postgres.models.rag import RetrievalPolicy, StorageBackend
from app.services.control_plane.agents_admin_service import AgentAdminService, CreateAgentInput
from app.services.control_plane.context import ControlPlaneContext
from app.services.control_plane.contracts import OperationResult
from app.services.control_plane.knowledge_store_admin_service import KnowledgeStoreAdminService


def test_operation_result_includes_result_and_error_channels():
    payload = OperationResult(
        operation_id="job-1",
        kind="pipeline_job",
        status="failed",
        result={"job_id": "job-1"},
        error={"message": "boom"},
    ).to_dict()
    assert payload["operation"]["id"] == "job-1"
    assert payload["result"] == {"job_id": "job-1"}
    assert payload["error"] == {"message": "boom"}


@pytest.mark.asyncio
async def test_agent_admin_rejects_blank_create_name(db_session):
    tenant = Tenant(name="Ops Tenant", slug=f"ops-{uuid4().hex[:8]}")
    user = User(email=f"ops-{uuid4().hex[:8]}@example.com", hashed_password="x", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    ctx = ControlPlaneContext(tenant_id=tenant.id, user=user, user_id=user.id, scopes=("*",))

    with pytest.raises(Exception) as exc_info:
        await AgentAdminService(db_session).create_agent(
            ctx=ctx,
            params=CreateAgentInput(name="   ", graph_definition={"nodes": [], "edges": []}),
        )

    assert getattr(exc_info.value, "code", None) == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_knowledge_store_admin_rejects_missing_create_name(db_session):
    tenant = Tenant(name="Ops Tenant", slug=f"ops-{uuid4().hex[:8]}")
    user = User(email=f"ops-{uuid4().hex[:8]}@example.com", hashed_password="x", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    ctx = ControlPlaneContext(tenant_id=tenant.id, user=user, user_id=user.id, scopes=("*",))

    with pytest.raises(Exception) as exc_info:
        await KnowledgeStoreAdminService(db_session).create_store(
            ctx=ctx,
            tenant_slug=None,
            name="   ",
            description=None,
            embedding_model_id="embed-model-1",
            chunking_strategy=None,
            retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
            backend=StorageBackend.PGVECTOR,
            backend_config={},
            credentials_ref=None,
        )

    assert getattr(exc_info.value, "code", None) == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_knowledge_store_admin_rejects_missing_embedding_model(db_session):
    tenant = Tenant(name="Ops Tenant", slug=f"ops-{uuid4().hex[:8]}")
    user = User(email=f"ops-{uuid4().hex[:8]}@example.com", hashed_password="x", role="admin")
    db_session.add_all([tenant, user])
    await db_session.flush()

    ctx = ControlPlaneContext(tenant_id=tenant.id, user=user, user_id=user.id, scopes=("*",))

    with pytest.raises(Exception) as exc_info:
        await KnowledgeStoreAdminService(db_session).create_store(
            ctx=ctx,
            tenant_slug=None,
            name="store-a",
            description=None,
            embedding_model_id="   ",
            chunking_strategy=None,
            retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
            backend=StorageBackend.PGVECTOR,
            backend_config={},
            credentials_ref=None,
        )

    assert getattr(exc_info.value, "code", None) == "VALIDATION_ERROR"
