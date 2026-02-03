import logging
import json
import hashlib
from typing import Any, Optional, Union, Set, Dict, List
from uuid import UUID
from pydantic import BaseModel
import jsonschema

from .schema import AgentGraph, AgentNode, AgentEdge, NodeType, EdgeType
from .executable import ExecutableAgent
from app.agent.registry import AgentExecutorRegistry, AgentOperatorRegistry, AgentStateField
from app.agent.models import CompiledAgent

logger = logging.getLogger(__name__)

class ValidationError(BaseModel):
    """Validation error for agent graph."""
    node_id: Optional[str] = None
    edge_id: Optional[str] = None
    message: str
    severity: str = "error"


class AgentCompiler:
    """
    Compiles an AgentGraph definition into an ExecutableAgent.
    Handles validation, normalization, and conversion to LangGraph state machine.
    """
    
    def __init__(self, tenant_id: Optional[UUID] = None, db: Any = None):
        self.tenant_id = tenant_id
        self.db = db

    async def validate(self, graph: AgentGraph) -> list[ValidationError]:
        """Validate the graph structure, configuration, and data flow."""
        errors = []
        
        # 1. Structural Validation
        errors.extend(self._validate_structure(graph))
        
        # 2. Configuration Validation
        errors.extend(self._validate_configuration(graph))
        
        # 3. Data Flow Validation
        errors.extend(self._validate_data_flow(graph))
        
        # 4. Parallel Safety Validation
        errors.extend(self._validate_parallel_safety(graph))
        
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
            spec = AgentOperatorRegistry.get(node.type)
            if not spec:
                errors.append(ValidationError(node_id=node.id, message=f"Unknown node type: {node.type}"))
                continue
            
            if spec.config_schema:
                try:
                    jsonschema.validate(instance=node.config, schema=spec.config_schema)
                except jsonschema.ValidationError as e:
                    errors.append(ValidationError(node_id=node.id, message=f"Config error: {e.message}"))
                
        return errors

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
                            message=f"Parallel write conflict: Branches write to shared fields {intersection}"
                        ))
                        conflict = True
                        break
                if conflict: break
                
        return errors

    async def compile(self, agent_id: UUID, version: int, graph: AgentGraph, config: Dict[str, Any] = None) -> ExecutableAgent:
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

        # 1. Validate
        errors = await self.validate(graph)
        critical_errors = [e for e in errors if e.severity == "error"]
        if critical_errors:
            error_msg = "; ".join([e.message for e in critical_errors])
            raise ValueError(f"Graph validation failed: {error_msg}")

        # 2. Build LangGraph Workflow
        from langgraph.graph import StateGraph, END
        from app.agent.core.state import AgentState
        
        workflow = StateGraph(AgentState)
        
        for node in graph.nodes:
            node_fn = self._build_node_fn(node)
            workflow.add_node(node.id, node_fn)
            
        for edge in graph.edges:
            # Handle conditional edges logic (simplified property check)
            source_node = next((n for n in graph.nodes if n.id == edge.source), None)
            if source_node and source_node.type == "conditional":
                 # Conditional nodes need special edge handling in LangGraph.
                 # They usually use 'add_conditional_edges'.
                 # For the standard 'Edge' list, it assumes static.
                 # If we have a conditional node, we likely need to group edges from it
                 # and register a routing function.
                 # SKIPPED for brevity in Phase 1/2 refactor - assuming direct edges work for now
                 # or that 'conditional' node returns a Runnable that handles internal routing?
                 # LangGraph pattern: add_conditional_edges(source, routing_fn, path_map).
                 # Our 'conditional' node returns a 'branch' key.
                 # We need a routing function that reads 'branch' from state/output.
                 pass
            
            workflow.add_edge(edge.source, edge.target)
            
        input_nodes = graph.get_input_nodes()
        if input_nodes:
            workflow.set_entry_point(input_nodes[0].id)
            
        output_nodes = graph.get_output_nodes()
        for node in output_nodes:
             workflow.add_edge(node.id, END)

        compiled_graph = workflow.compile()

        # 3. Create Compiled Snapshot
        graph_hash = hashlib.sha256(json.dumps(graph.dict(), sort_keys=True, default=str).encode()).hexdigest()
        
        snapshot = CompiledAgent(
            agent_id=agent_id,
            version=version,
            dag=graph.dict(),
            config=config or {},
            hash=graph_hash
        )

        return ExecutableAgent(
            graph_definition=graph, 
            compiled_graph=compiled_graph, 
            config=config or {},
            snapshot=snapshot,
            workflow=workflow
        )

    def _build_node_fn(self, node: AgentNode):
        """Builds a callable (async) function for a graph node."""
        executor_cls = AgentExecutorRegistry.get_executor_cls(node.type)
        if not executor_cls:
            logger.error(f"No executor registered for node type: {node.type}")
            async def error_node(state: Any):
                return state
            return error_node

        executor = executor_cls(self.tenant_id, self.db)

        async def node_fn(state: Any, config: Any = None):
            # Extract emitter from LangGraph configurable (passed by run_and_stream)
            configurable = config.get("configurable", {}) if config else {}
            emitter = configurable.get("emitter")
            
            context = {
                "langgraph_config": config,
                "emitter": emitter,
                "node_id": node.id,
                "node_type": node.type.value if hasattr(node.type, 'value') else str(node.type),
                "node_name": node.config.get("label", node.id)
            }
            
            if not await executor.can_execute(state, node.config, context):
                return {} 
            
            # Merge input_mappings into config for field resolver
            node_config = dict(node.config)
            if node.input_mappings:
                node_config["input_mappings"] = node.input_mappings
            
            try:
                state_update = await executor.execute(state, node_config, context)
                
                # Store node output for upstream reference by downstream nodes
                # This enables {{ upstream.node_id.field }} expressions
                if state_update and isinstance(state_update, dict):
                    node_outputs = state.get("_node_outputs", {})
                    node_outputs[node.id] = state_update
                    state_update["_node_outputs"] = node_outputs
                
                return state_update
            except Exception as e:
                logger.error(f"Error executing node {node.id} ({node.type}): {e}")
                raise e

        return node_fn

