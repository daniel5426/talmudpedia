import logging
import json
import hashlib
from typing import Any, Optional, Union, Set, Dict, List
from uuid import UUID
from pydantic import BaseModel
import jsonschema
from sqlalchemy import select

from .schema import AgentGraph, AgentNode, AgentEdge, NodeType, EdgeType
from app.agent.registry import AgentOperatorRegistry, AgentStateField
from app.agent.models import CompiledAgent
from app.agent.graph.ir import (
    GRAPH_SPEC_V1,
    GRAPH_SPEC_V2,
    ORCHESTRATION_V2_NODE_TYPES,
    GraphIR,
    GraphIRNode,
    GraphIREdge,
    RoutingMap,
)
from app.db.postgres.models.agents import Agent, AgentStatus
from app.db.postgres.models.orchestration import OrchestratorTargetAllowlist
from app.services.orchestration_policy_service import (
    DEFAULT_MAX_CHILDREN_TOTAL,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_FANOUT,
    ORCHESTRATION_SURFACE_OPTION_A,
    OrchestrationPolicyService,
    PolicySnapshot,
    is_orchestration_surface_enabled,
)

logger = logging.getLogger(__name__)

SUPPORTED_GRAPH_SPEC_VERSIONS = {GRAPH_SPEC_V1, GRAPH_SPEC_V2}

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

    async def validate(self, graph: AgentGraph, *, agent_id: Optional[UUID] = None) -> list[ValidationError]:
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

        # 8. GraphSpec v2 orchestration compile-time invariants
        errors.extend(await self._validate_graphspec_v2_orchestration(graph, agent_id=agent_id))
        
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
            spec = AgentOperatorRegistry.get(self._normalize_node_type(node.type))
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
        parallel_nodes = [n for n in graph.nodes if self._normalize_node_type(n.type) == "parallel"]
        
        adj = {n.id: [] for n in graph.nodes}
        for edge in graph.edges:
            if edge.source in adj and edge.target in adj:
                adj[edge.source].append(edge.target)

        node_writes_map = {}
        for node in graph.nodes:
            spec = AgentOperatorRegistry.get(self._normalize_node_type(node.type))
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
        if graph.spec_version and graph.spec_version not in SUPPORTED_GRAPH_SPEC_VERSIONS:
            errors.append(ValidationError(message=f"Unsupported graph spec version: {graph.spec_version}"))
            return errors

        has_v2_orchestration_nodes = any(
            self._normalize_node_type(node.type) in ORCHESTRATION_V2_NODE_TYPES
            for node in graph.nodes
        )
        effective_spec = graph.spec_version or GRAPH_SPEC_V1
        if has_v2_orchestration_nodes and effective_spec != GRAPH_SPEC_V2:
            errors.append(
                ValidationError(
                    message="GraphSpec v2 orchestration nodes require spec_version='2.0'"
                )
            )
        if has_v2_orchestration_nodes and not is_orchestration_surface_enabled(
            surface=ORCHESTRATION_SURFACE_OPTION_A,
            tenant_id=self.tenant_id,
        ):
            errors.append(
                ValidationError(
                    message="GraphSpec v2 orchestration is disabled by feature flag for this tenant"
                )
            )
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
        if node_type == "router":
            routes = node.config.get("routes", []) if isinstance(node.config, dict) else []
            handles: List[str] = []
            for idx, route in enumerate(routes):
                if isinstance(route, str):
                    name = route
                elif isinstance(route, dict):
                    name = route.get("name") or route.get("key") or route.get("handle")
                else:
                    name = None
                handles.append(name or f"route_{idx}")
            handles.append("default")
            return handles
        if node_type == "judge":
            outcomes = node.config.get("outcomes", []) if isinstance(node.config, dict) else []
            handles = [str(item) for item in outcomes if isinstance(item, str) and item.strip()]
            if not handles:
                handles = ["pass", "fail"]
            return handles
        if node_type == "join":
            return ["completed", "completed_with_errors", "failed", "timed_out", "pending"]
        if node_type == "replan":
            return ["replan", "continue"]
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

    async def _validate_graphspec_v2_orchestration(
        self,
        graph: AgentGraph,
        *,
        agent_id: Optional[UUID],
    ) -> list[ValidationError]:
        errors: List[ValidationError] = []
        node_by_id = {n.id: n for n in graph.nodes}
        orchestration_nodes = [
            n for n in graph.nodes
            if self._normalize_node_type(n.type) in ORCHESTRATION_V2_NODE_TYPES
        ]
        if not orchestration_nodes:
            return errors

        effective_spec = graph.spec_version or GRAPH_SPEC_V1
        if effective_spec != GRAPH_SPEC_V2:
            # Version mismatch is reported in _validate_graphspec_version.
            return errors

        max_depth = DEFAULT_MAX_DEPTH
        max_fanout = DEFAULT_MAX_FANOUT
        max_children_total = DEFAULT_MAX_CHILDREN_TOTAL
        policy: Optional[PolicySnapshot] = None
        allowlist_ids: set[str] = set()
        allowlist_slugs: set[str] = set()
        policy_targets_loaded = False

        if self.db is not None and self.tenant_id is not None and agent_id is not None:
            policy = await OrchestrationPolicyService(self.db).get_policy(self.tenant_id, agent_id)
            max_depth = int(policy.max_depth or DEFAULT_MAX_DEPTH)
            max_fanout = int(policy.max_fanout or DEFAULT_MAX_FANOUT)
            max_children_total = int(policy.max_children_total or DEFAULT_MAX_CHILDREN_TOTAL)

            allowlist_res = await self.db.execute(
                select(OrchestratorTargetAllowlist).where(
                    OrchestratorTargetAllowlist.tenant_id == self.tenant_id,
                    OrchestratorTargetAllowlist.orchestrator_agent_id == agent_id,
                    OrchestratorTargetAllowlist.is_active.is_(True),
                )
            )
            allowlist = list(allowlist_res.scalars().all())
            policy_targets_loaded = True
            allowlist_ids = {
                str(item.target_agent_id)
                for item in allowlist
                if item.target_agent_id is not None
            }
            allowlist_slugs = {
                str(item.target_agent_slug)
                for item in allowlist
                if item.target_agent_slug
            }

        incoming_by_target: Dict[str, List[AgentEdge]] = {}
        for edge in graph.edges:
            incoming_by_target.setdefault(edge.target, []).append(edge)

        target_refs: list[tuple[str, Optional[str], Optional[str]]] = []
        static_children_total = 0
        for node in orchestration_nodes:
            node_type = self._normalize_node_type(node.type)
            node_cfg = node.config or {}

            if node_type in {"spawn_run", "spawn_group"}:
                scope_subset = self._normalize_scope_subset(node_cfg.get("scope_subset"))
                if not scope_subset:
                    errors.append(
                        ValidationError(
                            node_id=node.id,
                            message="scope_subset is required for orchestration spawn nodes",
                        )
                    )
                elif policy is not None and policy.allowed_scope_subset:
                    allowed = set(policy.allowed_scope_subset or [])
                    if not set(scope_subset).issubset(allowed):
                        errors.append(
                            ValidationError(
                                node_id=node.id,
                                message="scope_subset exceeds orchestrator policy capability set",
                            )
                        )

            if node_type == "spawn_run":
                static_children_total += 1
                target_agent_id = self._as_text(node_cfg.get("target_agent_id"))
                target_agent_slug = self._as_text(node_cfg.get("target_agent_slug"))
                if not target_agent_id and not target_agent_slug:
                    errors.append(
                        ValidationError(
                            node_id=node.id,
                            message="spawn_run requires target_agent_id or target_agent_slug",
                        )
                    )
                else:
                    target_refs.append((node.id, target_agent_id, target_agent_slug))

            if node_type == "spawn_group":
                targets = node_cfg.get("targets", [])
                if not isinstance(targets, list) or not targets:
                    errors.append(
                        ValidationError(
                            node_id=node.id,
                            message="spawn_group requires a non-empty targets list",
                        )
                    )
                else:
                    static_children_total += len(targets)
                    if len(targets) > max_fanout:
                        errors.append(
                            ValidationError(
                                node_id=node.id,
                                message=f"spawn_group targets exceed max_fanout ({len(targets)} > {max_fanout})",
                            )
                        )
                    for idx, item in enumerate(targets):
                        item = item if isinstance(item, dict) else {}
                        target_agent_id = self._as_text(item.get("target_agent_id"))
                        target_agent_slug = self._as_text(item.get("target_agent_slug"))
                        if not target_agent_id and not target_agent_slug:
                            errors.append(
                                ValidationError(
                                    node_id=node.id,
                                    message=f"spawn_group target at index {idx} requires target_agent_id or target_agent_slug",
                                )
                            )
                        else:
                            target_refs.append((node.id, target_agent_id, target_agent_slug))

                join_mode = str(node_cfg.get("join_mode") or "all")
                if join_mode not in {"all", "best_effort", "fail_fast", "quorum", "first_success"}:
                    errors.append(
                        ValidationError(
                            node_id=node.id,
                            message=f"Unsupported spawn_group join_mode '{join_mode}'",
                        )
                    )
                if join_mode == "quorum":
                    quorum = node_cfg.get("quorum_threshold")
                    if not isinstance(quorum, int) or quorum < 1:
                        errors.append(
                            ValidationError(
                                node_id=node.id,
                                message="quorum_threshold must be >= 1 for join_mode='quorum'",
                            )
                        )

            if node_type == "join":
                mode = str(node_cfg.get("mode") or "all")
                if mode not in {"all", "best_effort", "fail_fast", "quorum", "first_success"}:
                    errors.append(
                        ValidationError(
                            node_id=node.id,
                            message=f"Unsupported join mode '{mode}'",
                        )
                    )
                if mode == "quorum":
                    quorum = node_cfg.get("quorum_threshold")
                    if not isinstance(quorum, int) or quorum < 1:
                        errors.append(
                            ValidationError(
                                node_id=node.id,
                                message="quorum_threshold must be >= 1 for mode='quorum'",
                            )
                        )

                incoming_types = self._incoming_types(node.id, node_by_id, incoming_by_target)
                has_group_id = bool(self._as_text(node_cfg.get("orchestration_group_id")))
                if not has_group_id and "spawn_group" not in incoming_types:
                    errors.append(
                        ValidationError(
                            node_id=node.id,
                            message="join requires orchestration_group_id or an incoming edge from spawn_group",
                        )
                    )

            if node_type == "router":
                routes = node_cfg.get("routes", [])
                if routes is not None and not isinstance(routes, list):
                    errors.append(
                        ValidationError(node_id=node.id, message="router routes must be a list")
                    )

            if node_type == "judge":
                incoming_types = self._incoming_types(node.id, node_by_id, incoming_by_target)
                if "join" not in incoming_types and "replan" not in incoming_types:
                    errors.append(
                        ValidationError(
                            node_id=node.id,
                            message="judge should receive input from join or replan nodes",
                            severity="warning",
                        )
                    )

            if node_type in {"replan", "cancel_subtree"}:
                has_run_id = bool(self._as_text(node_cfg.get("run_id")))
                incoming_types = self._incoming_types(node.id, node_by_id, incoming_by_target)
                has_run_lineage_source = bool(
                    incoming_types.intersection({"spawn_run", "spawn_group", "join", "judge", "replan"})
                )
                if not has_run_id and not has_run_lineage_source:
                    errors.append(
                        ValidationError(
                            node_id=node.id,
                            message=f"{node_type} requires run_id or incoming lineage-producing orchestration edges",
                        )
                    )

        if static_children_total > max_children_total:
            errors.append(
                ValidationError(
                    message=f"Static orchestration fanout exceeds max_children_total ({static_children_total} > {max_children_total})"
                )
            )

        depth_count, cycle_has_spawn = self._estimate_spawn_depth(graph, node_by_id)
        if cycle_has_spawn:
            errors.append(
                ValidationError(
                    message="Orchestration spawn cycle detected; static depth cannot be bounded safely",
                )
            )
        if depth_count > max_depth:
            errors.append(
                ValidationError(
                    message=f"Potential spawn depth exceeds max_depth ({depth_count} > {max_depth})",
                )
            )

        if not target_refs:
            return errors

        if policy_targets_loaded and not allowlist_ids and not allowlist_slugs:
            errors.append(
                ValidationError(
                    message="Orchestrator has no target allowlist entries",
                )
            )
            return errors

        if self.db is None or self.tenant_id is None:
            errors.append(
                ValidationError(
                    message="Skipping compile-time target eligibility checks (no DB/tenant context available)",
                    severity="warning",
                )
            )
            return errors

        by_id = {target_id for _node_id, target_id, _slug in target_refs if target_id}
        by_slug = {slug for _node_id, _target_id, slug in target_refs if slug}
        resolved_by_id: Dict[str, Agent] = {}
        resolved_by_slug: Dict[str, Agent] = {}

        if by_id:
            target_rows = await self.db.execute(
                select(Agent).where(
                    Agent.tenant_id == self.tenant_id,
                    Agent.id.in_(list(by_id)),
                )
            )
            for item in target_rows.scalars().all():
                resolved_by_id[str(item.id)] = item

        if by_slug:
            target_rows = await self.db.execute(
                select(Agent).where(
                    Agent.tenant_id == self.tenant_id,
                    Agent.slug.in_(list(by_slug)),
                )
            )
            for item in target_rows.scalars().all():
                resolved_by_slug[str(item.slug)] = item

        for node_id, target_id, target_slug in target_refs:
            target = resolved_by_id.get(target_id) if target_id else None
            if target is None and target_slug:
                target = resolved_by_slug.get(target_slug)

            if target is None:
                errors.append(
                    ValidationError(
                        node_id=node_id,
                        message=f"Orchestration target not found for tenant (id={target_id}, slug={target_slug})",
                    )
                )
                continue

            if policy_targets_loaded:
                allowed = str(target.id) in allowlist_ids or str(target.slug) in allowlist_slugs
                if not allowed:
                    errors.append(
                        ValidationError(
                            node_id=node_id,
                            message=f"Target '{target.slug}' is not allowlisted for this orchestrator",
                        )
                    )

            if policy is not None and policy.enforce_published_only:
                target_status = target.status.value if hasattr(target.status, "value") else str(target.status)
                if target_status != AgentStatus.published.value:
                    errors.append(
                        ValidationError(
                            node_id=node_id,
                            message=f"Target '{target.slug}' is not published",
                        )
                    )

        return errors

    def _incoming_types(
        self,
        node_id: str,
        node_by_id: Dict[str, AgentNode],
        incoming_by_target: Dict[str, List[AgentEdge]],
    ) -> set[str]:
        incoming = incoming_by_target.get(node_id, [])
        types: set[str] = set()
        for edge in incoming:
            source = node_by_id.get(edge.source)
            if source is None:
                continue
            types.add(self._normalize_node_type(source.type))
        return types

    def _estimate_spawn_depth(
        self,
        graph: AgentGraph,
        node_by_id: Dict[str, AgentNode],
    ) -> tuple[int, bool]:
        adjacency: Dict[str, List[str]] = {node.id: [] for node in graph.nodes}
        for edge in graph.edges:
            adjacency.setdefault(edge.source, []).append(edge.target)

        spawn_nodes = {"spawn_run", "spawn_group"}
        max_depth = 0
        cycle_has_spawn = False

        def walk(node_id: str, path: List[str], depth_count: int) -> None:
            nonlocal max_depth, cycle_has_spawn
            if node_id in path:
                cycle_nodes = path[path.index(node_id):] + [node_id]
                if any(
                    self._normalize_node_type(node_by_id.get(item).type) in spawn_nodes
                    for item in cycle_nodes
                    if node_by_id.get(item) is not None
                ):
                    cycle_has_spawn = True
                return

            node = node_by_id.get(node_id)
            if node is None:
                return

            next_depth = depth_count + (
                1 if self._normalize_node_type(node.type) in spawn_nodes else 0
            )
            max_depth = max(max_depth, next_depth)

            next_path = path + [node_id]
            for target_id in adjacency.get(node_id, []):
                walk(target_id, next_path, next_depth)

        start_nodes = graph.get_input_nodes()
        roots = [n.id for n in start_nodes] if start_nodes else list(node_by_id.keys())
        for root in roots:
            walk(root, [], 0)

        return max_depth, cycle_has_spawn

    @staticmethod
    def _normalize_scope_subset(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if isinstance(item, str) and item.strip()]

    @staticmethod
    def _as_text(value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        return str(value)

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
        errors = await self.validate(graph, agent_id=agent_id)
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
            default_handle = None
            if "else" in handles:
                default_handle = "else"
            elif "default" in handles:
                default_handle = "default"
            elif "pending" in handles:
                default_handle = "pending"
            routing_maps[node.id] = RoutingMap(handles=handles, edges=edge_map, default_handle=default_handle)

        input_nodes = graph.get_input_nodes()
        output_nodes = graph.get_output_nodes()

        if input_params is None:
            interrupt_before = [n.id for n in graph.nodes if n.type in ("human_input", "user_approval")]
        else:
            interrupt_before = []
            for node in graph.nodes:
                if node.type == "user_approval":
                    if "approval" not in input_params:
                        interrupt_before.append(node.id)
                elif node.type == "human_input":
                    if "input" not in input_params and "message" not in input_params:
                        interrupt_before.append(node.id)

        return GraphIR(
            schema_version=graph.spec_version or GRAPH_SPEC_V1,
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
