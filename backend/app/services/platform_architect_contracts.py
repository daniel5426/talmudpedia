from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


def _payload_schema(
    *,
    properties: Dict[str, Any],
    required: list[str] | None = None,
    additional_properties: bool = False,
) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required or []),
        "additionalProperties": additional_properties,
    }


def _list_payload_schema(
    *,
    properties: Dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> Dict[str, Any]:
    base_properties: Dict[str, Any] = {
        "skip": {"type": "integer", "minimum": 0},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        "view": {"type": "string", "enum": ["summary", "full"]},
    }
    base_properties.update(properties or {})
    return _payload_schema(
        properties=base_properties,
        required=required,
        additional_properties=False,
    )


PLATFORM_ARCHITECT_DOMAIN_TOOLS: Dict[str, Dict[str, Any]] = {
    "platform-rag": {
        "name": "Platform RAG",
        "description": "Domain tool for RAG visual pipeline operations in the control plane.",
        "actions": {
            "rag.list_visual_pipelines": {
                "mutation": False,
                "payload_schema": _list_payload_schema(),
                "contract": {
                    "summary": "List visual pipelines for an organization scope.",
                    "required_fields": [],
                    "example_payload": {"limit": 20, "skip": 0, "view": "summary"},
                    "failure_codes": ["UNAUTHORIZED", "ORGANIZATION_MISMATCH"],
                },
            },
            "rag.operators.catalog": {
                "mutation": False,
                "payload_schema": _payload_schema(properties={}, additional_properties=False),
                "contract": {
                    "summary": "List available RAG operators with categories, summaries, and required fields.",
                    "required_fields": [],
                    "example_payload": {},
                    "failure_codes": ["UNAUTHORIZED", "ORGANIZATION_MISMATCH"],
                },
            },
            "rag.operators.schema": {
                "mutation": False,
                "payload_schema": _payload_schema(
                    properties={
                        "operator_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    required=["operator_ids"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Resolve schemas/contracts for multiple RAG operators in one call, including config schema and exact visual-node/create contract shape.",
                    "required_fields": ["operator_ids"],
                    "example_payload": {"operator_ids": ["query_input", "knowledge_store_lookup"]},
                    "failure_codes": ["UNAUTHORIZED", "ORGANIZATION_MISMATCH", "VALIDATION_ERROR"],
                },
            },
            "rag.create_pipeline_shell": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "organization_id": {"type": "string"},
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "pipeline_type": {"type": "string", "enum": ["retrieval"]},
                    },
                    required=["name"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Create a draft retrieval pipeline shell with a minimal valid graph skeleton.",
                    "required_fields": ["name"],
                    "example_payload": {
                        "organization_id": "acme",
                        "name": "FAQ Pipeline",
                        "description": "Initial retrieval shell for FAQ search",
                        "pipeline_type": "retrieval",
                    },
                    "failure_codes": ["VALIDATION_ERROR", "SENSITIVE_ACTION_APPROVAL_REQUIRED"],
                    "notes": [
                        "Prefer this for first-time pipeline creation instead of authoring full nodes/edges.",
                        "Use rag.graph.* helpers or rag.update_visual_pipeline to enrich the shell after creation.",
                    ],
                },
            },
            "rag.create_visual_pipeline": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "pipeline_type": {"type": "string", "enum": ["ingestion", "retrieval"]},
                        "nodes": {"type": "array", "items": {"type": "object"}},
                        "edges": {"type": "array", "items": {"type": "object"}},
                    },
                    required=["name", "nodes", "edges"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Create a draft visual RAG pipeline.",
                    "required_fields": ["name", "nodes", "edges"],
                    "example_payload": {
                        "name": "FAQ Pipeline",
                        "pipeline_type": "retrieval",
                        "nodes": [
                            {"id": "n1", "category": "input", "operator": "query_input", "position": {"x": 80, "y": 120}, "config": {}},
                            {"id": "n2", "category": "embedding", "operator": "model_embedder", "position": {"x": 360, "y": 120}, "config": {"model_id": "model-123"}},
                            {"id": "n3", "category": "retrieval", "operator": "vector_search", "position": {"x": 640, "y": 120}, "config": {"knowledge_store_id": "ks-123"}},
                            {"id": "n4", "category": "output", "operator": "retrieval_result", "position": {"x": 920, "y": 120}, "config": {}},
                        ],
                        "edges": [
                            {"id": "e1", "source": "n1", "target": "n2"},
                            {"id": "e2", "source": "n2", "target": "n3"},
                            {"id": "e3", "source": "n3", "target": "n4"},
                        ],
                    },
                    "failure_codes": ["VALIDATION_ERROR", "SENSITIVE_ACTION_APPROVAL_REQUIRED"],
                    "notes": [
                        "Before constructing unfamiliar RAG operators, call rag.operators.catalog then rag.operators.schema.",
                        "For new pipelines, every node must include category, operator, and position; edges must include stable ids.",
                        "Retrieval pipelines must end in a retrieval_result output node before compile can succeed.",
                    ],
                },
            },
            "rag.update_visual_pipeline": {
                "mutation": True,
                "payload_schema": {
                    **_payload_schema(
                        properties={
                            "pipeline_id": {"type": "string"},
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "pipeline_type": {"type": "string", "enum": ["ingestion", "retrieval"]},
                            "nodes": {"type": "array", "items": {"type": "object"}},
                            "edges": {"type": "array", "items": {"type": "object"}},
                        },
                        additional_properties=False,
                    ),
                    "allOf": [
                        {"anyOf": [{"required": ["pipeline_id"]}, {"required": ["id"]}]},
                        {
                            "anyOf": [
                                {"required": ["name"]},
                                {"required": ["description"]},
                                {"required": ["nodes", "edges"]},
                            ]
                        },
                    ],
                    "dependentRequired": {"nodes": ["edges"], "edges": ["nodes"]},
                },
                "contract": {
                    "summary": "Update an existing visual RAG pipeline through direct graph-first fields.",
                    "required_fields": ["pipeline_id|id", "name|description|nodes+edges"],
                    "example_payload": {
                        "pipeline_id": "pipe-123",
                        "description": "patched",
                    },
                    "failure_codes": ["NOT_FOUND", "VALIDATION_ERROR"],
                },
            },
            "rag.graph.get": {
                "mutation": False,
                "payload_schema": _payload_schema(
                    properties={
                        "pipeline_id": {"type": "string"},
                        "id": {"type": "string"},
                    },
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Get the persisted graph for a visual pipeline.",
                    "required_fields": ["pipeline_id|id"],
                    "example_payload": {"pipeline_id": "pipe-123"},
                    "failure_codes": ["NOT_FOUND"],
                },
            },
            "rag.graph.validate_patch": {
                "mutation": False,
                "payload_schema": _payload_schema(
                    properties={
                        "pipeline_id": {"type": "string"},
                        "id": {"type": "string"},
                        "organization_id": {"type": "string"},
                        "operations": {"type": "array", "items": {"type": "object"}},
                    },
                    required=["operations"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Preview schema-aware graph mutation legality for a visual pipeline without persisting; runnability diagnostics are advisory.",
                    "required_fields": ["pipeline_id|id", "operations"],
                    "example_payload": {
                        "pipeline_id": "pipe-123",
                        "organization_id": "acme",
                        "operations": [{"op": "set_node_config_value", "node_id": "lookup_1", "path": "top_k", "value": 8}],
                    },
                    "failure_codes": ["NOT_FOUND", "GRAPH_MUTATION_ERROR"],
                },
            },
            "rag.graph.apply_patch": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "pipeline_id": {"type": "string"},
                        "id": {"type": "string"},
                        "organization_id": {"type": "string"},
                        "operations": {"type": "array", "items": {"type": "object"}},
                    },
                    required=["operations"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Apply legal graph mutation operations to a visual pipeline and return advisory diagnostics with the persisted draft graph.",
                    "required_fields": ["pipeline_id|id", "operations"],
                    "example_payload": {
                        "pipeline_id": "pipe-123",
                        "organization_id": "acme",
                        "operations": [{"op": "rewire_edge", "edge_id": "e1", "target": "answer_1"}],
                    },
                    "failure_codes": ["NOT_FOUND", "GRAPH_MUTATION_ERROR"],
                },
            },
            "rag.graph.attach_knowledge_store_to_node": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "pipeline_id": {"type": "string"},
                        "id": {"type": "string"},
                        "organization_id": {"type": "string"},
                        "node_id": {"type": "string"},
                        "knowledge_store_id": {"type": "string"},
                    },
                    required=["node_id", "knowledge_store_id"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Attach a knowledge store to an existing pipeline node without rebuilding the whole graph.",
                    "required_fields": ["pipeline_id|id", "node_id", "knowledge_store_id"],
                    "example_payload": {"pipeline_id": "pipe-123", "node_id": "lookup_1", "knowledge_store_id": "ks-123", "organization_id": "acme"},
                    "failure_codes": ["NOT_FOUND", "GRAPH_MUTATION_ERROR"],
                },
            },
            "rag.graph.set_pipeline_node_config": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "pipeline_id": {"type": "string"},
                        "id": {"type": "string"},
                        "organization_id": {"type": "string"},
                        "node_id": {"type": "string"},
                        "path": {"type": "string"},
                        "value": {},
                    },
                    required=["node_id", "path", "value"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Set one config field on an existing pipeline node through the graph mutation layer.",
                    "required_fields": ["pipeline_id|id", "node_id", "path", "value"],
                    "example_payload": {"pipeline_id": "pipe-123", "node_id": "lookup_1", "path": "top_k", "value": 8, "organization_id": "acme"},
                    "failure_codes": ["NOT_FOUND", "GRAPH_MUTATION_ERROR"],
                },
            },
            "rag.compile_visual_pipeline": {
                "mutation": True,
                "payload_schema": {
                    **_payload_schema(
                        properties={
                            "pipeline_id": {"type": "string"},
                            "id": {"type": "string"},
                        },
                        additional_properties=False,
                    ),
                    "anyOf": [{"required": ["pipeline_id"]}, {"required": ["id"]}],
                },
                "contract": {
                    "summary": "Compile a visual pipeline and return validation results.",
                    "required_fields": ["pipeline_id|id"],
                    "example_payload": {"pipeline_id": "pipe-123"},
                    "failure_codes": ["VALIDATION_ERROR", "INTERNAL_ERROR"],
                },
            },
            "rag.get_executable_pipeline": {
                "mutation": False,
                "payload_schema": _payload_schema(
                    properties={
                        "exec_id": {"type": "string"},
                        "executable_pipeline_id": {"type": "string"},
                        "id": {"type": "string"},
                    },
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Get compiled executable pipeline metadata.",
                    "required_fields": ["exec_id|executable_pipeline_id|id"],
                    "example_payload": {"exec_id": "exec-123"},
                    "failure_codes": ["NOT_FOUND"],
                },
            },
            "rag.get_executable_input_schema": {
                "mutation": False,
                "payload_schema": _payload_schema(
                    properties={
                        "exec_id": {"type": "string"},
                        "executable_pipeline_id": {"type": "string"},
                        "id": {"type": "string"},
                    },
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Get executable pipeline input schema.",
                    "required_fields": ["exec_id|executable_pipeline_id|id"],
                    "example_payload": {"exec_id": "exec-123"},
                    "failure_codes": ["NOT_FOUND"],
                },
            },
            "rag.create_job": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "executable_pipeline_id": {"type": "string"},
                        "input_params": {"type": "object"},
                    },
                    required=["executable_pipeline_id"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Run a pipeline job against an executable pipeline.",
                    "required_fields": ["executable_pipeline_id"],
                    "example_payload": {
                        "executable_pipeline_id": "exec-123",
                        "input_params": {"text": "hello"},
                    },
                    "failure_codes": ["VALIDATION_ERROR"],
                },
            },
            "rag.get_job": {
                "mutation": False,
                "payload_schema": _payload_schema(
                    properties={
                        "job_id": {"type": "string"},
                        "id": {"type": "string"},
                    },
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Get pipeline job execution state.",
                    "required_fields": ["job_id|id"],
                    "example_payload": {"job_id": "job-123"},
                    "failure_codes": ["NOT_FOUND"],
                },
            },
        },
    },
    "platform-agents": {
        "name": "Platform Agents",
        "description": "Domain tool for agent lifecycle and runs.",
        "actions": {
            "agents.list": {
                "mutation": False,
                "payload_schema": _list_payload_schema(
                    properties={
                        "status": {"type": "string"},
                    }
                ),
                "contract": {
                    "summary": "List agents.",
                    "required_fields": [],
                    "example_payload": {"status": "draft", "limit": 20, "skip": 0, "view": "summary"},
                    "failure_codes": ["UNAUTHORIZED"],
                },
            },
            "agents.get": {
                "mutation": False,
                "payload_schema": _payload_schema(
                    properties={"agent_id": {"type": "string"}, "id": {"type": "string"}},
                ),
                "contract": {
                    "summary": "Get agent by id.",
                    "required_fields": ["agent_id|id"],
                    "example_payload": {"agent_id": "agent-123"},
                    "failure_codes": ["NOT_FOUND"],
                },
            },
            "agents.create_shell": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    required=["name"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Create a draft agent shell with the minimal valid graph skeleton.",
                    "required_fields": ["name"],
                    "example_payload": {
                        "name": "FAQ Agent",
                        "description": "Initial draft shell for FAQ routing",
                    },
                    "failure_codes": ["VALIDATION_ERROR", "SENSITIVE_ACTION_APPROVAL_REQUIRED"],
                },
            },
            "agents.create": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "name": {"type": "string"},
                        "graph_definition": {"type": "object"},
                        "description": {"type": "string"},
                    },
                    required=["name", "graph_definition"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Create a draft agent with a valid non-empty graph_definition.",
                    "required_fields": ["name", "graph_definition"],
                    "example_payload": {
                        "name": "FAQ Agent",
                        "graph_definition": {
                            "spec_version": "2.0",
                            "nodes": [
                                {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
                                {"id": "assistant", "type": "agent", "position": {"x": 220, "y": 0}, "config": {"model_id": "model-123", "instructions": "Answer user questions clearly."}},
                                {"id": "end", "type": "end", "position": {"x": 460, "y": 0}, "config": {"output_variable": "context"}},
                            ],
                            "edges": [
                                {"id": "e1", "source": "start", "target": "assistant", "type": "control"},
                                {"id": "e2", "source": "assistant", "target": "end", "type": "control"},
                            ],
                        },
                    },
                    "failure_codes": ["VALIDATION_ERROR", "SENSITIVE_ACTION_APPROVAL_REQUIRED"],
                },
            },
            "agents.update": {
                "mutation": True,
                "payload_schema": {
                    **_payload_schema(
                        properties={
                            "agent_id": {"type": "string"},
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "graph_definition": {"type": "object"},
                            "memory_config": {"type": "object"},
                            "execution_constraints": {"type": "object"},
                            "show_in_playground": {"type": "boolean"},
                        },
                        additional_properties=False,
                    ),
                    "allOf": [
                        {"anyOf": [{"required": ["agent_id"]}, {"required": ["id"]}]},
                        {
                            "anyOf": [
                                {"required": ["name"]},
                                {"required": ["description"]},
                                {"required": ["graph_definition"]},
                                {"required": ["memory_config"]},
                                {"required": ["execution_constraints"]},
                                {"required": ["show_in_playground"]},
                            ]
                        },
                    ],
                },
                "contract": {
                    "summary": "Update an existing agent through direct graph-first fields.",
                    "required_fields": ["agent_id|id", "name|description|graph_definition|memory_config|execution_constraints|show_in_playground"],
                    "example_payload": {"agent_id": "agent-123", "description": "updated"},
                    "failure_codes": ["NOT_FOUND", "VALIDATION_ERROR"],
                },
            },
            "agents.graph.get": {
                "mutation": False,
                "payload_schema": _payload_schema(
                    properties={"agent_id": {"type": "string"}, "id": {"type": "string"}},
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Get the persisted graph for an agent.",
                    "required_fields": ["agent_id|id"],
                    "example_payload": {"agent_id": "agent-123"},
                    "failure_codes": ["NOT_FOUND"],
                },
            },
            "agents.graph.validate_patch": {
                "mutation": False,
                "payload_schema": _payload_schema(
                    properties={
                        "agent_id": {"type": "string"},
                        "id": {"type": "string"},
                        "operations": {"type": "array", "items": {"type": "object"}},
                    },
                    required=["operations"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Preview schema-aware graph mutation legality for an agent without persisting; runnability diagnostics are advisory.",
                    "required_fields": ["agent_id|id", "operations"],
                    "example_payload": {
                        "agent_id": "agent-123",
                        "operations": [{"op": "append_unique_node_config_list_item", "node_id": "assistant", "path": "tools", "value": "tool-123"}],
                    },
                    "failure_codes": ["NOT_FOUND", "GRAPH_MUTATION_ERROR", "GRAPH_WRITE_REJECTED"],
                },
            },
            "agents.graph.apply_patch": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "agent_id": {"type": "string"},
                        "id": {"type": "string"},
                        "operations": {"type": "array", "items": {"type": "object"}},
                    },
                    required=["operations"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Apply legal graph mutation operations to an agent and return advisory diagnostics with the persisted draft graph.",
                    "required_fields": ["agent_id|id", "operations"],
                    "example_payload": {
                        "agent_id": "agent-123",
                        "operations": [{"op": "set_node_config_value", "node_id": "assistant", "path": "instructions", "value": "Use web search when needed."}],
                    },
                    "failure_codes": ["NOT_FOUND", "GRAPH_MUTATION_ERROR", "GRAPH_WRITE_REJECTED"],
                },
            },
            "agents.graph.add_tool_to_agent_node": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "agent_id": {"type": "string"},
                        "id": {"type": "string"},
                        "node_id": {"type": "string"},
                        "tool_id": {"type": "string"},
                    },
                    required=["node_id", "tool_id"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Add a tool reference to an existing agent node without rebuilding the full graph.",
                    "required_fields": ["agent_id|id", "node_id", "tool_id"],
                    "example_payload": {"agent_id": "agent-123", "node_id": "assistant", "tool_id": "tool-123"},
                    "failure_codes": ["NOT_FOUND", "GRAPH_MUTATION_ERROR", "GRAPH_WRITE_REJECTED"],
                },
            },
            "agents.graph.remove_tool_from_agent_node": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "agent_id": {"type": "string"},
                        "id": {"type": "string"},
                        "node_id": {"type": "string"},
                        "tool_id": {"type": "string"},
                    },
                    required=["node_id", "tool_id"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Remove a tool reference from an existing agent node through the graph mutation layer.",
                    "required_fields": ["agent_id|id", "node_id", "tool_id"],
                    "example_payload": {"agent_id": "agent-123", "node_id": "assistant", "tool_id": "tool-123"},
                    "failure_codes": ["NOT_FOUND", "GRAPH_MUTATION_ERROR", "GRAPH_WRITE_REJECTED"],
                },
            },
            "agents.graph.set_agent_model": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "agent_id": {"type": "string"},
                        "id": {"type": "string"},
                        "node_id": {"type": "string"},
                        "model_id": {"type": "string"},
                    },
                    required=["node_id", "model_id"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Set model_id on an agent node through the graph mutation layer.",
                    "required_fields": ["agent_id|id", "node_id", "model_id"],
                    "example_payload": {"agent_id": "agent-123", "node_id": "assistant", "model_id": "model-123"},
                    "failure_codes": ["NOT_FOUND", "GRAPH_MUTATION_ERROR", "GRAPH_WRITE_REJECTED"],
                },
            },
            "agents.graph.set_agent_instructions": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "agent_id": {"type": "string"},
                        "id": {"type": "string"},
                        "node_id": {"type": "string"},
                        "instructions": {"type": "string"},
                    },
                    required=["node_id", "instructions"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Set instructions on an agent node through the graph mutation layer.",
                    "required_fields": ["agent_id|id", "node_id", "instructions"],
                    "example_payload": {"agent_id": "agent-123", "node_id": "assistant", "instructions": "Use web search when needed."},
                    "failure_codes": ["NOT_FOUND", "GRAPH_MUTATION_ERROR", "GRAPH_WRITE_REJECTED"],
                },
            },
            "agents.publish": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={"agent_id": {"type": "string"}, "id": {"type": "string"}},
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Publish agent (explicit publish intent required by policy).",
                    "required_fields": ["agent_id|id"],
                    "example_payload": {"agent_id": "agent-123"},
                    "failure_codes": ["DRAFT_FIRST_POLICY_DENIED", "SENSITIVE_ACTION_APPROVAL_REQUIRED"],
                },
            },
            "agents.validate": {
                "mutation": False,
                "payload_schema": {
                    **_payload_schema(
                        properties={
                            "agent_id": {"type": "string"},
                            "id": {"type": "string"},
                        },
                        additional_properties=False,
                    ),
                    "anyOf": [{"required": ["agent_id"]}, {"required": ["id"]}],
                },
                "contract": {
                    "summary": "Analyze an agent definition and return advisory compiler/runtime diagnostics.",
                    "required_fields": ["agent_id|id"],
                    "example_payload": {"agent_id": "agent-123"},
                    "failure_codes": ["VALIDATION_ERROR"],
                },
            },
            "agents.nodes.catalog": {
                "mutation": False,
                "payload_schema": _payload_schema(properties={}, additional_properties=False),
                "contract": {
                    "summary": "List available agent node/operator types and their contracts.",
                    "required_fields": [],
                    "example_payload": {},
                    "failure_codes": [],
                },
            },
            "agents.nodes.schema": {
                "mutation": False,
                "payload_schema": _payload_schema(
                    properties={"node_types": {"type": "array", "items": {"type": "string"}, "minItems": 1}},
                    required=["node_types"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Resolve schemas/contracts for multiple node types in one call.",
                    "required_fields": ["node_types"],
                    "example_payload": {"node_types": ["agent", "tool", "router"]},
                    "failure_codes": ["VALIDATION_ERROR"],
                },
            },
            "agents.nodes.validate": {
                "mutation": False,
                "payload_schema": _payload_schema(
                    properties={"agent_id": {"type": "string"}, "id": {"type": "string"}},
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Analyze the persisted agent graph by id with compiler and runtime reference checks.",
                    "required_fields": ["agent_id|id"],
                    "example_payload": {"agent_id": "agent-123"},
                    "failure_codes": ["VALIDATION_ERROR", "NOT_FOUND"],
                },
            },
            "agents.execute": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "agent_id": {"type": "string"},
                        "id": {"type": "string"},
                        "input": {"type": "string"},
                        "messages": {"type": "array"},
                        "context": {"type": "object"},
                    },
                    additional_properties=True,
                ),
                "contract": {
                    "summary": "Execute an agent run.",
                    "required_fields": ["agent_id|id"],
                    "example_payload": {"agent_id": "agent-123", "input": "health-check"},
                    "failure_codes": ["NOT_FOUND", "VALIDATION_ERROR"],
                },
            },
            "agents.start_run": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "agent_id": {"type": "string"},
                        "id": {"type": "string"},
                        "run": {"type": "object"},
                        "payload": {"type": "object"},
                    },
                    additional_properties=True,
                ),
                "contract": {
                    "summary": "Start a resumable run for an agent.",
                    "required_fields": ["agent_id|id"],
                    "example_payload": {"agent_id": "agent-123", "run": {"input": "hello"}},
                    "failure_codes": ["NOT_FOUND", "VALIDATION_ERROR"],
                },
            },
            "agents.get_run": {
                "mutation": False,
                "payload_schema": _payload_schema(
                    properties={"run_id": {"type": "string"}, "include_tree": {"type": "boolean"}},
                    required=["run_id"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Get run status.",
                    "required_fields": ["run_id"],
                    "example_payload": {"run_id": "run-123", "include_tree": False},
                    "failure_codes": ["NOT_FOUND"],
                },
            },
        },
    },
    "platform-assets": {
        "name": "Platform Assets",
        "description": "Domain tool for tools, artifacts, models, credentials, and knowledge stores.",
        "actions": {
            "tools.list": {
                "mutation": False,
                "payload_schema": _list_payload_schema(
                    properties={
                        "name": {"type": "string"},
                        "scope": {"type": "string"},
                        "is_active": {"type": "boolean"},
                        "status": {"type": "string"},
                        "implementation_type": {"type": "string"},
                        "tool_type": {"type": "string"},
                    }
                ),
                "contract": {
                    "summary": "List tools.",
                    "required_fields": [],
                    "example_payload": {"name": "FAQ Tool", "limit": 20, "skip": 0, "view": "summary", "is_active": True},
                    "failure_codes": [],
                },
            },
            "tools.get": {
                "mutation": False,
                "payload_schema": _payload_schema(properties={"tool_id": {"type": "string"}, "id": {"type": "string"}}),
                "contract": {"summary": "Get tool.", "required_fields": ["tool_id|id"], "example_payload": {"tool_id": "tool-123"}, "failure_codes": ["NOT_FOUND"]},
            },
            "tools.create": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "scope": {"type": "string"},
                        "input_schema": {"type": "object"},
                        "output_schema": {"type": "object"},
                        "config_schema": {"type": "object"},
                        "implementation_config": {"type": "object"},
                        "execution_config": {"type": "object"},
                        "implementation_type": {"type": "string"},
                        "status": {"type": "string"},
                        "is_active": {"type": "boolean"},
                        "artifact_id": {"type": "string"},
                        "artifact_version": {"type": "string"},
                    },
                    required=["name"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Create a tool draft.",
                    "required_fields": ["name"],
                    "example_payload": {"name": "My Tool"},
                    "failure_codes": ["VALIDATION_ERROR"],
                },
            },
            "tools.update": {
                "mutation": True,
                "payload_schema": {
                    **_payload_schema(
                        properties={
                            "tool_id": {"type": "string"},
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "scope": {"type": "string"},
                            "input_schema": {"type": "object"},
                            "output_schema": {"type": "object"},
                            "config_schema": {"type": "object"},
                            "implementation_config": {"type": "object"},
                            "execution_config": {"type": "object"},
                            "implementation_type": {"type": "string"},
                            "status": {"type": "string"},
                            "is_active": {"type": "boolean"},
                            "artifact_id": {"type": "string"},
                            "artifact_version": {"type": "string"},
                        },
                        additional_properties=False,
                    ),
                    "allOf": [
                        {"anyOf": [{"required": ["tool_id"]}, {"required": ["id"]}]},
                        {
                            "anyOf": [
                                {"required": ["name"]},
                                {"required": ["description"]},
                                {"required": ["scope"]},
                                {"required": ["input_schema"]},
                                {"required": ["output_schema"]},
                                {"required": ["config_schema"]},
                                {"required": ["implementation_config"]},
                                {"required": ["execution_config"]},
                                {"required": ["implementation_type"]},
                                {"required": ["status"]},
                                {"required": ["is_active"]},
                                {"required": ["artifact_id"]},
                                {"required": ["artifact_version"]},
                            ]
                        },
                    ],
                },
                "contract": {
                    "summary": "Update a tool draft.",
                    "required_fields": ["tool_id|id", "at least one update field"],
                    "example_payload": {"tool_id": "tool-123", "description": "Updated description"},
                    "failure_codes": ["VALIDATION_ERROR"],
                },
            },
            "tools.create_or_update": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={"tool_id": {"type": "string"}, "id": {"type": "string"}, "name": {"type": "string"}, "schema": {"type": "object"}, "config_schema": {"type": "object"}},
                    additional_properties=True,
                ),
                "contract": {"summary": "Create or update tool draft.", "required_fields": ["name|tool_id"], "example_payload": {"name": "My Tool"}, "failure_codes": ["VALIDATION_ERROR"]},
            },
            "tools.publish": {
                "mutation": True,
                "payload_schema": _payload_schema(properties={"tool_id": {"type": "string"}, "id": {"type": "string"}}),
                "contract": {"summary": "Publish tool version (explicit publish intent required).", "required_fields": ["tool_id|id"], "example_payload": {"tool_id": "tool-123"}, "failure_codes": ["DRAFT_FIRST_POLICY_DENIED", "SENSITIVE_ACTION_APPROVAL_REQUIRED"]},
            },
            "artifacts.list": {
                "mutation": False,
                "payload_schema": _list_payload_schema(),
                "contract": {
                    "summary": "List artifacts.",
                    "required_fields": [],
                    "example_payload": {"limit": 20, "skip": 0, "view": "summary"},
                    "failure_codes": [],
                },
            },
            "artifacts.get": {
                "mutation": False,
                "payload_schema": _payload_schema(properties={"artifact_id": {"type": "string"}, "id": {"type": "string"}}),
                "contract": {"summary": "Get artifact.", "required_fields": ["artifact_id|id"], "example_payload": {"artifact_id": "artifact-123"}, "failure_codes": ["NOT_FOUND"]},
            },
            "artifacts.create": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "display_name": {"type": "string"},
                        "description": {"type": "string"},
                        "kind": {"type": "string", "enum": ["agent_node", "rag_operator", "tool_impl"]},
                        "runtime": {"type": "object"},
                        "capabilities": {"type": "object"},
                        "config_schema": {"type": "object"},
                        "agent_contract": {"type": "object"},
                        "rag_contract": {"type": "object"},
                        "tool_contract": {"type": "object"},
                    },
                    required=["display_name", "kind", "runtime"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Create a canonical draft artifact.",
                    "required_fields": ["display_name", "kind", "runtime"],
                    "example_payload": {
                        "display_name": "Normalize Docs",
                        "description": "Tool implementation artifact.",
                        "kind": "tool_impl",
                        "runtime": {
                            "language": "python",
                            "source_files": [{"path": "main.py", "content": "async def execute(inputs, config, context):\n    return {\"ok\": True}"}],
                            "entry_module_path": "main.py",
                            "dependencies": [],
                            "runtime_target": "cloudflare_workers",
                        },
                        "capabilities": {"network_access": False, "allowed_hosts": [], "secret_refs": [], "storage_access": [], "side_effects": []},
                        "config_schema": {"type": "object", "properties": {}, "additionalProperties": True},
                        "tool_contract": {
                            "input_schema": {"type": "object", "additionalProperties": True},
                            "output_schema": {"type": "object", "additionalProperties": True},
                            "side_effects": [],
                            "execution_mode": "interactive",
                            "tool_ui": {},
                        },
                    },
                    "failure_codes": ["VALIDATION_ERROR"],
                },
            },
            "artifacts.update": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "artifact_id": {"type": "string"},
                        "id": {"type": "string"},
                        "patch": {"type": "object"},
                    },
                    required=["patch"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Patch an existing draft artifact with canonical artifact fields.",
                    "required_fields": ["artifact_id|id", "patch"],
                    "example_payload": {
                        "artifact_id": "artifact-123",
                        "patch": {
                            "description": "Updated description",
                            "runtime": {
                                "language": "python",
                                "source_files": [{"path": "main.py", "content": "async def execute(inputs, config, context):\n    return inputs"}],
                                "entry_module_path": "main.py",
                                "dependencies": [],
                                "runtime_target": "cloudflare_workers",
                            },
                        },
                    },
                    "failure_codes": ["NOT_FOUND", "VALIDATION_ERROR"],
                },
            },
            "artifacts.convert_kind": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "artifact_id": {"type": "string"},
                        "id": {"type": "string"},
                        "kind": {"type": "string", "enum": ["agent_node", "rag_operator", "tool_impl"]},
                        "agent_contract": {"type": "object"},
                        "rag_contract": {"type": "object"},
                        "tool_contract": {"type": "object"},
                    },
                    required=["kind"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Convert a draft artifact to a different canonical kind with the matching contract payload.",
                    "required_fields": ["artifact_id|id", "kind"],
                    "example_payload": {
                        "artifact_id": "artifact-123",
                        "kind": "tool_impl",
                        "tool_contract": {
                            "input_schema": {"type": "object", "additionalProperties": True},
                            "output_schema": {"type": "object", "additionalProperties": True},
                            "side_effects": [],
                            "execution_mode": "interactive",
                            "tool_ui": {},
                        },
                    },
                    "failure_codes": ["NOT_FOUND", "VALIDATION_ERROR"],
                },
            },
            "artifacts.create_test_run": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "artifact_id": {"type": "string"},
                        "source_files": {"type": "array", "items": {"type": "object"}},
                        "entry_module_path": {"type": "string"},
                        "input_data": {},
                        "config": {"type": "object"},
                        "dependencies": {"type": "array", "items": {"type": "string"}},
                        "kind": {"type": "string", "enum": ["agent_node", "rag_operator", "tool_impl"]},
                        "runtime_target": {"type": "string"},
                        "capabilities": {"type": "object"},
                        "config_schema": {"type": "object"},
                        "agent_contract": {"type": "object"},
                        "rag_contract": {"type": "object"},
                        "tool_contract": {"type": "object"},
                    },
                    required=["input_data"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Create a canonical artifact test run from a saved or ephemeral revision payload.",
                    "required_fields": ["input_data"],
                    "example_payload": {
                        "artifact_id": "artifact-123",
                        "input_data": {"items": [1, 2, 3]},
                        "config": {},
                    },
                    "failure_codes": ["VALIDATION_ERROR"],
                },
            },
            "artifacts.publish": {
                "mutation": True,
                "payload_schema": _payload_schema(properties={"artifact_id": {"type": "string"}, "id": {"type": "string"}}),
                "contract": {"summary": "Publish artifact draft (explicit publish intent required).", "required_fields": ["artifact_id|id"], "example_payload": {"artifact_id": "artifact-123"}, "failure_codes": ["DRAFT_FIRST_POLICY_DENIED", "SENSITIVE_ACTION_APPROVAL_REQUIRED"]},
            },
            "artifacts.delete": {
                "mutation": True,
                "payload_schema": _payload_schema(properties={"artifact_id": {"type": "string"}, "id": {"type": "string"}}, additional_properties=False),
                "contract": {
                    "summary": "Delete an artifact.",
                    "required_fields": ["artifact_id|id"],
                    "example_payload": {"artifact_id": "artifact-123"},
                    "failure_codes": ["NOT_FOUND"],
                },
            },
            "models.list": {
                "mutation": False,
                "payload_schema": _list_payload_schema(
                    properties={
                        "capability_type": {"type": "string"},
                        "status": {"type": "string"},
                        "is_active": {"type": "boolean"},
                    },
                ),
                "contract": {
                    "summary": "List models.",
                    "required_fields": [],
                    "example_payload": {"capability_type": "chat", "is_active": True, "limit": 20, "skip": 0, "view": "summary"},
                    "failure_codes": [],
                },
            },
            "models.create_or_update": {
                "mutation": True,
                "payload_schema": _payload_schema(properties={"model_id": {"type": "string"}, "id": {"type": "string"}, "name": {"type": "string"}}, additional_properties=True),
                "contract": {"summary": "Create or update model.", "required_fields": ["name|model_id"], "example_payload": {"name": "Model A"}, "failure_codes": ["VALIDATION_ERROR"]},
            },
            "prompts.list": {
                "mutation": False,
                "payload_schema": _list_payload_schema(
                    properties={
                        "q": {"type": "string"},
                        "status": {"type": "string", "enum": ["active", "archived"]},
                    },
                ),
                "contract": {
                    "summary": "List prompt library records visible in the current organization scope.",
                    "required_fields": [],
                    "example_payload": {"limit": 20, "skip": 0, "view": "summary", "status": "active"},
                    "failure_codes": [],
                },
            },
            "credentials.list": {
                "mutation": False,
                "payload_schema": _list_payload_schema(properties={"category": {"type": "string"}}),
                "contract": {
                    "summary": "List credentials.",
                    "required_fields": [],
                    "example_payload": {"category": "api", "limit": 20, "skip": 0, "view": "summary"},
                    "failure_codes": [],
                },
            },
            "credentials.create_or_update": {
                "mutation": True,
                "payload_schema": _payload_schema(properties={"credential_id": {"type": "string"}, "id": {"type": "string"}, "name": {"type": "string"}, "category": {"type": "string"}}, additional_properties=True),
                "contract": {"summary": "Create or update credential.", "required_fields": ["name|credential_id"], "example_payload": {"name": "OpenAI", "category": "api"}, "failure_codes": ["VALIDATION_ERROR"]},
            },
            "knowledge_stores.list": {
                "mutation": False,
                "payload_schema": _list_payload_schema(),
                "contract": {
                    "summary": "List knowledge stores.",
                    "required_fields": [],
                    "example_payload": {"limit": 20, "skip": 0, "view": "summary"},
                    "failure_codes": [],
                },
            },
            "knowledge_stores.create": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "embedding_model_id": {"type": "string"},
                        "chunking_strategy": {"type": "object"},
                        "retrieval_policy": {"type": "string"},
                        "backend": {"type": "string"},
                        "backend_config": {"type": "object"},
                        "credentials_ref": {"type": "string"},
                    },
                    required=["name", "embedding_model_id"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Create a knowledge store.",
                    "required_fields": ["name", "embedding_model_id"],
                    "example_payload": {"name": "kb", "embedding_model_id": "model-123"},
                    "failure_codes": ["VALIDATION_ERROR"],
                },
            },
            "knowledge_stores.update": {
                "mutation": True,
                "payload_schema": {
                    **_payload_schema(
                        properties={
                            "store_id": {"type": "string"},
                            "knowledge_store_id": {"type": "string"},
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "retrieval_policy": {"type": "string"},
                            "credentials_ref": {"type": "string"},
                        },
                        additional_properties=False,
                    ),
                    "allOf": [
                        {
                            "anyOf": [
                                {"required": ["store_id"]},
                                {"required": ["knowledge_store_id"]},
                                {"required": ["id"]},
                            ]
                        },
                        {
                            "anyOf": [
                                {"required": ["name"]},
                                {"required": ["description"]},
                                {"required": ["retrieval_policy"]},
                                {"required": ["credentials_ref"]},
                            ]
                        },
                    ],
                },
                "contract": {
                    "summary": "Update a knowledge store.",
                    "required_fields": ["store_id|knowledge_store_id|id", "at least one update field"],
                    "example_payload": {"store_id": "ks-123", "description": "Updated description"},
                    "failure_codes": ["VALIDATION_ERROR"],
                },
            },
            "knowledge_stores.create_or_update": {
                "mutation": True,
                "payload_schema": _payload_schema(properties={"store_id": {"type": "string"}, "id": {"type": "string"}, "organization_id": {"type": "string"}, "name": {"type": "string"}}, additional_properties=True),
                "contract": {"summary": "Create or update knowledge store.", "required_fields": ["organization_id", "name|store_id"], "example_payload": {"organization_id": "acme", "name": "kb"}, "failure_codes": ["VALIDATION_ERROR"]},
            },
        },
    },
    "platform-governance": {
        "name": "Platform Governance",
        "description": "Domain tool for governance-safe orchestration and control-plane coordination.",
        "actions": {
            "orchestration.join": {"mutation": False, "payload_schema": _payload_schema(properties={"caller_run_id": {"type": "string"}, "orchestration_group_id": {"type": "string"}}, additional_properties=True), "contract": {"summary": "Join orchestration group.", "required_fields": ["caller_run_id", "orchestration_group_id"], "example_payload": {"caller_run_id": "run-1", "orchestration_group_id": "grp-1"}, "failure_codes": ["NOT_FOUND"]}},
            "orchestration.cancel_subtree": {"mutation": True, "payload_schema": _payload_schema(properties={"caller_run_id": {"type": "string"}, "run_id": {"type": "string"}}, required=["caller_run_id", "run_id"], additional_properties=True), "contract": {"summary": "Cancel subtree run.", "required_fields": ["caller_run_id", "run_id"], "example_payload": {"caller_run_id": "run-1", "run_id": "run-2"}, "failure_codes": ["NOT_FOUND"]}},
            "orchestration.evaluate_and_replan": {"mutation": True, "payload_schema": _payload_schema(properties={"caller_run_id": {"type": "string"}, "run_id": {"type": "string"}}, required=["caller_run_id", "run_id"], additional_properties=True), "contract": {"summary": "Evaluate and replan run.", "required_fields": ["caller_run_id", "run_id"], "example_payload": {"caller_run_id": "run-1", "run_id": "run-2"}, "failure_codes": ["VALIDATION_ERROR"]}},
            "orchestration.query_tree": {"mutation": False, "payload_schema": _payload_schema(properties={"run_id": {"type": "string"}}, required=["run_id"], additional_properties=False), "contract": {"summary": "Query run tree.", "required_fields": ["run_id"], "example_payload": {"run_id": "run-1"}, "failure_codes": ["NOT_FOUND"]}},
        },
    },
}

