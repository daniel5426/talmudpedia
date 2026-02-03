import logging
import uuid
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.agent.executors.base import BaseNodeExecutor, ValidationResult
from app.db.postgres.models.rag import PipelineJob, PipelineJobStatus, ExecutablePipeline, PipelineStepStatus
from app.rag.pipeline.executor import PipelineExecutor as RAGPipelineExecutor
from app.services.retrieval_service import RetrievalService
from app.agent.cel_engine import evaluate_template

logger = logging.getLogger(__name__)

class RetrievalNodeExecutor(BaseNodeExecutor):
    """
    Executes a RAG Retrieval Pipeline.
    """
    async def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        if not config.get("pipeline_id"):
             return ValidationResult(valid=False, errors=["Missing 'pipeline_id' in configuration"])
        return ValidationResult(valid=True)

    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        pipeline_id_str = config.get("pipeline_id")
        if not pipeline_id_str:
            raise ValueError("Missing pipeline_id")

        # Resolve Query
        query = self._resolve_query(state, config)
        top_k = config.get("top_k", 10)

        # Emit Start Event
        self._emit_start(context, config, "retrieval", {"query": query, "pipeline_id": pipeline_id_str})

        try:
            pipeline_id = UUID(pipeline_id_str)
            
            # 1. Resolve Executable Pipeline
            stmt = select(ExecutablePipeline).where(
                ExecutablePipeline.visual_pipeline_id == pipeline_id,
                ExecutablePipeline.is_valid == True
            ).order_by(ExecutablePipeline.version.desc()).limit(1)
            
            result = await self.db.execute(stmt)
            exec_pipeline = result.scalar_one_or_none()
            
            if not exec_pipeline:
                    # Fallback to any version if no valid one marked?
                    stmt = select(ExecutablePipeline).where(
                    ExecutablePipeline.visual_pipeline_id == pipeline_id
                    ).order_by(ExecutablePipeline.version.desc()).limit(1)
                    result = await self.db.execute(stmt)
                    exec_pipeline = result.scalar_one_or_none()
            
            if not exec_pipeline:
                    raise ValueError(f"No executable pipeline found for pipeline {pipeline_id_str}")

            # 2. Create Job
            job_id = uuid.uuid4()
            job = PipelineJob(
                id=job_id,
                tenant_id=self.tenant_id,
                executable_pipeline_id=exec_pipeline.id,
                status=PipelineJobStatus.PENDING,
                input_params={"query": query, "top_k": top_k}, 
                triggered_by="agent"
            )
            self.db.add(job)
            await self.db.commit()
            
            # 3. Execute Job
            executor = RAGPipelineExecutor(self.db)
            await executor.execute_job(job.id)
            
            # 4. Get Results
            await self.db.refresh(job)
            if job.status == PipelineJobStatus.FAILED:
                    raise RuntimeError(f"Pipeline execution failed: {job.error_message}")
            
            results = self._normalize_results(job.output)

            # Emit End Event
            self._emit_end(context, config, "retrieval", {"results_count": len(results)}, results)

            return {
                "rag_output": results,
                "context": {
                    "search_results": results,
                    "last_query": query
                }
            }

        except Exception as e:
            logger.error(f"Retrieval Pipeline execution failed: {e}")
            self._emit_error(context, str(e))
            raise e

    def _resolve_query(self, state: Dict[str, Any], config: Dict[str, Any]) -> str:
        query_template = config.get("query", "")
        query = ""
        
        if query_template:
            try:
                query = evaluate_template(query_template, state)
            except Exception as e:
                logger.warning(f"Failed to interpolate query template: {e}")
                query = query_template
        
        if not query:
            messages = state.get("messages", [])
            if messages:
                last_msg = messages[-1]
                if isinstance(last_msg, dict):
                    query = last_msg.get("content", str(last_msg))
                else:
                    query = getattr(last_msg, "content", str(last_msg))
        return query

    def _normalize_results(self, raw_results: Any) -> list:
        if isinstance(raw_results, list):
            return raw_results
        elif isinstance(raw_results, dict) and "results" in raw_results:
            return raw_results["results"]
        else:
            return [raw_results] if raw_results else []

    def _emit_start(self, context, config, node_type, metadata):
        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        if emitter and context:
            node_id = context.get("node_id", f"{node_type}_node")
            node_name = config.get("name", node_type.capitalize())
            emitter.emit_node_start(node_id, node_name, node_type, metadata)

    def _emit_end(self, context, config, node_type, metadata, results):
        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        if emitter and context:
            node_id = context.get("node_id", f"{node_type}_node")
            node_name = config.get("name", node_type.capitalize())
            
            # Emit retrieval artifact
            normalized_results = []
            for r in results:
                if isinstance(r, dict):
                    normalized_results.append({
                        "id": r.get("id", str(uuid.uuid4())),
                        "score": r.get("score", 0),
                        "text": r.get("text", "") or r.get("content", ""),
                        "metadata": r.get("metadata", {})
                    })
                else:
                     normalized_results.append(r) # Best effort

            emitter.emit_retrieval(normalized_results, node_id)
            emitter.emit_node_end(node_id, node_name, node_type, metadata)

    def _emit_error(self, context, error_msg):
        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        if emitter and context:
            node_id = context.get("node_id", "unknown_node")
            emitter.emit_error(error_msg, node_id)


