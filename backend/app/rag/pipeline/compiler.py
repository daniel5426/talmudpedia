"""
Pipeline Compiler - Compiles visual pipelines to executable form.

Uses Pydantic models for compilation artifacts instead of MongoDB models.
"""
from typing import Dict, List, Optional, Any, Set, Tuple
from collections import defaultdict
from pydantic import BaseModel
from uuid import UUID
import enum


# Pydantic models for pipeline compilation (replacing MongoDB models)

class OperatorCategory(str, enum.Enum):
    SOURCE = "source"
    TRANSFORM = "transform"
    RETRIEVAL = "retrieval"
    LLM = "llm"
    OUTPUT = "output"
    CONTROL = "control"
    EMBEDDING = "embedding"
    STORAGE = "storage"


class PipelineNodePosition(BaseModel):
    x: float
    y: float


class PipelineNode(BaseModel):
    id: str
    category: OperatorCategory
    operator: str
    position: PipelineNodePosition
    config: Dict[str, Any] = {}


class PipelineEdge(BaseModel):
    id: str
    source: str
    target: str
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None


class VisualPipeline(BaseModel):
    """Pydantic model for visual pipeline (used in compilation)."""
    id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    org_unit_id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    nodes: List[PipelineNode] = []
    edges: List[PipelineEdge] = []
    version: int = 1
    is_published: bool = False

    class Config:
        from_attributes = True


class ExecutableStep(BaseModel):
    step_id: str
    operator: str
    category: OperatorCategory
    config: Dict[str, Any] = {}
    depends_on: List[str] = []


class ExecutablePipeline(BaseModel):
    """Compiled executable pipeline."""
    visual_pipeline_id: Optional[UUID] = None
    version: int
    tenant_id: Optional[UUID] = None
    dag: List[ExecutableStep] = []
    config_snapshot: Dict[str, Any] = {}
    is_valid: bool = True
    compiled_by: Optional[str] = None

    class Config:
        from_attributes = True


from app.rag.pipeline.registry import OperatorRegistry, DataType


class CompilationError(BaseModel):
    code: str
    message: str
    node_id: Optional[str] = None


class CompilationResult(BaseModel):
    success: bool
    errors: List[CompilationError] = []
    warnings: List[CompilationError] = []
    executable_pipeline: Optional[ExecutablePipeline] = None