PLATFORM_ARCHITECT_CANONICAL_ACTION_TOOL_KEYS: tuple[str, ...] = (
    "agents.list",
    "agents.get",
    "agents.create",
    "agents.update",
    "agents.graph.get",
    "agents.validate",
    "agents.nodes.catalog",
    "agents.nodes.schema",
    "agents.execute",
    "agents.get_run",
    "agents.publish",
    "rag.list_visual_pipelines",
    "rag.operators.catalog",
    "rag.operators.schema",
    "rag.create_visual_pipeline",
    "rag.update_visual_pipeline",
    "rag.graph.get",
    "rag.compile_visual_pipeline",
    "rag.get_executable_pipeline",
    "rag.get_executable_input_schema",
    "rag.create_job",
    "rag.get_job",
    "tools.list",
    "tools.get",
    "tools.create",
    "tools.update",
    "tools.publish",
    "artifacts.list",
    "artifacts.get",
    "artifacts.create",
    "artifacts.update",
    "artifacts.create_test_run",
    "artifacts.publish",
    "models.list",
    "credentials.list",
    "knowledge_stores.list",
    "knowledge_stores.create",
    "knowledge_stores.update",
)

PLATFORM_ARCHITECT_CANONICAL_WORKER_TOOL_KEYS: tuple[str, ...] = (
    "architect-worker-binding-prepare",
    "architect-worker-binding-persist-artifact",
    "architect-worker-spawn",
    "architect-worker-await",
    "architect-worker-respond",
)

