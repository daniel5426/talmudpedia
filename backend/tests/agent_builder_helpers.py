from __future__ import annotations

import os
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pytest
from sqlalchemy import select, case, or_

from app.agent.executors.standard import register_standard_operators
from app.agent.registry import AgentOperatorRegistry
from app.agent.execution.service import AgentExecutorService
from app.services.agent_service import AgentService, CreateAgentData, ExecuteAgentData
from app.db.postgres.models.registry import (
    ModelRegistry,
    ModelCapabilityType,
    ModelStatus,
)
from app.db.postgres.models.rag import (
    KnowledgeStore,
    VisualPipeline,
    ExecutablePipeline,
    PipelineType,
    StorageBackend,
)
from app.rag.pipeline.compiler import PipelineCompiler
from app.services.model_resolver import ModelResolver
from app.rag.providers.vector_store.pgvector import PgvectorVectorStore
from app.rag.interfaces.vector_store import VectorDocument


EXCLUDED_AGENT_NODE_TYPES = {"tool"}


def list_agent_operator_specs() -> List[Any]:
    register_standard_operators()
    specs = AgentOperatorRegistry.list_operators()
    return [
        spec for spec in specs
        if spec.type not in EXCLUDED_AGENT_NODE_TYPES and not str(spec.type).startswith("artifact:")
    ]


def list_agent_operator_types() -> List[str]:
    return [spec.type for spec in list_agent_operator_specs()]


def node_def(node_id: str, node_type: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "id": node_id,
        "type": node_type,
        "position": {"x": 0, "y": 0},
        "config": config or {},
    }


def edge_def(
    edge_id: str,
    source: str,
    target: str,
    source_handle: Optional[str] = None,
    target_handle: Optional[str] = None,
) -> Dict[str, Any]:
    data = {
        "id": edge_id,
        "source": source,
        "target": target,
    }
    if source_handle is not None:
        data["source_handle"] = source_handle
    if target_handle is not None:
        data["target_handle"] = target_handle
    return data


def graph_def(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "spec_version": "1.0",
        "nodes": nodes,
        "edges": edges,
    }


def routing_handles(node_type: str, config: Dict[str, Any]) -> List[str]:
    if node_type == "if_else":
        conditions = config.get("conditions", [])
        handles = [c.get("name") or f"condition_{i}" for i, c in enumerate(conditions)]
        handles.append("else")
        return handles
    if node_type == "classify":
        categories = config.get("categories", [])
        return [c.get("name") or f"category_{i}" for i, c in enumerate(categories)]
    if node_type == "while":
        return ["loop", "exit"]
    if node_type == "user_approval":
        return ["approve", "reject"]
    if node_type == "conditional":
        return ["true", "false"]
    return []


def minimal_config_for(
    node_type: str,
    chat_model_id: Optional[str] = None,
    pipeline_id: Optional[str] = None,
    knowledge_store_id: Optional[str] = None,
) -> Dict[str, Any]:
    if node_type in {"agent", "llm"}:
        if not chat_model_id:
            raise RuntimeError("chat_model_id required for LLM/Agent nodes")
        return {"model_id": chat_model_id}
    if node_type == "classify":
        if not chat_model_id:
            raise RuntimeError("chat_model_id required for classify node")
        return {
            "model_id": chat_model_id,
            "categories": [{"name": "alpha"}, {"name": "else"}],
        }
    if node_type == "if_else":
        return {
            "conditions": [{"name": "yes", "expression": "true"}],
        }
    if node_type == "while":
        return {
            "condition": "!has(loop_counters, \"while_node\")",
            "max_iterations": 3,
        }
    if node_type == "conditional":
        return {
            "condition_type": "contains",
            "condition_value": "yes",
        }
    if node_type == "transform":
        return {"mode": "object", "mappings": [{"key": "status", "value": "ok"}]}
    if node_type == "set_state":
        return {"assignments": [{"variable": "flag", "value": "true"}], "is_expression": False}
    if node_type == "rag":
        if not pipeline_id:
            raise RuntimeError("pipeline_id required for rag node")
        return {"pipeline_id": pipeline_id, "top_k": 3}
    if node_type == "vector_search":
        if not knowledge_store_id:
            raise RuntimeError("knowledge_store_id required for vector_search node")
        return {"knowledge_store_id": knowledge_store_id, "top_k": 3}
    if node_type == "end":
        return {"output_message": "done"}
    return {}


