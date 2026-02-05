import logging
import json
import hashlib
from typing import Any, Optional, Union, Set, Dict, List
from uuid import UUID
from pydantic import BaseModel
import jsonschema

from .schema import AgentGraph, AgentNode, AgentEdge, NodeType, EdgeType
from app.agent.registry import AgentOperatorRegistry, AgentStateField
from app.agent.models import CompiledAgent
from app.agent.graph.ir import GraphIR, GraphIRNode, GraphIREdge, RoutingMap

logger = logging.getLogger(__name__)

class ValidationError(BaseModel):
    """Validation error for agent graph."""
    node_id: Optional[str] = None
    edge_id: Optional[str] = None
    message: str
    severity: str = "error"


class AgentCompiler:
    """
    Compiles an AgentGraph definition into a runtime-agnostic GraphIR.
    Handles validation and normalization.
    """
    
    def __init__(self, tenant_id: Optional[UUID] = None, db: Any = None):
        self.tenant_id = tenant_id
        self.db = db

    async def validate(self, graph: AgentGraph) -> list[ValidationError]:
        """Validate the graph structure, configuration, and data flow."""
        errors = []
        from app.agent.executors.standard import register_standard_operators
        register_standard_operators()
        
        # 1. Structural Validation
        errors.extend(self._validate_structure(graph))
        
        # 2. Configuration Validation
        errors.extend(self._validate_configuration(graph))
        
        # 3. Data Flow Validation
        errors.extend(self._validate_data_flow(graph))
        
        # 4. Parallel Safety Validation
        errors.extend(self._validate_parallel_safety(graph))

        # 5. GraphSpec Version Validation
        errors.extend(self._validate_graphspec_version(graph))

        # 6. Routing Validation
        errors.extend(self._validate_routing(graph))

        # 7. Artifact Mapping Validation (lightweight)
        errors.extend(self._validate_artifact_mappings(graph))
        
        return errors

    def _validate_structure(self, graph: AgentGraph) -> list[ValidationError]:
        errors = []
        input_nodes = graph.get_input_nodes()
        if len(input_nodes) != 1:
            errors.append(ValidationError(message=f"Graph must have exactly one Start node (found {len(input_nodes)})"))
            
        output_nodes = graph.get_output_nodes()
        if not output_nodes:
            errors.append(ValidationError(message="Graph must have at least one End node"))

        # Reachability from Start
        adj = {n.id: [] for n in graph.nodes}
        for edge in graph.edges:
            if edge.source in adj and edge.target in adj:
                adj[edge.source].append(edge.target)
        
        if input_nodes:
            start_id = input_nodes[0].id
            visited = set()
            stack = [start_id]
            while stack:
                curr = stack.pop()
                if curr in visited:
                    continue
                visited.add(curr)
                for neighbor in adj[curr]:
                    stack.append(neighbor)
            
            for node in graph.nodes:
                if node.id not in visited:
                    errors.append(ValidationError(node_id=node.id, message="Node is unreachable from Start node"))
                    
        return errors

    def _validate_configuration(self, graph: AgentGraph) -> list[ValidationError]:
        errors = []
        for node in graph.nodes:
            normalized_type = self._normalize_node_type(node.type)
            spec = AgentOperatorRegistry.get(normalized_type)
            if not spec:
                errors.append(ValidationError(node_id=node.id, message=f"Unknown node type: {node.type}"))
                continue
            
            if spec.config_schema:
                try:
                    jsonschema.validate(instance=node.config, schema=spec.config_schema)
                except jsonschema.ValidationError as e:
                    errors.append(ValidationError(node_id=node.id, message=f"Config error: {e.message}"))
                
        return errors

    def _normalize_node_type(self, node_type: str) -> str:
        mapping = {
            "input": "start",
            "start": "start",
            "output": "end",
            "end": "end",
            "llm_call": "llm",
            "llm": "llm",
            "tool_call": "tool",
            "rag_retrieval": "rag",
        }
        return mapping.get(str(node_type), str(node_type))

    def _validate_data_flow(self, graph: AgentGraph) -> list[ValidationError]:
        errors = []
        node_writes: Dict[str, Set[AgentStateField]] = {}
        node_reads: Dict[str, Set[AgentStateField]] = {}
        
        for node in graph.nodes:
            spec = AgentOperatorRegistry.get(node.type)
            if spec:
                node_writes[node.id] = set(spec.writes)
                node_reads[node.id] = set(spec.reads)
            else:
                 node_writes[node.id] = set()
                 node_reads[node.id] = set()
        
        all_writes = set()
        for writes in node_writes.values():
            all_writes.update(writes)
            
        for node in graph.nodes:
            reads = node_reads[node.id]
            missing = reads - all_writes
            actual_missing = {f for f in missing if f not in [AgentStateField.MEMORY, AgentStateField.MESSAGE_HISTORY]}
            
            if actual_missing:
                errors.append(ValidationError(
                    node_id=node.id, 
                    message=f"Node requires {actual_missing}, but no node in graph produces it",
                    severity="warning"
                ))
        return errors

    def _validate_parallel_safety(self, graph: AgentGraph) -> list[ValidationError]:
        """
        Ensure parallel branches do not write to the same state fields.
        Strategies:
        1. Identify 'Parallel' nodes.
        2. Trace outgoing paths from Parallel node until a common convergence point (join) or end.
        3. Collect writes for each branch.
        4. Intersect writes. If non-empty, error.
        """
        errors = []
        # Find Parallel nodes
        parallel_nodes = [n for n in graph.nodes if n.type == "parallel"]
        
        adj = {n.id: [] for n in graph.nodes}
        for edge in graph.edges:
            if edge.source in adj and edge.target in adj:
                adj[edge.source].append(edge.target)

        node_writes_map = {}
        for node in graph.nodes:
            spec = AgentOperatorRegistry.get(node.type)
            node_writes_map[node.id] = set(spec.writes) if spec else set()

        for p_node in parallel_nodes:
            # Branches are neighbors of the parallel node
            branches = adj[p_node.id]
            if len(branches) < 2:
                continue # Not really parallel
            
            branch_writes = []
            
            # DFS for each branch to find reachable nodes (naive: finding all downstream)
            # This is tricky because branches eventually merge.
            # We need to stop at merge points? 
            # Or simplified: Check immediate neighbors.
            # "ParallelNodeExecutor is unsafe by default": It implies the *logic* of the parallel execution.
            # If the user connects Parallel -> A and Parallel -> B, then A and B run in parallel.
            # So we check A and B (and their sub-graphs until join).
            # For Phase 3, let's verify just the *first level* of the branches and maybe 2nd level if distinct.
            # Simpler robust check: Calculate reachable set for each branch head. Intersect node IDs. Common nodes are join points.
            # Exclude join points from write check.
            
            branch_reachability = []
            for b_node_id in branches:
                visited = set()
                stack = [b_node_id]
                writes_in_branch = set()
                
                # Limit depth or detect join?
                # Let's find common descendants first to exclude them.
                # Actually, simply checking if ANY two branches can reach a node that writes X is hard without dominant path analysis.
                # Heuristic: Check the immediate parallel nodes (the ones connected to Parallel node).
                # If they are distinct, check their writes.
                
                writes_in_branch.update(node_writes_map.get(b_node_id, set()))
                branch_writes.append(writes_in_branch)
            
            # Check pairwise intersection
            all_fields = set()
            conflict = False
            for i in range(len(branch_writes)):
                for j in range(i + 1, len(branch_writes)):
                    intersection = branch_writes[i].intersection(branch_writes[j])
                    if intersection:
                        errors.append(ValidationError(
                            node_id=p_node.id,
                            message=f"Parallel write conflict: Branches write to shared fields {intersection}",
                            severity="warning"
                        ))
                        conflict = True
                        break
                if conflict: break
                
        return errors

    def _validate_graphspec_version(self, graph: AgentGraph) -> list[ValidationError]:
        errors = []
        if graph.spec_version and graph.spec_version != "1.0":
            errors.append(ValidationError(message=f"Unsupported graph spec version: {graph.spec_version}"))
        return errors

    def _get_routing_handles(self, node: AgentNode) -> List[str]:
        node_type = self._normalize_node_type(node.type)
        if node_type == "if_else":
            conditions = node.config.get("conditions", []) if isinstance(node.config, dict) else []
            handles = [c.get("name") or f"condition_{i}" for i, c in enumerate(conditions)]
            handles.append("else")
            return handles
        if node_type == "classify":
            categories = node.config.get("categories", []) if isinstance(node.config, dict) else []
            return [c.get("name") or f"category_{i}" for i, c in enumerate(categories)]
        if node_type == "while":
            return ["loop", "exit"]
        if node_type == "user_approval":
            return ["approve", "reject"]
        if node_type == "conditional":
            return ["true", "false"]
        return []

    def _validate_routing(self, graph: AgentGraph) -> list[ValidationError]:
        errors: List[ValidationError] = []
        routing_nodes = {n.id: self._get_routing_handles(n) for n in graph.nodes if self._get_routing_handles(n)}
        edges_by_source: Dict[str, List[AgentEdge]] = {}
        for edge in graph.edges:
            edges_by_source.setdefault(edge.source, []).append(edge)

        for node_id, handles in routing_nodes.items():
            edges = edges_by_source.get(node_id, [])
            handle_targets = {}
            for edge in edges:
                if not edge.source_handle:
                    errors.append(ValidationError(node_id=node_id, edge_id=edge.id, message="Conditional edge missing source_handle"))
                    continue
                if edge.source_handle not in handles:
                    errors.append(ValidationError(node_id=node_id, edge_id=edge.id, message=f"Invalid branch handle '{edge.source_handle}'"))
                    continue
                if edge.source_handle in handle_targets:
                    errors.append(ValidationError(node_id=node_id, edge_id=edge.id, message=f"Duplicate branch handle '{edge.source_handle}'"))
                    continue
                handle_targets[edge.source_handle] = edge.target

            missing = [h for h in handles if h not in handle_targets]
            if missing:
                errors.append(ValidationError(node_id=node_id, message=f"Missing branch edges for handles: {missing}"))

        return errors

    def _validate_artifact_mappings(self, graph: AgentGraph) -> list[ValidationError]:
        errors: List[ValidationError] = []
        for node in graph.nodes:
            if isinstance(node.type, str) and node.type.startswith("artifact:"):
                if not node.input_mappings:
                    errors.append(ValidationError(
                        node_id=node.id,
                        message="Artifact node missing input_mappings",
                        severity="warning"
                    ))
        return errors

    async def compile(
        self,
        agent_id: UUID,
        version: int,
        graph: AgentGraph,
        config: Dict[str, Any] = None,
        input_params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> GraphIR:
        from app.agent.resolution import ToolResolver, RAGPipelineResolver, ResolutionError
        
        # 0. Resolve Components (Compile-time resolution)
        # We start by verifying and resolving external references.
        # This mutates the 'graph' object (or a copy) to bake in resolved IDs?
        # Ideally we update the 'config' of the nodes.
        
        tool_resolver = ToolResolver(self.db, self.tenant_id)
        rag_resolver = RAGPipelineResolver(self.db, self.tenant_id)
        
        for node in graph.nodes:
            if node.type == "tool":
                tool_id = node.config.get("tool_id")
                if tool_id:
                    try:
                        resolved = await tool_resolver.resolve(UUID(tool_id))
                        # Optimization: we could store 'resolved_implementation' in config
                        # node.config["_resolved"] = resolved
                    except ResolutionError as e:
                        raise ValueError(f"Tool resolution failed for node {node.id}: {e}")
            
            elif node.type == "rag":
                pipeline_id = node.config.get("pipeline_id")
                if pipeline_id:
                    try:
                        # RAG node config typically has 'pipeline_id'. 
                        # We verify it exists.
                        await rag_resolver.resolve(UUID(pipeline_id))
                    except ResolutionError as e:
                        raise ValueError(f"RAG resolution failed for node {node.id}: {e}")

            elif node.type == "agent":
                tools = node.config.get("tools") or []
                if tools:
                    if not isinstance(tools, list):
                        raise ValueError(f"Agent node {node.id} tools must be a list")
                    for tool_id in tools:
                        try:
                            await tool_resolver.resolve(UUID(str(tool_id)))
                        except (ValueError, ResolutionError) as e:
                            raise ValueError(f"Agent node {node.id} tool resolution failed: {e}")

        # 1. Validate
        errors = await self.validate(graph)
        critical_errors = [e for e in errors if e.severity == "error"]
        if critical_errors:
            error_msg = "; ".join([e.message for e in critical_errors])
            raise ValueError(f"Graph validation failed: {error_msg}")

        # 2. Build GraphIR
        graph_ir = self._build_graph_ir(graph, input_params=input_params)

        # 3. Create Compiled Snapshot
        graph_hash = hashlib.sha256(json.dumps(graph.dict(), sort_keys=True, default=str).encode()).hexdigest()
        
        final_config = (config or {}).copy()
        final_config.update(kwargs)

        snapshot = CompiledAgent(
            agent_id=agent_id,
            version=version,
            dag=graph.dict(),
            config=final_config,
            hash=graph_hash
        )
        graph_ir.metadata["snapshot"] = snapshot.model_dump()
        return graph_ir

    def _build_graph_ir(self, graph: AgentGraph, input_params: Optional[Dict[str, Any]] = None) -> GraphIR:
        routing_maps: Dict[str, RoutingMap] = {}
        for node in graph.nodes:
            handles = self._get_routing_handles(node)
            if not handles:
                continue
            edge_map: Dict[str, str] = {}
            for edge in graph.edges:
                if edge.source == node.id and edge.source_handle:
                    edge_map[edge.source_handle] = edge.target
            default_handle = "else" if "else" in handles else None
            routing_maps[node.id] = RoutingMap(handles=handles, edges=edge_map, default_handle=default_handle)

        input_nodes = graph.get_input_nodes()
        output_nodes = graph.get_output_nodes()

        if input_params is None:
            interrupt_before = [n.id for n in graph.nodes if n.type in ("human_input", "user_approval")]
        else:
            interrupt_before = []
            for node in graph.nodes:
                if node.type == "user_approval" and "approval" not in input_params:
                    interrupt_before.append(node.id)
                elif node.type == "human_input" and "input" not in input_params and "message" not in input_params:
                    interrupt_before.append(node.id)

        return GraphIR(
            schema_version=graph.spec_version or "1.0",
            nodes=[
                GraphIRNode(
                    id=n.id,
                    type=self._normalize_node_type(n.type),
                    config=n.config or {},
                    input_mappings=n.input_mappings,
                    data=n.data,
                )
                for n in graph.nodes
            ],
            edges=[
                GraphIREdge(
                    id=e.id,
                    source=e.source,
                    target=e.target,
                    source_handle=e.source_handle,
                    target_handle=e.target_handle,
                    type=str(e.type) if e.type else None,
                    label=e.label,
                    condition=e.condition,
                )
                for e in graph.edges
            ],
            entry_point=input_nodes[0].id if input_nodes else None,
            exit_nodes=[n.id for n in output_nodes],
            routing_maps=routing_maps,
            interrupt_before=interrupt_before,
        )