PLATFORM_ARCHITECT_ACTION_DOMAIN_BY_ID: Dict[str, str] = {}
PLATFORM_ARCHITECT_ACTION_SPECS: Dict[str, Dict[str, Any]] = {}
for _domain_builtin_key, _domain_spec in PLATFORM_ARCHITECT_DOMAIN_TOOLS.items():
    for _action_id, _action_spec in _domain_spec["actions"].items():
        PLATFORM_ARCHITECT_ACTION_DOMAIN_BY_ID[_action_id] = _domain_builtin_key
        PLATFORM_ARCHITECT_ACTION_SPECS[_action_id] = _action_spec


def _request_metadata_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "trace_id": {"type": "string"},
            "request_id": {"type": "string"},
            "reason": {"type": "string"},
            "source": {"type": "string"},
        },
        "additionalProperties": True,
    }


def build_platform_domain_tool_schema(builtin_key: str, tool_spec: Dict[str, Any]) -> Dict[str, Any]:
    actions = tool_spec["actions"]
    action_names = list(actions.keys())
    one_of_variants: list[Dict[str, Any]] = []

    for action_name, action_spec in actions.items():
        variant: Dict[str, Any] = {
            "type": "object",
            "properties": {
                "action": {"const": action_name},
                "payload": action_spec["payload_schema"],
                "dry_run": {"type": "boolean"},
                "validate_only": {"type": "boolean"},
                "idempotency_key": {"type": "string"},
                "request_metadata": _request_metadata_schema(),
                "builtin_key": {"const": builtin_key},
                "organization_id": {"type": "string"},
            },
            "required": ["action", "payload"],
            "additionalProperties": False,
            "x-action-contract": {
                "action": action_name,
                **(action_spec.get("contract") or {}),
                "requires_mutation_controls": bool(action_spec.get("mutation")),
            },
        }
        one_of_variants.append(variant)

    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": action_names},
            "payload": {"type": "object"},
            "dry_run": {"type": "boolean"},
            "validate_only": {"type": "boolean"},
            "idempotency_key": {"type": "string"},
            "request_metadata": _request_metadata_schema(),
            "builtin_key": {"type": "string", "const": builtin_key},
            "organization_id": {"type": "string"},
        },
        "required": ["action", "payload"],
        "additionalProperties": False,
        "oneOf": one_of_variants,
    }
    output_schema = {
        "type": "object",
        "properties": {
            "result": {"type": "object"},
            "errors": {"type": "array", "items": {"type": "object"}},
            "action": {"type": "string"},
            "dry_run": {"type": "boolean"},
            "meta": {
                "type": "object",
                "properties": {
                    "trace_id": {"type": ["string", "null"]},
                    "request_id": {"type": ["string", "null"]},
                    "idempotency_key": {"type": ["string", "null"]},
                    "idempotency_provided": {"type": "boolean"},
                    "builtin_key": {"type": ["string", "null"]},
                },
                "additionalProperties": True,
            },
        },
        "additionalProperties": True,
    }
    return {"input": input_schema, "output": output_schema}


