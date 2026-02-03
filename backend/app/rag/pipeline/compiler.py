"""
Pipeline Compiler - Compiles visual pipelines to executable form.

Features:
- Structural validation (DAG integrity, source/storage nodes)
- Semantic validation (operator configs, model capabilities)
- Type compatibility checking between operators
- Topological sorting for execution order
- Immutable execution plan generation with version locking
"""
from typing import Dict, List, Optional, Any, Set
from collections import defaultdict
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
import hashlib
import json

from app.db.postgres.models.rag import (
    VisualPipeline,
    ExecutablePipeline,
    PipelineType,
)
from app.rag.pipeline.registry import (
    OperatorSpec,
    OperatorRegistry,
)


class PipelineNodePosition(BaseModel):
    x: float
    y: float


class PipelineNode(BaseModel):
    id: str
    category: str  # String to allow flexibility, validated against registry
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
    pipeline_type: PipelineType = PipelineType.INGESTION
    version: int = 1
    is_published: bool = False

    class Config:
        from_attributes = True


class ExecutableStep(BaseModel):
    """A single step in the executable DAG."""
    step_id: str
    operator: str
    operator_version: str = "1.0.0"  # Locked operator version
    category: str
    config: Dict[str, Any] = {}
    depends_on: List[str] = []


class ExecutablePipeline(BaseModel):
    """
    Compiled executable pipeline.
    
    This is an immutable execution plan that captures:
    - The exact operator versions used
    - All configuration snapshots
    - A hash for integrity verification
    """
    visual_pipeline_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    pipeline_type: PipelineType = PipelineType.INGESTION
    dag: List[ExecutableStep] = []
    config_snapshot: Dict[str, Any] = {}
    
    # Immutability fields
    dag_hash: Optional[str] = None  # SHA-256 of serialized DAG
    locked_operator_versions: Dict[str, str] = {}
    compiled_at: Optional[datetime] = None
    compiled_by: Optional[str] = None
    
    is_valid: bool = True

    class Config:
        from_attributes = True

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of the DAG for integrity verification."""
        dag_json = json.dumps(
            [step.model_dump() for step in self.dag],
            sort_keys=True,
            default=str
        )
        return hashlib.sha256(dag_json.encode()).hexdigest()


class CompilationError(BaseModel):
    code: str
    message: str
    node_id: Optional[str] = None
    severity: str = "error"  # "error" or "warning"


class CompilationResult(BaseModel):
    success: bool
    errors: List[CompilationError] = []
    warnings: List[CompilationError] = []
    executable_pipeline: Optional[ExecutablePipeline] = None


class PipelineCompiler:
    """
    Compiles visual pipelines into executable form.
    
    The compilation process:
    1. Normalize the pipeline representation
    2. Validate structure (DAG, source/storage nodes)
    3. Validate semantics (operator configs)
    4. Validate type compatibility
    5. Topological sort for execution order
    6. Build immutable execution plan
    """

    def __init__(self, registry: Optional[OperatorRegistry] = None):
        self.registry = registry or OperatorRegistry.get_instance()

    def compile(
        self,
        visual_pipeline: Any,
        compiled_by: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> CompilationResult:
        """
        Compile a visual pipeline into an executable pipeline.
        
        This is the synchronous version that doesn't validate models.
        """
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

        # Structural validation
        structural_errors = self._validate_structure(pipeline)
        errors.extend(structural_errors)

        if errors:
            return CompilationResult(success=False, errors=errors)

        # Semantic validation
        semantic_result = self._validate_semantics(pipeline, tenant_id)
        errors.extend(semantic_result["errors"])
        warnings.extend(semantic_result["warnings"])

        if errors:
            return CompilationResult(success=False, errors=errors, warnings=warnings)

        # Compatibility validation
        compatibility_errors = self._validate_compatibility(pipeline, tenant_id)
        errors.extend(compatibility_errors)

        if errors:
            return CompilationResult(success=False, errors=errors, warnings=warnings)

        # Topological sort
        ordered_steps = self._topological_sort(pipeline)
        if ordered_steps is None:
            errors.append(CompilationError(
                code="CYCLE_DETECTED",
                message="Pipeline contains a cycle",
            ))
            return CompilationResult(success=False, errors=errors, warnings=warnings)

        # Build DAG with locked versions
        dag, locked_versions = self._build_dag(pipeline, ordered_steps, tenant_id)

        # Build config snapshot
        config_snapshot = self._build_config_snapshot(pipeline)

        # Create executable pipeline
        executable = ExecutablePipeline(
            visual_pipeline_id=pipeline.id,
            version=pipeline.version,
            tenant_id=pipeline.tenant_id,
            pipeline_type=pipeline.pipeline_type,
            dag=dag,
            config_snapshot=config_snapshot,
            locked_operator_versions=locked_versions,
            compiled_at=datetime.utcnow(),
            compiled_by=compiled_by,
            is_valid=True,
        )
        
        # Compute integrity hash
        executable.dag_hash = executable.compute_hash()

        return CompilationResult(
            success=True,
            errors=[],
            warnings=warnings,
            executable_pipeline=executable,
        )

    async def compile_async(
        self,
        visual_pipeline: Any,
        model_resolver: Any,
        compiled_by: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> CompilationResult:
        """
        Async compilation with model validation.
        
        Validates operators with required_capability against the ModelRegistry:
        - Model exists and is accessible to tenant
        - Model has correct capability type
        - Model is not disabled
        - Resolves dimension from model metadata
        """
        # First run synchronous compilation
        result = self.compile(visual_pipeline, compiled_by, tenant_id)
        if not result.success:
            return result
        
        # Validate models for operators with required_capability
        pipeline = self._normalize_pipeline(visual_pipeline)
        errors: List[CompilationError] = []
        warnings: List[CompilationError] = list(result.warnings)
        
        # Track resolved dimensions for downstream validation
        resolved_dimensions: Dict[str, int] = {}
        
        for node in pipeline.nodes:
            spec = self.registry.get(node.operator, tenant_id)
            if not spec or not spec.required_capability:
                continue
            
            # Get model_id from config
            model_id = node.config.get("model_id")
            if not model_id:
                errors.append(CompilationError(
                    code="MISSING_MODEL_ID",
                    message=f"Operator '{node.operator}' requires model_id",
                    node_id=node.id,
                ))
                continue
            
            try:
                # Validate model exists and has correct capability
                dimension = await model_resolver.get_model_dimension(model_id)
                resolved_dimensions[node.id] = dimension
                
            except Exception as e:
                errors.append(CompilationError(
                    code="MODEL_VALIDATION_ERROR",
                    message=str(e),
                    node_id=node.id,
                ))
        
        if errors:
            return CompilationResult(
                success=False,
                errors=errors,
                warnings=warnings,
            )
        
        # Add resolved dimensions to executable config
        if result.executable_pipeline:
            result.executable_pipeline.config_snapshot["resolved_dimensions"] = resolved_dimensions
        
        return result

    def _normalize_pipeline(self, visual_pipeline: Any) -> VisualPipeline:
        """Convert various pipeline representations to our internal model."""
        if isinstance(visual_pipeline, VisualPipeline):
            return visual_pipeline

        # Handle dict or other object types
        nodes = []
        raw_nodes = getattr(visual_pipeline, 'nodes', []) or []
        for node in raw_nodes:
            if isinstance(node, dict):
                # Handle ReactFlow format where metadata is in 'data'
                data = node.get('data', {})
                cat = data.get('category') or node.get('category', 'chunking')
                operator = data.get('operator') or node.get('operator', '')
                config = data.get('config') or node.get('config', {})
                
                pos = node.get('position', {'x': 0, 'y': 0})
                nodes.append(PipelineNode(
                    id=node.get('id', ''),
                    category=cat,
                    operator=operator,
                    position=PipelineNodePosition(**pos) if isinstance(pos, dict) else pos,
                    config=config,
                ))
            elif hasattr(node, 'id'):
                cat = getattr(node, 'category', 'chunking')
                if hasattr(cat, 'value'):
                    cat = cat.value
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
            pipeline_type=getattr(visual_pipeline, 'pipeline_type', PipelineType.INGESTION),
            version=getattr(visual_pipeline, 'version', 1),
            is_published=getattr(visual_pipeline, 'is_published', False),
        )

    def _validate_structure(self, pipeline: VisualPipeline) -> List[CompilationError]:
        """Validate pipeline structure (DAG, required nodes)."""
        errors = []

        nodes_by_category: Dict[str, List[PipelineNode]] = defaultdict(list)
        for node in pipeline.nodes:
            nodes_by_category[node.category].append(node)

        if pipeline.pipeline_type == PipelineType.INGESTION:
            # Check for source nodes
            source_nodes = nodes_by_category.get("source", [])
            if len(source_nodes) == 0:
                errors.append(CompilationError(
                    code="NO_SOURCE",
                    message="Ingestion pipeline must have at least one source node",
                ))

            # Check for storage nodes
            storage_nodes = nodes_by_category.get("storage", [])
            if len(storage_nodes) == 0:
                errors.append(CompilationError(
                    code="NO_STORAGE",
                    message="Ingestion pipeline must have at least one storage node",
                ))

            # Check for chunking nodes
            chunking_nodes = nodes_by_category.get("chunking", [])
            transform_nodes = nodes_by_category.get("transform", [])
            if len(chunking_nodes) == 0 and len(transform_nodes) == 0:
                errors.append(CompilationError(
                    code="NO_CHUNKING",
                    message="Ingestion pipeline must have at least one chunking node",
                ))

            # Check for embedding nodes
            embedding_nodes = nodes_by_category.get("embedding", [])
            if len(embedding_nodes) == 0:
                errors.append(CompilationError(
                    code="NO_EMBEDDING",
                    message="Ingestion pipeline must have at least one embedding node",
                ))

            entry_nodes = source_nodes
            exit_nodes = storage_nodes

        else: # RETRIEVAL
            # Check for query input nodes
            input_nodes = nodes_by_category.get("input", [])
            if len(input_nodes) == 0:
                errors.append(CompilationError(
                    code="NO_QUERY_INPUT",
                    message="Retrieval pipeline must have at least one query input node",
                ))
            elif len(input_nodes) > 1:
                errors.append(CompilationError(
                    code="MULTIPLE_QUERY_INPUTS",
                    message="Retrieval pipeline must have exactly one query input node",
                ))

            # Check for retrieval output nodes
            output_nodes = nodes_by_category.get("output", [])
            if len(output_nodes) == 0:
                errors.append(CompilationError(
                    code="NO_RETRIEVAL_RESULT",
                    message="Retrieval pipeline must have at least one retrieval result node",
                ))

            entry_nodes = input_nodes
            exit_nodes = output_nodes

        # Validate edge references
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

        # Build adjacency for reachability check
        adjacency: Dict[str, Set[str]] = defaultdict(set)
        reverse_adjacency: Dict[str, Set[str]] = defaultdict(set)
        for edge in pipeline.edges:
            adjacency[edge.source].add(edge.target)
            reverse_adjacency[edge.target].add(edge.source)

        # Entry nodes should not have inputs
        for node in entry_nodes:
            if node.id in reverse_adjacency and reverse_adjacency[node.id]:
                errors.append(CompilationError(
                    code="ENTRY_NODE_HAS_INPUTS",
                    message=f"Entry node '{node.id}' should not have incoming edges",
                    node_id=node.id,
                ))

        # Exit nodes should not have outputs
        for node in exit_nodes:
            if node.id in adjacency and adjacency[node.id]:
                errors.append(CompilationError(
                    code="EXIT_NODE_HAS_OUTPUTS",
                    message=f"Exit node '{node.id}' should not have outgoing edges",
                    node_id=node.id,
                ))

        # Check all nodes are reachable from entry nodes
        reachable = self._get_reachable_nodes(pipeline, entry_nodes)
        for node in pipeline.nodes:
            if node.id not in reachable:
                errors.append(CompilationError(
                    code="UNREACHABLE_NODE",
                    message=f"Node '{node.id}' is not reachable from entry nodes",
                    node_id=node.id,
                ))

        return errors

    def _get_reachable_nodes(
        self,
        pipeline: VisualPipeline,
        start_nodes: List[PipelineNode]
    ) -> Set[str]:
        """Get all nodes reachable from start nodes via BFS."""
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

    def _validate_semantics(
        self, 
        pipeline: VisualPipeline,
        tenant_id: Optional[str] = None
    ) -> Dict[str, List[CompilationError]]:
        """Validate operator configurations."""
        errors = []
        warnings = []

        for node in pipeline.nodes:
            spec = self.registry.get(node.operator, tenant_id)
            if not spec:
                errors.append(CompilationError(
                    code="UNKNOWN_OPERATOR",
                    message=f"Unknown operator: {node.operator}",
                    node_id=node.id,
                ))
                continue

            # Validate config against spec
            config_errors = spec.validate_config(node.config)
            for err in config_errors:
                errors.append(CompilationError(
                    code="CONFIG_ERROR",
                    message=err,
                    node_id=node.id,
                ))

            # Check for deprecated operators
            if spec.deprecated:
                warnings.append(CompilationError(
                    code="DEPRECATED_OPERATOR",
                    message=spec.deprecation_message or f"Operator '{node.operator}' is deprecated",
                    node_id=node.id,
                    severity="warning",
                ))

        return {"errors": errors, "warnings": warnings}

    def _validate_compatibility(
        self, 
        pipeline: VisualPipeline,
        tenant_id: Optional[str] = None
    ) -> List[CompilationError]:
        """Validate type compatibility between connected operators."""
        errors = []

        node_map = {n.id: n for n in pipeline.nodes}

        for edge in pipeline.edges:
            source_node = node_map.get(edge.source)
            target_node = node_map.get(edge.target)

            if not source_node or not target_node:
                continue

            compatible, reason = self.registry.check_compatibility(
                source_node.operator,
                target_node.operator,
                tenant_id
            )

            if not compatible:
                errors.append(CompilationError(
                    code="TYPE_MISMATCH",
                    message=reason or "Incompatible connection",
                    node_id=edge.source,
                ))

        return errors

    def _topological_sort(self, pipeline: VisualPipeline) -> Optional[List[str]]:
        """Topological sort of pipeline nodes (Kahn's algorithm)."""
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
            return None  # Cycle detected

        return result

    def _build_dag(
        self,
        pipeline: VisualPipeline,
        ordered_node_ids: List[str],
        tenant_id: Optional[str] = None
    ) -> tuple[List[ExecutableStep], Dict[str, str]]:
        """Build the executable DAG with locked operator versions."""
        node_map = {n.id: n for n in pipeline.nodes}
        locked_versions: Dict[str, str] = {}

        reverse_adjacency: Dict[str, List[str]] = defaultdict(list)
        for edge in pipeline.edges:
            reverse_adjacency[edge.target].append(edge.source)

        dag = []
        for node_id in ordered_node_ids:
            node = node_map[node_id]
            
            # Get operator version
            spec = self.registry.get(node.operator, tenant_id)
            version = spec.version if spec else "1.0.0"
            locked_versions[node.operator] = version
            
            step = ExecutableStep(
                step_id=node_id,
                operator=node.operator,
                operator_version=version,
                category=node.category,
                config=node.config,
                depends_on=reverse_adjacency.get(node_id, []),
            )
            dag.append(step)

        return dag, locked_versions

    def _build_config_snapshot(self, pipeline: VisualPipeline) -> Dict[str, Any]:
        """Build a configuration snapshot for audit purposes."""
        return {
            "name": pipeline.name,
            "description": pipeline.description,
            "node_count": len(pipeline.nodes),
            "edge_count": len(pipeline.edges),
            "operators": [n.operator for n in pipeline.nodes],
            "categories": list(set(n.category for n in pipeline.nodes)),
        }