class VectorSearchNodeExecutor(BaseNodeExecutor):
    """
    Executes a direct Knowledge Store vector search.
    """
    async def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        if not config.get("knowledge_store_id"):
             return ValidationResult(valid=False, errors=["Missing 'knowledge_store_id' in configuration"])
        return ValidationResult(valid=True)

    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        store_id_str = config.get("knowledge_store_id")
        if not store_id_str:
            raise ValueError("Missing knowledge_store_id")

        # Reuse helper from RetrievalNodeExecutor or duplicate logic? 
        # Since they are separate classes, duplication is safer for now to avoid mixins complexity
        query = self._resolve_query(state, config)
        top_k = config.get("top_k", 10)

        self._emit_start(context, config, "vector_search", {"query": query, "store_id": store_id_str})

        try:
            store_id = UUID(store_id_str)
            
            retrieval_service = RetrievalService(self.db)
            search_results = await retrieval_service.query(
                store_id=store_id,
                query=query,
                top_k=top_k
            )
            
            results = [
                {
                    "id": r.id,
                    "score": r.score,
                    "text": r.text,
                    "metadata": r.metadata,
                }
                for r in search_results
            ]

            self._emit_end(context, config, "vector_search", {"results_count": len(results)}, results)

            return {
                "rag_output": results,
                "context": {
                    "search_results": results,
                    "last_query": query
                }
            }

        except Exception as e:
            logger.error(f"Knowledge Store query failed: {e}")
            self._emit_error(context, str(e))
            raise e

    def _resolve_query(self, state: Dict[str, Any], config: Dict[str, Any]) -> str:
        query_template = config.get("query", "")
        query = ""
        
        if query_template:
            try:
                query = evaluate_template(query_template, state)
            except Exception as e:
                logger.warning(f"Failed to interpolate query template: {e}")
                query = query_template
        
        if not query:
            messages = state.get("messages", [])
            if messages:
                last_msg = messages[-1]
                if isinstance(last_msg, dict):
                    query = last_msg.get("content", str(last_msg))
                else:
                    query = getattr(last_msg, "content", str(last_msg))
        return query

    def _emit_start(self, context, config, node_type, metadata):
        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        if emitter and context:
            node_id = context.get("node_id", f"{node_type}_node")
            node_name = config.get("name", "Vector Search")
            emitter.emit_node_start(node_id, node_name, node_type, metadata)

    def _emit_end(self, context, config, node_type, metadata, results):
        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        if emitter and context:
            node_id = context.get("node_id", f"{node_type}_node")
            node_name = config.get("name", "Vector Search")
            
            # Standardize for artifact
            normalized_results = []
            for r in results:
                 normalized_results.append({
                    "id": r.get("id"),
                    "score": r.get("score"),
                    "text": r.get("text"),
                    "metadata": r.get("metadata")
                })

            emitter.emit_retrieval(normalized_results, node_id)
            emitter.emit_node_end(node_id, node_name, node_type, metadata)

    def _emit_error(self, context, error_msg):
        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        if emitter and context:
            node_id = context.get("node_id", "unknown_node")
            emitter.emit_error(error_msg, node_id)