def full_config_for(
    node_type: str,
    chat_model_id: Optional[str] = None,
    pipeline_id: Optional[str] = None,
    knowledge_store_id: Optional[str] = None,
) -> Dict[str, Any]:
    if node_type == "agent":
        if not chat_model_id:
            raise RuntimeError("chat_model_id required for agent node")
        return {
            "name": "Agent Node",
            "model_id": chat_model_id,
            "instructions": "Be helpful.",
            "include_chat_history": True,
            "reasoning_effort": "medium",
            "output_format": "text",
            "tools": [],
            "temperature": 0.2,
        }
    if node_type == "llm":
        if not chat_model_id:
            raise RuntimeError("chat_model_id required for llm node")
        return {
            "model_id": chat_model_id,
            "system_prompt": "You are a helpful assistant.",
            "temperature": 0.1,
        }
    return minimal_config_for(
        node_type,
        chat_model_id=chat_model_id,
        pipeline_id=pipeline_id,
        knowledge_store_id=knowledge_store_id,
    )


async def pick_model_slug(
    db_session,
    tenant_id,
    capability: ModelCapabilityType,
    override_env: str,
) -> Optional[str]:
    override = os.getenv(override_env)
    if override:
        return override

    tenant_priority = case((ModelRegistry.tenant_id == tenant_id, 1), else_=0).desc()
    default_priority = case((ModelRegistry.is_default == True, 1), else_=0).desc()
    stmt = (
        select(ModelRegistry)
        .where(
            ModelRegistry.is_active == True,
            ModelRegistry.status == ModelStatus.ACTIVE,
            ModelRegistry.capability_type == capability,
            or_(ModelRegistry.tenant_id == tenant_id, ModelRegistry.tenant_id.is_(None)),
        )
        .order_by(tenant_priority, default_priority, ModelRegistry.updated_at.desc())
        .limit(1)
    )
    result = await db_session.execute(stmt)
    model = result.scalar_one_or_none()
    return model.slug if model else None


async def get_chat_model_slug(db_session, tenant_id) -> Optional[str]:
    return await pick_model_slug(db_session, tenant_id, ModelCapabilityType.CHAT, "TEST_CHAT_MODEL_SLUG")


async def get_embedding_model_slug(db_session, tenant_id) -> Optional[str]:
    return await pick_model_slug(db_session, tenant_id, ModelCapabilityType.EMBEDDING, "TEST_EMBED_MODEL_SLUG")


def require_pgvector():
    if not os.getenv("PGVECTOR_CONNECTION_STRING"):
        pytest.skip("PGVECTOR_CONNECTION_STRING is required for retrieval tests.")


async def create_agent(
    db_session,
    tenant_id,
    user_id,
    name: str,
    slug: str,
    graph_definition: Dict[str, Any],
):
    service = AgentService(db=db_session, tenant_id=tenant_id)
    return await service.create_agent(
        CreateAgentData(
            name=name,
            slug=slug,
            description="agent-builder-test",
            graph_definition=graph_definition,
        ),
        user_id=user_id,
    )


async def execute_agent_via_service(
    db_session,
    tenant_id,
    agent_id,
    user_id,
    input_text: str = "hello",
    context: Optional[Dict[str, Any]] = None,
):
    service = AgentService(db=db_session, tenant_id=tenant_id)
    return await service.execute_agent(
        agent_id=agent_id,
        data=ExecuteAgentData(input=input_text, context=context or {}),
        user_id=user_id,
    )


async def execute_agent_with_input_params(
    db_session,
    agent_id,
    input_params: Dict[str, Any],
):
    executor = AgentExecutorService(db=db_session)
    run_id = await executor.start_run(agent_id=agent_id, input_params=input_params, background=False)
    async for _ in executor.run_and_stream(run_id, db_session):
        pass
    from app.db.postgres.models.agents import AgentRun
    return await db_session.get(AgentRun, run_id)


async def delete_agent(db_session, tenant_id, agent_id):
    service = AgentService(db=db_session, tenant_id=tenant_id)
    try:
        await service.delete_agent(agent_id)
    except Exception:
        pass


