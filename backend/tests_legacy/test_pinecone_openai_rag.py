import asyncio
import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db.postgres.models.identity import Tenant, User, OrgMembership
from app.db.postgres.models.registry import (
    ModelRegistry,
    ModelProviderBinding,
    ModelProviderType,
    ModelCapabilityType,
    ModelStatus,
    ProviderConfig,
)
from app.db.postgres.models.rag import (
    VisualPipeline,
    ExecutablePipeline,
    PipelineJob,
    PipelineJobStatus,
    PipelineStepExecution,
    PipelineStepStatus,
    PipelineType,
    KnowledgeStore,
    StorageBackend,
    RetrievalPolicy,
)
from app.db.postgres.models.agents import AgentRun, AgentTrace, RunStatus
from app.rag.pipeline.compiler import PipelineCompiler
from app.rag.pipeline.executor import PipelineExecutor
from app.rag.pipeline.registry import OperatorRegistry
from app.rag.providers.vector_store.pinecone import PineconeVectorStore
from app.services.agent_service import AgentService, CreateAgentData
from app.agent.graph.schema import AgentNodePosition, AgentGraph
from app.agent.graph.compiler import AgentCompiler
from app.agent.executors.standard import register_standard_operators
from app.agent.execution.service import AgentExecutorService
from app.agent.execution.types import ExecutionMode


@pytest_asyncio.fixture
async def tenant_user(db_session):
    if os.getenv("TEST_USE_REAL_DB") == "1":
        email = os.getenv("TEST_USER_EMAIL", "danielbenassaya2626@gmail.com")
        user_result = await db_session.execute(select(User).where(User.email == email))
        user = user_result.scalars().first()
        assert user, f"User with email {email} not found in DB"

        membership_result = await db_session.execute(
            select(OrgMembership, Tenant)
            .join(Tenant, OrgMembership.tenant_id == Tenant.id)
            .where(OrgMembership.user_id == user.id)
        )
        membership_row = membership_result.first()
        assert membership_row, f"No tenant membership found for user {email}"
        membership, tenant = membership_row
        return tenant, user

    tenant = Tenant(name="Test Tenant", slug="test-tenant")
    db_session.add(tenant)
    await db_session.flush()

    user = User(email="tester@example.com", full_name="Tester", role="admin")
    db_session.add(user)
    await db_session.flush()

    return tenant, user


@pytest.fixture(scope="session", autouse=True)
def register_operator_registries():
    OperatorRegistry.reset_instance()
    OperatorRegistry.get_instance()
    register_standard_operators()


def _node(node_id, category, operator, x=0, y=0, config=None):
    return {
        "id": node_id,
        "category": category,
        "operator": operator,
        "position": {"x": x, "y": y},
        "config": config or {},
    }


def _edge(edge_id, source, target):
    return {
        "id": edge_id,
        "source": source,
        "target": target,
    }


async def _ensure_provider_config(db_session, tenant_id, api_key):
    stmt = select(ProviderConfig).where(
        ProviderConfig.tenant_id == tenant_id,
        ProviderConfig.provider == ModelProviderType.OPENAI,
    )
    existing = (await db_session.execute(stmt)).scalars().first()
    if existing:
        return existing

    config = ProviderConfig(
        tenant_id=tenant_id,
        provider=ModelProviderType.OPENAI,
        credentials={"api_key": api_key},
        is_enabled=True,
    )
    db_session.add(config)
    await db_session.commit()
    await db_session.refresh(config)
    return config


async def _create_model_with_binding(
    db_session,
    tenant_id,
    name,
    slug,
    capability_type,
    provider_model_id,
    binding_config,
    metadata=None,
):
    model = ModelRegistry(
        tenant_id=tenant_id,
        name=name,
        slug=slug,
        description=f"{name} (test)",
        capability_type=capability_type,
        status=ModelStatus.ACTIVE,
        default_resolution_policy={},
        metadata_=metadata or {},
        version=1,
        is_active=True,
        is_default=False,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)

    binding = ModelProviderBinding(
        model_id=model.id,
        tenant_id=tenant_id,
        provider=ModelProviderType.OPENAI,
        provider_model_id=provider_model_id,
        priority=0,
        is_enabled=True,
        config=binding_config or {},
    )
    db_session.add(binding)
    await db_session.commit()
    await db_session.refresh(binding)

    return model, binding


