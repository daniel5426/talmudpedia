from __future__ import annotations

from datetime import datetime
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph_authoring import (
    collect_rag_authoring_issues,
    dedupe_issues,
    get_rag_authoring_spec,
    normalize_rag_graph_definition,
)
from app.db.postgres.models.rag import VisualPipeline
from app.rag.pipeline.compiler import PipelineCompiler, VisualPipeline as CompilerVisualPipeline
from app.rag.pipeline.registry import OperatorRegistry
from app.services.graph_mutation_service import GraphMutationError, apply_graph_operations

logger = logging.getLogger(__name__)


class RagGraphMutationService:
    def __init__(self, db: AsyncSession, organization_id: UUID, project_id: UUID | None = None):
        self.db = db
        self.organization_id = organization_id
        self.project_id = project_id
        self.registry = OperatorRegistry.get_instance()

    async def get_graph(self, pipeline_id: UUID) -> dict[str, Any]:
        pipeline = await self._get_pipeline(pipeline_id)
        return {
            "pipeline_id": str(pipeline.id),
            "graph_definition": {
                "nodes": list(pipeline.nodes or []),
                "edges": list(pipeline.edges or []),
            },
            "pipeline_type": pipeline.pipeline_type.value if hasattr(pipeline.pipeline_type, "value") else pipeline.pipeline_type,
        }

    async def validate_patch(self, pipeline_id: UUID, operations: list[dict[str, Any]]) -> dict[str, Any]:
        pipeline = await self._get_pipeline(pipeline_id)
        current_graph = {"nodes": list(pipeline.nodes or []), "edges": list(pipeline.edges or [])}
        mutation = apply_graph_operations(
            current_graph,
            operations,
            validate_node_config_path=self._validate_node_config_path,
        )
        normalized_graph = normalize_rag_graph_definition(
            mutation.graph,
            organization_id=str(self.organization_id),
            registry=self.registry,
        )
        compile_result = self._compile_preview(pipeline, normalized_graph)
        return self._build_result(
            pipeline=pipeline,
            graph_definition=normalized_graph,
            mutation=mutation,
            compile_result=compile_result,
        )

    async def apply_patch(
        self,
        pipeline_id: UUID,
        operations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        phase = "preview_validation"
        try:
            preview = await self.validate_patch(pipeline_id, operations)

            phase = "persist_graph"
            pipeline = await self._get_pipeline(pipeline_id)
            pipeline.nodes = list(preview["graph_definition"].get("nodes") or [])
            pipeline.edges = list(preview["graph_definition"].get("edges") or [])
            if pipeline.is_published:
                pipeline.version = int(pipeline.version or 0) + 1
                pipeline.is_published = False
            pipeline.updated_at = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(pipeline)

            phase = "post_write_validation"
            compile_result = self._compile_preview(pipeline, preview["graph_definition"])
            return self._build_result(
                pipeline=pipeline,
                graph_definition=preview["graph_definition"],
                mutation=preview["mutation"],
                compile_result=compile_result,
            )
        except Exception as exc:
            setattr(exc, "graph_mutation_phase", phase)
            logger.exception(
                "RAG graph patch failed",
                extra={
                    "pipeline_id": str(pipeline_id),
                    "organization_id": str(getattr(self, "organization_id", "") or ""),
                    "phase": phase,
                    "operation_count": len(operations or []),
                },
            )
            raise

    async def attach_knowledge_store_to_node(
        self,
        pipeline_id: UUID,
        *,
        node_id: str,
        knowledge_store_id: str,
    ) -> dict[str, Any]:
        return await self.apply_patch(
            pipeline_id,
            [
                {
                    "op": "set_node_config_value",
                    "node_id": node_id,
                    "path": "knowledge_store_id",
                    "value": knowledge_store_id,
                }
            ],
        )

    async def set_pipeline_node_config(
        self,
        pipeline_id: UUID,
        *,
        node_id: str,
        path: str,
        value: Any,
    ) -> dict[str, Any]:
        return await self.apply_patch(
            pipeline_id,
            [
                {
                    "op": "set_node_config_value",
                    "node_id": node_id,
                    "path": path,
                    "value": value,
                }
            ],
        )

    async def _get_pipeline(self, pipeline_id: UUID) -> VisualPipeline:
        if self.project_id is None:
            raise GraphMutationError(
                [{"code": "ACTIVE_PROJECT_REQUIRED", "message": "Active project context is required"}]
            )
        result = await self.db.execute(
            select(VisualPipeline).where(
                VisualPipeline.id == pipeline_id,
                VisualPipeline.organization_id == self.organization_id,
                VisualPipeline.project_id == self.project_id,
            )
        )
        pipeline = result.scalar_one_or_none()
        if pipeline is None:
            raise GraphMutationError(
                [{"code": "RAG_PIPELINE_NOT_FOUND", "message": f"Pipeline '{pipeline_id}' was not found"}]
            )
        return pipeline

    def _compile_preview(self, pipeline: VisualPipeline, graph_definition: dict[str, Any]) -> Any:
        compiler = PipelineCompiler()
        visual_pipeline = CompilerVisualPipeline(
            id=pipeline.id,
            organization_id=pipeline.organization_id,
            org_unit_id=pipeline.org_unit_id,
            name=pipeline.name,
            description=pipeline.description,
            nodes=list(graph_definition.get("nodes") or []),
            edges=list(graph_definition.get("edges") or []),
            pipeline_type=pipeline.pipeline_type,
            version=pipeline.version,
            is_published=pipeline.is_published,
        )
        return compiler.compile(
            visual_pipeline,
            compiled_by=None,
            organization_id=str(self.organization_id),
        )

    def _validate_node_config_path(self, node: dict[str, Any], segments: list[str | int]) -> None:
        operator_id = str(node.get("operator") or "").strip()
        raw_spec = self.registry.get(operator_id, organization_id=str(self.organization_id))
        if raw_spec is None or not segments:
            return
        first_segment = segments[0]
        if isinstance(first_segment, int):
            raise GraphMutationError(
                [
                    {
                        "code": "GRAPH_MUTATION_INVALID_PATH",
                        "message": "RAG node config paths must begin with a field name",
                        "node_id": node.get("id"),
                    }
                ]
            )
        if hasattr(raw_spec, "operator_id"):
            spec = get_rag_authoring_spec(operator_id, organization_id=str(self.organization_id), registry=self.registry)
            config_schema = spec.config_schema if spec and isinstance(spec.config_schema, dict) else {}
            allowed = set(config_schema.get("properties", {}).keys()) if isinstance(config_schema.get("properties"), dict) else set()
        else:
            allowed = {
                str(getattr(field, "name", "") or "").strip()
                for field in list(getattr(raw_spec, "required_config", []) or []) + list(getattr(raw_spec, "optional_config", []) or [])
                if str(getattr(field, "name", "") or "").strip()
            }
        existing = set((node.get("config") or {}).keys()) if isinstance(node.get("config"), dict) else set()
        if allowed and first_segment not in allowed and first_segment not in existing:
            raise GraphMutationError(
                [
                    {
                        "code": "GRAPH_MUTATION_UNKNOWN_CONFIG_FIELD",
                        "message": f"Config field '{first_segment}' is not valid for pipeline operator '{operator_id}'",
                        "node_id": node.get("id"),
                        "path": ".".join(str(part) for part in segments),
                    }
                ]
            )

    @staticmethod
    def _build_result(
        *,
        pipeline: VisualPipeline,
        graph_definition: dict[str, Any],
        mutation: Any,
        compile_result: Any,
    ) -> dict[str, Any]:
        return {
            "pipeline_id": str(pipeline.id),
            "graph_definition": graph_definition,
            "mutation": {
                "applied_operations": list(getattr(mutation, "applied_operations", []) or []),
                "changed_node_ids": list(getattr(mutation, "changed_node_ids", []) or []),
                "changed_edge_ids": list(getattr(mutation, "changed_edge_ids", []) or []),
                "warnings": list(getattr(mutation, "warnings", []) or []),
            },
            "validation": {
                "valid": bool(getattr(compile_result, "success", False))
                and not any(
                    str(issue.get("severity") or "").lower() == "error"
                    for issue in collect_rag_authoring_issues(
                        graph_definition,
                        organization_id=str(pipeline.organization_id),
                    )
                ),
                "errors": dedupe_issues(
                    collect_rag_authoring_issues(
                        graph_definition,
                        organization_id=str(pipeline.organization_id),
                    )
                    + [
                        item.model_dump() if hasattr(item, "model_dump") else dict(item)
                        for item in list(getattr(compile_result, "errors", []) or [])
                    ]
                ),
                "warnings": [
                    item.model_dump() if hasattr(item, "model_dump") else dict(item)
                    for item in list(getattr(compile_result, "warnings", []) or [])
                ],
            },
        }