class PipelineCompiler:

    def __init__(self, registry: Optional[OperatorRegistry] = None):
        self.registry = registry or OperatorRegistry.get_instance()

    def compile(
        self,
        visual_pipeline: Any,  # Accept any object with the required attributes
        compiled_by: Optional[str] = None
    ) -> CompilationResult:
        errors: List[CompilationError] = []
        warnings: List[CompilationError] = []

        # Convert to our internal model if needed
        pipeline = self._normalize_pipeline(visual_pipeline)

        if not pipeline.nodes:
            errors.append(CompilationError(
                code="EMPTY_PIPELINE",
                message="Pipeline has no nodes",
            ))
            return CompilationResult(success=False, errors=errors)

        structural_errors = self._validate_structure(pipeline)
        errors.extend(structural_errors)

        if errors:
            return CompilationResult(success=False, errors=errors)

        semantic_result = self._validate_semantics(pipeline)
        errors.extend(semantic_result["errors"])
        warnings.extend(semantic_result["warnings"])

        if errors:
            return CompilationResult(success=False, errors=errors, warnings=warnings)

        compatibility_errors = self._validate_compatibility(pipeline)
        errors.extend(compatibility_errors)

        if errors:
            return CompilationResult(success=False, errors=errors, warnings=warnings)

        ordered_steps = self._topological_sort(pipeline)
        if ordered_steps is None:
            errors.append(CompilationError(
                code="CYCLE_DETECTED",
                message="Pipeline contains a cycle",
            ))
            return CompilationResult(success=False, errors=errors, warnings=warnings)

        dag = self._build_dag(pipeline, ordered_steps)

        config_snapshot = self._build_config_snapshot(pipeline)

        executable = ExecutablePipeline(
            visual_pipeline_id=pipeline.id,
            version=pipeline.version,
            tenant_id=pipeline.tenant_id,
            dag=dag,
            config_snapshot=config_snapshot,
            is_valid=True,
            compiled_by=compiled_by,
        )

        return CompilationResult(
            success=True,
            errors=[],
            warnings=warnings,
            executable_pipeline=executable,
        )

    def _normalize_pipeline(self, visual_pipeline: Any) -> VisualPipeline:
        """Convert various pipeline representations to our internal model."""
        if isinstance(visual_pipeline, VisualPipeline):
            return visual_pipeline

        # Handle dict or other object types
        nodes = []
        raw_nodes = getattr(visual_pipeline, 'nodes', []) or []
        for node in raw_nodes:
            if isinstance(node, dict):
                # Convert category to enum if needed
                cat = node.get('category', 'transform')
                if isinstance(cat, str):
                    try:
                        cat = OperatorCategory(cat.lower())
                    except ValueError:
                        cat = OperatorCategory.TRANSFORM
                pos = node.get('position', {'x': 0, 'y': 0})
                nodes.append(PipelineNode(
                    id=node.get('id', ''),
                    category=cat,
                    operator=node.get('operator', ''),
                    position=PipelineNodePosition(**pos) if isinstance(pos, dict) else pos,
                    config=node.get('config', {}),
                ))
            elif hasattr(node, 'id'):
                cat = getattr(node, 'category', OperatorCategory.TRANSFORM)
                if isinstance(cat, str):
                    try:
                        cat = OperatorCategory(cat.lower())
                    except ValueError:
                        cat = OperatorCategory.TRANSFORM
                pos = getattr(node, 'position', None)
                if pos is None:
                    pos = PipelineNodePosition(x=0, y=0)
                elif isinstance(pos, dict):
                    pos = PipelineNodePosition(**pos)
                nodes.append(PipelineNode(
                    id=node.id,
                    category=cat,
                    operator=getattr(node, 'operator', ''),
                    position=pos,
                    config=getattr(node, 'config', {}),
                ))

        edges = []
        raw_edges = getattr(visual_pipeline, 'edges', []) or []
        for edge in raw_edges:
            if isinstance(edge, dict):
                edges.append(PipelineEdge(
                    id=edge.get('id', ''),
                    source=edge.get('source', ''),
                    target=edge.get('target', ''),
                    source_handle=edge.get('source_handle'),
                    target_handle=edge.get('target_handle'),
                ))
            elif hasattr(edge, 'id'):
                edges.append(PipelineEdge(
                    id=edge.id,
                    source=getattr(edge, 'source', ''),
                    target=getattr(edge, 'target', ''),
                    source_handle=getattr(edge, 'source_handle', None),
                    target_handle=getattr(edge, 'target_handle', None),
                ))

        return VisualPipeline(
            id=getattr(visual_pipeline, 'id', None),
            tenant_id=getattr(visual_pipeline, 'tenant_id', None),
            org_unit_id=getattr(visual_pipeline, 'org_unit_id', None),
            name=getattr(visual_pipeline, 'name', ''),
            description=getattr(visual_pipeline, 'description', None),
            nodes=nodes,
            edges=edges,
            version=getattr(visual_pipeline, 'version', 1),
            is_published=getattr(visual_pipeline, 'is_published', False),
        )

    def _validate_structure(self, pipeline: VisualPipeline) -> List[CompilationError]:
        errors = []

        nodes_by_category: Dict[str, List[PipelineNode]] = defaultdict(list)
        for node in pipeline.nodes:
            nodes_by_category[node.category.value].append(node)

        source_nodes = nodes_by_category.get("source", [])
        if len(source_nodes) == 0:
            errors.append(CompilationError(
                code="NO_SOURCE",
                message="Pipeline must have exactly one source node",
            ))
        elif len(source_nodes) > 1:
            errors.append(CompilationError(
                code="MULTIPLE_SOURCES",
                message=f"Pipeline has {len(source_nodes)} source nodes, expected 1",
            ))

        storage_nodes = nodes_by_category.get("storage", [])
        if len(storage_nodes) == 0:
            errors.append(CompilationError(
                code="NO_STORAGE",
                message="Pipeline must have exactly one storage node",
            ))
        elif len(storage_nodes) > 1:
            errors.append(CompilationError(
                code="MULTIPLE_STORAGE",
                message=f"Pipeline has {len(storage_nodes)} storage nodes, expected 1",
            ))

        transform_nodes = nodes_by_category.get("transform", [])
        if len(transform_nodes) == 0:
            errors.append(CompilationError(
                code="NO_TRANSFORM",
                message="Pipeline must have at least one transform (chunker) node",
            ))

        embedding_nodes = nodes_by_category.get("embedding", [])
        if len(embedding_nodes) == 0:
            errors.append(CompilationError(
                code="NO_EMBEDDING",
                message="Pipeline must have at least one embedding node",
            ))

        node_ids = {n.id for n in pipeline.nodes}
        for edge in pipeline.edges:
            if edge.source not in node_ids:
                errors.append(CompilationError(
                    code="INVALID_EDGE_SOURCE",
                    message=f"Edge references unknown source node: {edge.source}",
                ))
            if edge.target not in node_ids:
                errors.append(CompilationError(
                    code="INVALID_EDGE_TARGET",
                    message=f"Edge references unknown target node: {edge.target}",
                ))

        adjacency: Dict[str, Set[str]] = defaultdict(set)
        reverse_adjacency: Dict[str, Set[str]] = defaultdict(set)
        for edge in pipeline.edges:
            adjacency[edge.source].add(edge.target)
            reverse_adjacency[edge.target].add(edge.source)

        for node in source_nodes:
            if node.id in reverse_adjacency and reverse_adjacency[node.id]:
                errors.append(CompilationError(
                    code="SOURCE_HAS_INPUTS",
                    message=f"Source node '{node.id}' should not have incoming edges",
                    node_id=node.id,
                ))

        for node in storage_nodes:
            if node.id in adjacency and adjacency[node.id]:
                errors.append(CompilationError(
                    code="STORAGE_HAS_OUTPUTS",
                    message=f"Storage node '{node.id}' should not have outgoing edges",
                    node_id=node.id,
                ))

        reachable = self._get_reachable_nodes(pipeline, source_nodes)
        for node in pipeline.nodes:
            if node.id not in reachable:
                errors.append(CompilationError(
                    code="UNREACHABLE_NODE",
                    message=f"Node '{node.id}' is not reachable from source",
                    node_id=node.id,
                ))

        return errors

    def _get_reachable_nodes(
        self,
        pipeline: VisualPipeline,
        start_nodes: List[PipelineNode]
    ) -> Set[str]:
        adjacency: Dict[str, Set[str]] = defaultdict(set)
        for edge in pipeline.edges:
            adjacency[edge.source].add(edge.target)

        visited: Set[str] = set()
        stack = [n.id for n in start_nodes]

        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            for neighbor in adjacency[current]:
                if neighbor not in visited:
                    stack.append(neighbor)

        return visited

    def _validate_semantics(self, pipeline: VisualPipeline) -> Dict[str, List[CompilationError]]:
        errors = []
        warnings = []

        for node in pipeline.nodes:
            spec = self.registry.get(node.operator)
            if not spec:
                errors.append(CompilationError(
                    code="UNKNOWN_OPERATOR",
                    message=f"Unknown operator: {node.operator}",
                    node_id=node.id,
                ))
                continue

            config_errors = spec.validate_config(node.config)
            for err in config_errors:
                errors.append(CompilationError(
                    code="CONFIG_ERROR",
                    message=err,
                    node_id=node.id,
                ))

        return {"errors": errors, "warnings": warnings}

    def _validate_compatibility(self, pipeline: VisualPipeline) -> List[CompilationError]:
        errors = []

        node_map = {n.id: n for n in pipeline.nodes}

        for edge in pipeline.edges:
            source_node = node_map.get(edge.source)
            target_node = node_map.get(edge.target)

            if not source_node or not target_node:
                continue

            compatible, reason = self.registry.check_compatibility(
                source_node.operator,
                target_node.operator
            )

            if not compatible:
                errors.append(CompilationError(
                    code="TYPE_MISMATCH",
                    message=reason or "Incompatible connection",
                    node_id=edge.source,
                ))

        embedding_node = None
        storage_node = None
        for node in pipeline.nodes:
            spec = self.registry.get(node.operator)
            if spec:
                if spec.category == "embedding" and spec.dimension:
                    embedding_node = (node, spec)
                elif spec.category == "storage":
                    storage_node = (node, spec)

        return errors

    def _topological_sort(self, pipeline: VisualPipeline) -> Optional[List[str]]:
        adjacency: Dict[str, List[str]] = defaultdict(list)
        in_degree: Dict[str, int] = {n.id: 0 for n in pipeline.nodes}

        for edge in pipeline.edges:
            adjacency[edge.source].append(edge.target)
            in_degree[edge.target] = in_degree.get(edge.target, 0) + 1

        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            current = queue.pop(0)
            result.append(current)

            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(pipeline.nodes):
            return None

        return result

    def _build_dag(
        self,
        pipeline: VisualPipeline,
        ordered_node_ids: List[str]
    ) -> List[ExecutableStep]:
        node_map = {n.id: n for n in pipeline.nodes}

        reverse_adjacency: Dict[str, List[str]] = defaultdict(list)
        for edge in pipeline.edges:
            reverse_adjacency[edge.target].append(edge.source)

        dag = []
        for node_id in ordered_node_ids:
            node = node_map[node_id]
            step = ExecutableStep(
                step_id=node_id,
                operator=node.operator,
                category=node.category,
                config=node.config,
                depends_on=reverse_adjacency.get(node_id, []),
            )
            dag.append(step)

        return dag

    def _build_config_snapshot(self, pipeline: VisualPipeline) -> Dict[str, Any]:
        return {
            "name": pipeline.name,
            "description": pipeline.description,
            "node_count": len(pipeline.nodes),
            "edge_count": len(pipeline.edges),
            "operators": [n.operator for n in pipeline.nodes],
        }