async def _ensure_pinecone_index(api_key, base_name, dimension):
    store = PineconeVectorStore(api_key=api_key)
    existing = await store.list_indices()

    index_name = base_name
    if index_name in existing:
        stats = await store.get_index_stats(index_name)
        if stats and stats.dimension != dimension:
            index_name = f"{base_name}-{dimension}-{uuid.uuid4().hex[:6]}"
        else:
            return index_name

    created = await store.create_index(index_name, dimension=dimension)
    if not created:
        # Fall back to a unique name if creation failed due to a race
        index_name = f"{base_name}-{uuid.uuid4().hex[:6]}"
        created = await store.create_index(index_name, dimension=dimension)

    # If creation failed (e.g., index limit), reuse an existing compatible index
    if not created:
        for name in existing:
            stats = await store.get_index_stats(name)
            if stats and stats.dimension == dimension:
                return name
        raise RuntimeError("No Pinecone index available with matching dimension")

    # Give Pinecone a moment to initialize the index
    await asyncio.sleep(5)
    return index_name


async def _compile_and_execute(db_session, pipeline, tenant_id, user_id, input_params):
    compiler = PipelineCompiler()
    executor = PipelineExecutor(db_session)

    db_session.add(pipeline)
    await db_session.commit()
    await db_session.refresh(pipeline)

    compilation = compiler.compile(pipeline, compiled_by=str(user_id), tenant_id=str(tenant_id))
    assert compilation.success, f"Pipeline compilation failed: {compilation.errors}"

    executable = compilation.executable_pipeline
    executable_db = ExecutablePipeline(
        visual_pipeline_id=pipeline.id,
        tenant_id=tenant_id,
        version=pipeline.version,
        compiled_graph={
            "dag": [step.model_dump() for step in executable.dag],
            "config_snapshot": executable.config_snapshot,
            "locked_operator_versions": executable.locked_operator_versions,
            "dag_hash": executable.dag_hash,
        },
        pipeline_type=pipeline.pipeline_type,
        compiled_by=user_id,
        is_valid=True,
    )
    db_session.add(executable_db)
    await db_session.commit()
    await db_session.refresh(executable_db)

    job = PipelineJob(
        tenant_id=tenant_id,
        executable_pipeline_id=executable_db.id,
        input_params=input_params,
        triggered_by=user_id,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    job_id = job.id
    await executor.execute_job(job_id)

    db_session.expire_all()
    refreshed = await db_session.get(PipelineJob, job_id)
    return refreshed


@pytest.mark.asyncio
async def test_pinecone_openai_rag_and_agent(db_session, tenant_user):
    if os.getenv("TEST_USE_REAL_DB") != "1":
        pytest.skip("Requires real DB for Pinecone/OpenAI integration")

    openai_key = os.getenv("OPENAI_API_KEY")
    pinecone_key = os.getenv("PINECONE_API_KEY")
    if not openai_key or not pinecone_key:
        pytest.skip("Missing OPENAI_API_KEY or PINECONE_API_KEY")

    tenant, user = tenant_user
    tenant_id = tenant.id
    user_id = user.id

    await _ensure_provider_config(db_session, tenant_id, openai_key)

    slug_suffix = uuid.uuid4().hex[:8]
    embedding_model, _ = await _create_model_with_binding(
        db_session,
        tenant_id,
        name=f"OpenAI Embedding {slug_suffix}",
        slug=f"openai-embed-{slug_suffix}",
        capability_type=ModelCapabilityType.EMBEDDING,
        provider_model_id="text-embedding-3-small",
        binding_config={"api_key": openai_key},
        metadata={"dimension": 1536},
    )

    chat_model, _ = await _create_model_with_binding(
        db_session,
        tenant_id,
        name=f"OpenAI Chat {slug_suffix}",
        slug=f"openai-chat-{slug_suffix}",
        capability_type=ModelCapabilityType.CHAT,
        provider_model_id="gpt-4o-mini",
        binding_config={"temperature": 0.2},
        metadata={},
    )

    index_name = await _ensure_pinecone_index(
        pinecone_key,
        base_name=f"talmudpedia-test-{slug_suffix}",
        dimension=1536,
    )

    knowledge_store = KnowledgeStore(
        tenant_id=tenant_id,
        name=f"Pinecone Store {slug_suffix}",
        description="Integration test store",
        embedding_model_id=str(embedding_model.id),
        chunking_strategy={"chunk_size": 200, "chunk_overlap": 20},
        retrieval_policy=RetrievalPolicy.SEMANTIC_ONLY,
        backend=StorageBackend.PINECONE,
        backend_config={
            "index_name": index_name,
            "api_key": pinecone_key,
        },
        status="active",
        created_by=user_id,
    )
    db_session.add(knowledge_store)
    await db_session.commit()
    await db_session.refresh(knowledge_store)
    knowledge_store_id = str(knowledge_store.id)
    embedding_model_id = str(embedding_model.id)
    chat_model_id = str(chat_model.id)

    doc_path = Path("/tmp") / f"talmudpedia_rag_{slug_suffix}.txt"
    doc_path.write_text(
        """Rabbi Akiva taught: Love your neighbor as yourself.\n"
        "This test document is used for Pinecone + OpenAI integration.\n"
        "Keywords: Akiva, neighbor, talmudpedia.\n""",
        encoding="utf-8",
    )

    namespace = f"ns-{slug_suffix}"

    ingestion_pipeline = VisualPipeline(
        tenant_id=tenant_id,
        name=f"Ingestion {slug_suffix}",
        description="Pinecone ingestion pipeline",
        nodes=[
            _node("source_1", "source", "local_loader", x=0, y=0, config={"source": str(doc_path)}),
            _node("chunk_1", "chunking", "recursive_chunker", x=200, y=0, config={"chunk_size": 200, "chunk_overlap": 20}),
            _node("embed_1", "embedding", "model_embedder", x=400, y=0, config={"model_id": embedding_model_id}),
            _node(
                "store_1",
                "storage",
                "knowledge_store_sink",
                x=600,
                y=0,
                config={
                    "knowledge_store_id": knowledge_store_id,
                    "namespace": namespace,
                    "batch_size": 10,
                },
            ),
        ],
        edges=[
            _edge("e1", "source_1", "chunk_1"),
            _edge("e2", "chunk_1", "embed_1"),
            _edge("e3", "embed_1", "store_1"),
        ],
        pipeline_type=PipelineType.INGESTION,
    )

    ingestion_job = await _compile_and_execute(
        db_session,
        ingestion_pipeline,
        tenant_id,
        user_id,
        input_params={"source": str(doc_path)},
    )

    assert ingestion_job.status == PipelineJobStatus.COMPLETED
    assert ingestion_job.output is not None

    ingestion_steps = (await db_session.execute(
        select(PipelineStepExecution).where(PipelineStepExecution.job_id == ingestion_job.id)
    )).scalars().all()
    assert ingestion_steps
    assert all(step.status == PipelineStepStatus.COMPLETED for step in ingestion_steps)

    # Wait for Pinecone to index vectors
    adapter = PineconeVectorStore(api_key=pinecone_key)
    for _ in range(5):
        stats = await adapter.get_index_stats(index_name)
        if stats and stats.namespaces and stats.namespaces.get(namespace, 0) > 0:
            break
        await asyncio.sleep(2)

    retrieval_pipeline_1 = VisualPipeline(
        tenant_id=tenant_id,
        name=f"Retrieval Basic {slug_suffix}",
        description="Vector search retrieval",
        nodes=[
            _node("input_1", "input", "query_input", x=0, y=0),
            _node("embed_2", "embedding", "model_embedder", x=200, y=0, config={"model_id": embedding_model_id}),
            _node(
                "search_1",
                "retrieval",
                "vector_search",
                x=400,
                y=0,
                config={
                    "knowledge_store_id": knowledge_store_id,
                    "namespace": namespace,
                    "top_k": 3,
                },
            ),
            _node("output_1", "output", "retrieval_result", x=600, y=0),
        ],
        edges=[
            _edge("r1", "input_1", "embed_2"),
            _edge("r2", "embed_2", "search_1"),
            _edge("r3", "search_1", "output_1"),
        ],
        pipeline_type=PipelineType.RETRIEVAL,
    )

    retrieval_pipeline_2 = VisualPipeline(
        tenant_id=tenant_id,
        name=f"Retrieval Passthrough {slug_suffix}",
        description="Retrieval with query passthrough",
        nodes=[
            _node("input_2", "input", "query_input", x=0, y=0),
            _node("pass_2", "enrichment", "custom/rag_query_passthrough", x=200, y=0, config={"tag": "passthrough"}),
            _node("embed_3", "embedding", "model_embedder", x=400, y=0, config={"model_id": embedding_model_id}),
            _node(
                "search_2",
                "retrieval",
                "vector_search",
                x=600,
                y=0,
                config={
                    "knowledge_store_id": knowledge_store_id,
                    "namespace": namespace,
                    "top_k": 5,
                },
            ),
            _node("output_2", "output", "retrieval_result", x=800, y=0),
        ],
        edges=[
            _edge("r4", "input_2", "pass_2"),
            _edge("r5", "pass_2", "embed_3"),
            _edge("r6", "embed_3", "search_2"),
            _edge("r7", "search_2", "output_2"),
        ],
        pipeline_type=PipelineType.RETRIEVAL,
    )

    retrieval_job_1 = await _compile_and_execute(
        db_session,
        retrieval_pipeline_1,
        tenant_id,
        user_id,
        input_params={"text": "What did Rabbi Akiva teach about neighbors?"},
    )

    assert retrieval_job_1.status == PipelineJobStatus.COMPLETED
    assert isinstance(retrieval_job_1.output, list)

    retrieval_job_2 = await _compile_and_execute(
        db_session,
        retrieval_pipeline_2,
        tenant_id,
        user_id,
        input_params={"text": "Find Akiva keyword in talmudpedia"},
    )

    assert retrieval_job_2.status == PipelineJobStatus.COMPLETED
    assert isinstance(retrieval_job_2.output, list)

    retrieval_steps = (await db_session.execute(
        select(PipelineStepExecution).where(PipelineStepExecution.job_id == retrieval_job_2.id)
    )).scalars().all()
    assert retrieval_steps
    assert all(step.status == PipelineStepStatus.COMPLETED for step in retrieval_steps)

    # Agent with OpenAI LLM
    agent_service = AgentService(db=db_session, tenant_id=tenant_id)
    agent_graph = {
        "nodes": [
            {
                "id": "start_1",
                "type": "start",
                "position": AgentNodePosition(x=0, y=0).model_dump(),
                "config": {},
            },
            {
                "id": "llm_1",
                "type": "llm",
                "position": AgentNodePosition(x=200, y=0).model_dump(),
                "config": {
                    "model_id": chat_model_id,
                    "system_prompt": "Respond with a short confirmation.",
                    "temperature": 0.2,
                },
            },
            {
                "id": "end_1",
                "type": "end",
                "position": AgentNodePosition(x=400, y=0).model_dump(),
                "config": {},
            },
        ],
        "edges": [
            {"id": "ae1", "source": "start_1", "target": "llm_1"},
            {"id": "ae2", "source": "llm_1", "target": "end_1"},
        ],
    }

    agent = await agent_service.create_agent(
        CreateAgentData(
            name=f"OpenAI Agent {slug_suffix}",
            slug=f"openai-agent-{slug_suffix}",
            graph_definition=agent_graph,
            memory_config={},
        ),
        user_id=user_id,
    )

    compiler = AgentCompiler(db=db_session, tenant_id=tenant_id)
    graph = AgentGraph(**agent.graph_definition)
    compiled = await compiler.compile(agent.id, agent.version, graph=graph)
    assert compiled.entry_point is not None

    executor_service = AgentExecutorService(db=db_session)
    run_id = await executor_service.start_run(
        agent.id,
        input_params={"messages": [{"role": "user", "content": "Hello agent"}]},
        user_id=user_id,
        background=False,
        mode=ExecutionMode.DEBUG,
    )
    await executor_service._execute(run_id, db=db_session, mode=ExecutionMode.DEBUG)

    db_session.expire_all()
    run = (await db_session.execute(select(AgentRun).where(AgentRun.id == run_id))).scalars().first()
    assert run.status == RunStatus.completed
    assert run.output_result is not None
    assert "messages" in run.output_result

    traces = (await db_session.execute(select(AgentTrace).where(AgentTrace.run_id == run_id))).scalars().all()
    assert any(t.span_type == "node_start" for t in traces)