def build_platform_action_tool_schema(action_id: str) -> Dict[str, Any]:
    action_spec = PLATFORM_ARCHITECT_ACTION_SPECS[action_id]
    input_schema = deepcopy(action_spec["payload_schema"])
    input_properties = dict(input_schema.get("properties") or {})
    input_properties.update(
        {
            "dry_run": {"type": "boolean"},
            "validate_only": {"type": "boolean"},
            "idempotency_key": {"type": "string"},
            "request_metadata": _request_metadata_schema(),
        }
    )
    input_schema["properties"] = input_properties
    input_schema["x-action-contract"] = {
        "action": action_id,
        **(action_spec.get("contract") or {}),
        "requires_mutation_controls": bool(action_spec.get("mutation")),
    }
    output_schema = {
        "type": "object",
        "properties": {
            "result": {"type": "object"},
            "errors": {"type": "array", "items": {"type": "object"}},
            "action": {"type": "string"},
            "dry_run": {"type": "boolean"},
            "meta": {
                "type": "object",
                "properties": {
                    "trace_id": {"type": ["string", "null"]},
                    "request_id": {"type": ["string", "null"]},
                    "idempotency_key": {"type": ["string", "null"]},
                    "idempotency_provided": {"type": "boolean"},
                    "builtin_key": {"type": ["string", "null"]},
                },
                "additionalProperties": True,
            },
        },
        "additionalProperties": True,
    }
    return {"input": input_schema, "output": output_schema}