async def create_retrieval_setup(
    db_session,
    tenant_id,
    user_id,
    run_prefix: str,
) -> Tuple[str, str, str]:
    """
    Returns (pipeline_id, knowledge_store_id, collection_name).
    """
    require_pgvector()
    embed_model_id = await get_embedding_model_slug(db_session, tenant_id)
    if not embed_model_id:
        pytest.skip("No embedding model available for retrieval tests.")

    collection_name = f"{run_prefix}_vec"
    store = KnowledgeStore(
        tenant_id=tenant_id,
        name=f"{run_prefix}-ks",
        description="test store",
        embedding_model_id=embed_model_id,
        chunking_strategy={},
        backend=StorageBackend.PGVECTOR,
        backend_config={"collection_name": collection_name},
        created_by=user_id,
    )
    db_session.add(store)
    await db_session.commit()
    await db_session.refresh(store)

    # Seed pgvector index with one embedded doc
    resolver = ModelResolver(db_session, tenant_id)
    try:
        embedder = await resolver.resolve_embedding(embed_model_id)
        embedded = await embedder.embed("hello retrieval")
    except Exception:
        pytest.skip("Embedding provider not available for retrieval tests.")
    dimension = len(embedded.values)
    if dimension == 0:
        pytest.skip("Embedding provider returned empty vector.")
    vector_store = PgvectorVectorStore()
    await vector_store.create_index(collection_name, dimension)
    await vector_store.upsert(
        collection_name,
        documents=[
            VectorDocument(
                id=f"{run_prefix}-doc",
                values=embedded.values,
                metadata={"text": "hello retrieval"},
            )
        ],
    )

    nodes = [
        {"id": "query", "category": "input", "operator": "query_input", "position": {"x": 0, "y": 0}, "config": {}},
        {"id": "embed", "category": "embedding", "operator": "model_embedder", "position": {"x": 120, "y": 0}, "config": {"model_id": embed_model_id}},
        {"id": "search", "category": "retrieval", "operator": "vector_search", "position": {"x": 240, "y": 0}, "config": {"knowledge_store_id": str(store.id)}},
        {"id": "out", "category": "output", "operator": "retrieval_result", "position": {"x": 360, "y": 0}, "config": {}},
    ]
    edges = [
        {"id": "e1", "source": "query", "target": "embed"},
        {"id": "e2", "source": "embed", "target": "search"},
        {"id": "e3", "source": "search", "target": "out"},
    ]

    pipeline = VisualPipeline(
        tenant_id=tenant_id,
        name=f"{run_prefix}-retrieval",
        description="retrieval pipeline",
        nodes=nodes,
        edges=edges,
        pipeline_type=PipelineType.RETRIEVAL,
        created_by=user_id,
        is_published=True,
    )
    db_session.add(pipeline)
    await db_session.commit()
    await db_session.refresh(pipeline)

    compiler = PipelineCompiler()
    model_resolver = ModelResolver(db_session, tenant_id)
    compile_result = await compiler.compile_async(pipeline, model_resolver, compiled_by=str(user_id), tenant_id=str(tenant_id))
    if not compile_result.success or not compile_result.executable_pipeline:
        pytest.skip("Failed to compile retrieval pipeline for tests.")

    exec_pipeline = ExecutablePipeline(
        visual_pipeline_id=pipeline.id,
        tenant_id=tenant_id,
        version=pipeline.version,
        compiled_graph=compile_result.executable_pipeline.model_dump(mode="json"),
        is_valid=True,
        pipeline_type=pipeline.pipeline_type,
        compiled_by=user_id,
    )
    db_session.add(exec_pipeline)
    await db_session.commit()

    return str(pipeline.id), str(store.id), collection_name


async def cleanup_retrieval_setup(db_session, pipeline_id: str, store_id: str, collection_name: str):
    if not os.getenv("PGVECTOR_CONNECTION_STRING"):
        return
    try:
        vector_store = PgvectorVectorStore()
        await vector_store.delete_index(collection_name)
    except Exception:
        pass

    try:
        from uuid import UUID
        pipeline = await db_session.get(VisualPipeline, UUID(pipeline_id))
        if pipeline:
            await db_session.delete(pipeline)
    except Exception:
        pass

    try:
        from uuid import UUID
        store = await db_session.get(KnowledgeStore, UUID(store_id))
        if store:
            await db_session.delete(store)
    except Exception:
        pass

    await db_session.commit()
