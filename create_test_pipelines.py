import asyncio
import os
import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Load env variables from .env
from dotenv import load_dotenv
load_dotenv(os.path.join(os.getcwd(), "backend", ".env"))

from app.db.postgres.models.identity import User, Tenant
from app.db.postgres.models.registry import ModelRegistry, ModelCapabilityType
from app.db.postgres.models.rag import VisualPipeline, ExecutablePipeline, PipelineType, PipelineJob
from app.rag.pipeline import PipelineCompiler

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")

engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create_pipelines():
    async with async_session() as session:
        # 1. Get User/Tenant
        user = (await session.execute(select(User).limit(1))).scalar()
        tenant = (await session.execute(select(Tenant).limit(1))).scalar()
        
        if not user or not tenant:
            print("Error: No user or tenant found.")
            return

        # 2. Find Models
        emb_model = (await session.execute(select(ModelRegistry).where(ModelRegistry.capability_type == ModelCapabilityType.EMBEDDING, ModelRegistry.is_active == True))).scalar()
        rerank_model = (await session.execute(select(ModelRegistry).where(ModelRegistry.capability_type == ModelCapabilityType.RERANK, ModelRegistry.is_active == True))).scalar()
        
        emb_model_slug = emb_model.slug if emb_model else "text-embedding-3-small"
        rerank_model_slug = rerank_model.slug if rerank_model else "rerank-english-v3.0"
        
        print(f"Using Embedding Model: {emb_model_slug}")
        print(f"Using Reranking Model: {rerank_model_slug}")

        pipelines_to_create = [
            {
                "name": "Test: Basic Vector Search",
                "nodes": [
                    {"id": "n1", "type": "pipeline_input", "data": {"operator": "query_input", "category": "input", "displayName": "Query", "config": {}}},
                    {"id": "n2", "type": "embedding", "data": {"operator": "model_embedder", "category": "embedding", "displayName": "Embedder", "config": {"model_id": emb_model_slug}}},
                    {"id": "n3", "type": "retrieval", "data": {"operator": "vector_search", "category": "retrieval", "displayName": "Vector Search", "config": {"index_name": "talmud-index", "top_k": 5}}},
                    {"id": "n4", "type": "pipeline_output", "data": {"operator": "retrieval_result", "category": "output", "displayName": "Output", "config": {}}}
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n2"},
                    {"id": "e2", "source": "n2", "target": "n3"},
                    {"id": "e3", "source": "n3", "target": "n4"}
                ]
            },
            {
                "name": "Test: Hybrid + Rerank",
                "nodes": [
                    {"id": "n1", "type": "pipeline_input", "data": {"operator": "query_input", "category": "input", "displayName": "Query", "config": {}}},
                    {"id": "n2", "type": "embedding", "data": {"operator": "model_embedder", "category": "embedding", "displayName": "Embedder", "config": {"model_id": emb_model_slug}}},
                    {"id": "n3", "type": "retrieval", "data": {"operator": "hybrid_search", "category": "retrieval", "displayName": "Hybrid Search", "config": {"index_name": "talmud-index", "top_k": 20, "alpha": 0.5}}},
                    {"id": "n4", "type": "reranking", "data": {"operator": "model_reranker", "category": "reranking", "displayName": "Reranker", "config": {"model_id": rerank_model_slug, "top_k": 5}}},
                    {"id": "n5", "type": "pipeline_output", "data": {"operator": "retrieval_result", "category": "output", "displayName": "Output", "config": {}}}
                ],
                "edges": [
                    {"id": "e1", "source": "n1", "target": "n2"},
                    {"id": "e2", "source": "n2", "target": "n3"},
                    {"id": "e3", "source": "n3", "target": "n4"},
                    {"id": "e4", "source": "n4", "target": "n5"}
                ]
            }
        ]

        for p_data in pipelines_to_create:
            pipeline = VisualPipeline(
                tenant_id=tenant.id,
                name=p_data["name"],
                description="Auto-generated test retrieval pipeline",
                nodes=p_data["nodes"],
                edges=p_data["edges"],
                pipeline_type=PipelineType.RETRIEVAL,
                version=1,
                is_published=False,
                created_by=user.id
            )
            session.add(pipeline)
            await session.commit()
            await session.refresh(pipeline)
            
            print(f"Created Pipeline: {pipeline.name} (ID: {pipeline.id})")
            
            # Compile
            compiler = PipelineCompiler()
            # Compiler expects a dict-like object for nodes/edges
            class MockPipeline:
                def __init__(self, p):
                    self.id = p.id
                    self.tenant_id = p.tenant_id
                    self.name = p.name
                    self.nodes = p.nodes
                    self.edges = p.edges
                    self.version = p.version
                    self.pipeline_type = p.pipeline_type
            
            compile_result = compiler.compile(MockPipeline(pipeline), compiled_by=str(user.id), tenant_id=str(tenant.id))
            
            if compile_result.success:
                exec_pipeline = ExecutablePipeline(
                    visual_pipeline_id=pipeline.id,
                    tenant_id=tenant.id,
                    version=pipeline.version,
                    compiled_graph=compile_result.executable_pipeline.model_dump(mode='json'),
                    is_valid=True,
                    pipeline_type=pipeline.pipeline_type,
                    compiled_by=user.id
                )
                session.add(exec_pipeline)
                pipeline.is_published = True
                await session.commit()
                print(f"  Compiled successfully! Exec ID: {exec_pipeline.id}")
                
                # Create Job
                job = PipelineJob(
                    tenant_id=tenant.id,
                    executable_pipeline_id=exec_pipeline.id,
                    input_params={"query": "What is the Talmud?"},
                    triggered_by=user.id
                )
                session.add(job)
                await session.commit()
                print(f"  Triggered Job: {job.id}")
            else:
                print(f"  Compilation FAILED: {compile_result.errors}")

if __name__ == '__main__':
    asyncio.run(create_pipelines())