def build_architect_graph_definition(model_id: str, tool_ids: list[str] | None = None) -> dict:
    instructions = (
        "You are Platform Architect v2.0. "
        "Visible agent tools: agents.list, agents.get, agents.create, agents.update, agents.graph.get, agents.validate, agents.nodes.catalog, agents.nodes.schema, agents.execute, agents.get_run, agents.publish. "
        "Visible RAG tools: rag.list_visual_pipelines, rag.operators.catalog, rag.operators.schema, rag.create_visual_pipeline, rag.update_visual_pipeline, rag.graph.get, rag.compile_visual_pipeline, rag.get_executable_pipeline, rag.get_executable_input_schema, rag.create_job, rag.get_job. "
        "Visible asset tools: tools.list, tools.get, tools.create, tools.update, tools.publish, artifacts.list, artifacts.get, artifacts.create, artifacts.update, artifacts.create_test_run, artifacts.publish, models.list, credentials.list, knowledge_stores.list, knowledge_stores.create, knowledge_stores.update. "
        "Visible worker tools: architect-worker-binding-prepare, architect-worker-binding-persist-artifact, architect-worker-spawn, architect-worker-await, architect-worker-respond. "
        "The legacy domain container tools platform-rag, platform-agents, platform-assets, and platform-governance are not available here. "
        "Never call architect.run or invent meta actions. "
        "Each visible platform tool already fixes the action id. Send only the direct input fields for that tool. Do not send action, payload, query, text, or value wrappers. "
        "Use only exact visible tool names. Never invent aliases like create_agent, jobs.create, register_asset, or list-schema helpers. "
        "Workflow policy: extract intent and constraints, build a short plan, discover node/operator contracts when needed, author the full graph, rely on backend normalization/defaulting for mechanical fields, validate or compile, repair from structured errors, then run or publish only when the objective requires it. "
        "For agent graph discovery use agents.nodes.catalog and agents.nodes.schema only. "
        "For RAG operator discovery use rag.operators.catalog and rag.operators.schema only. "
        "Never use agents.nodes.* for RAG discovery and never invent unsupported actions like rag.nodes.catalog. "
        "Before introducing unfamiliar agent node types, call agents.nodes.catalog first and then agents.nodes.schema for all needed node_types in one call. "
        "Before introducing unfamiliar RAG operators, call rag.operators.catalog first and then rag.operators.schema for all needed operator_ids in one call. "
        "Graph-first authoring is the default path. Use agents.create for first agent creation and agents.update for graph updates. Use rag.create_visual_pipeline for first pipeline creation and rag.update_visual_pipeline for graph updates. "
        "Do not use shell or helper authoring patterns. Author the actual graph and let the backend normalize defaults. "
        "Never create empty graphs: agents and pipelines must include a minimal working node and edge skeleton. "
        "For agents.create and agents.update, send graph_definition and then use agents.validate as the repair checkpoint. "
        "For rag.create_visual_pipeline and rag.update_visual_pipeline, send nodes and edges at top level and use rag.compile_visual_pipeline as the repair checkpoint. "
        "For retrieval pipelines, include a retrieval_result output node. vector_search or reranker alone is not a valid final retrieval graph. "
        "For query_input, runtime query text is provided at execution time; do not hardcode placeholder query text into saved retrieval graphs unless the node schema explicitly requires a persisted default. "
        "If validation or compile returns structured errors, repair the graph from those exact paths instead of guessing. "
        "If rag.compile_visual_pipeline fails, repair that same pipeline first. Do not create duplicate replacement pipelines unless the user explicitly asked for an alternative design. "
        "Do not call rag.get_executable_pipeline or rag.get_executable_input_schema until rag.compile_visual_pipeline succeeds. "
        "Do not call rag.update_visual_pipeline with only pipeline_id or only unchanged metadata. Updates must include actual graph or field changes. "
        "For runtime agent execution, use agents.execute and poll agents.get_run until the run reaches a terminal state. Queued or running is not a completed result unless the user explicitly asked for a non-terminal snapshot. "
        "For runtime pipeline execution, use rag.create_job with executable_pipeline_id plus input_params only. If the executable input shape is unclear, call rag.get_executable_input_schema first and map input_params to the returned step-id shape. Poll rag.get_job until terminal state before reporting completion. "
        "If a graph node requires model_id and it is missing or rejected, call models.list, choose a valid active model, and retry. Do not ask the user for model_id unless models.list returns no usable models. "
        "For knowledge store creation flows, use knowledge_stores.create. Do not send organization_id. Resolve a valid embedding-capable model through models.list first, then send at minimum name plus embedding_model_id. Use knowledge_stores.update only for existing stores. "
        "When the user asks what platform tools are available, answer with the visible canonical tool ids above, grouped by family. Do not answer with only old domain container names. "
        "For code-heavy or multi-file artifact authoring, prepare an artifact_shared_draft binding with architect-worker-binding-prepare using canonical top-level fields only. The normal new-binding flow is prepare_mode=create_new_draft with title_prompt plus draft_seed.kind, and optionally draft_seed.language when the create flow should start in javascript instead of python. "
        "Language selection belongs to create flow only. Do not mutate artifact language after persistence and do not construct a full draft_snapshot for normal artifact creation. "
        "Spawn the artifact worker asynchronously with architect-worker-spawn using objective as a top-level field, then wait with architect-worker-await. "
        "If architect-worker-await returns waiting_for_input, continue the same worker with architect-worker-respond or surface the blocker to the user. That continuation stays on the worker's native thread; do not respawn a fresh worker just to send another turn. "
        "Artifact-coding delegated workers edit the shared draft only; they do not persist artifacts themselves. Use architect-worker-binding-persist-artifact for the persistence step when create or update is required. "
        "Do not invent nested fields like task.instructions, task.title, task.worker_agent, or generic binding_payload wrappers. Do not invent non-canonical binding fields such as create, files, entrypoint, or text. "
        "Do not ask a worker to mutate runtime-owned fields like persistence_readiness or platform asset payloads. "
        "If artifact code needs an existing credential reference, the worker should discover it through artifact_coding_list_credentials and then use only exact @{credential-id} string literals in source. Do not author mixed or embedded credential strings such as Bearer @{id}. "
        "If you used an artifact worker binding for a create or update task, you must not end the run after spawn alone. Before final completion you must persist through architect-worker-binding-persist-artifact yourself or return an explicit blocker explaining why persistence could not be completed. "
        "Do not treat successful worker completion as task completion by itself. "
        "If the worker finished but you need more changes, use architect-worker-respond to continue that same worker conversation and then await the latest child before any persistence decision. "
        "After delegated artifact changes, ensure the artifact is persisted exactly once, optionally run artifacts.create_test_run, and only then publish if explicit publish intent is present. "
        "If the requested output is an agent-callable tool, the normal lifecycle is: create or update a tool_impl artifact, persist the artifact, publish the artifact when required, create or update the bound tool row, and publish the tool so it pins artifact_revision_id. "
        "If the same mutation action fails twice with the same normalized error, stop mutating, summarize the blocker, and report the target resource, attempted action, normalized failure code, last validation details, whether any mutation succeeded, and the recommended next repair action. "
        "If a platform call fails due to non-canonical input or unsupported action, do not keep retrying the same malformed branch. "
        "Draft-first is mandatory: do not call publish actions unless objective_flags.allow_publish=true in user-provided input. "
        "Runtime organization context is authoritative for platform mutations. Never ask the user for organization_id, never rely on a user-supplied organization override, and operate only inside the current runtime organization. "
        "Idempotency keys and request metadata should be autogenerated from runtime context when absent; do not block on asking the user for them unless a caller explicitly requires custom values. "
    )

    return {
        "spec_version": "2.0",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {
                "id": "architect_runtime",
                "type": "agent",
                "position": {"x": 220, "y": 0},
                "config": {
                    "model_id": model_id,
                    "instructions": instructions,
                    "include_chat_history": True,
                    "temperature": 1,
                    "max_tool_iterations": 26,
                    "reasoning_effort": "medium",
                    "tools": list(tool_ids or []),
                    "write_output_to_context": True,
                },
            },
            {"id": "end", "type": "end", "position": {"x": 460, "y": 0}, "config": {"output_variable": "context"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "architect_runtime", "type": "control"},
            {"id": "e2", "source": "architect_runtime", "target": "end", "type": "control"},
        ],
    }
