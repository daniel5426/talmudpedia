from __future__ import annotations

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


PLATFORM_ARCHITECT_DOMAIN_TOOLS: Dict[str, Dict[str, Any]] = {
    "platform-rag": {
        "name": "Platform RAG",
        "description": "Domain tool for RAG visual pipeline operations in the control plane.",
        "actions": {
            "rag.list_visual_pipelines": {
                "mutation": False,
                "payload_schema": _payload_schema(
                    properties={"tenant_slug": {"type": "string"}},
                ),
                "contract": {
                    "summary": "List visual pipelines for a tenant scope.",
                    "required_fields": [],
                    "example_payload": {"tenant_slug": "acme"},
                    "failure_codes": ["UNAUTHORIZED", "TENANT_MISMATCH"],
                },
            },
            "rag.operators.catalog": {
                "mutation": False,
                "payload_schema": _payload_schema(
                    properties={"tenant_slug": {"type": "string"}},
                ),
                "contract": {
                    "summary": "List available RAG operators with categories, summaries, and required fields.",
                    "required_fields": [],
                    "example_payload": {"tenant_slug": "acme"},
                    "failure_codes": ["UNAUTHORIZED", "TENANT_MISMATCH"],
                },
            },
            "rag.operators.schema": {
                "mutation": False,
                "payload_schema": _payload_schema(
                    properties={
                        "tenant_slug": {"type": "string"},
                        "operator_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    required=["operator_ids"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Resolve schemas/contracts for multiple RAG operators in one call, including config schema and exact visual-node/create contract shape.",
                    "required_fields": ["operator_ids"],
                    "example_payload": {"tenant_slug": "acme", "operator_ids": ["query_input", "knowledge_store_lookup"]},
                    "failure_codes": ["UNAUTHORIZED", "TENANT_MISMATCH", "VALIDATION_ERROR"],
                },
            },
            "rag.create_pipeline_shell": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "tenant_slug": {"type": "string"},
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
                        "tenant_slug": "acme",
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
                        "tenant_slug": {"type": "string"},
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "pipeline_type": {"type": "string", "enum": ["ingestion", "retrieval"]},
                        "nodes": {"type": "array", "items": {"type": "object"}},
                        "edges": {"type": "array", "items": {"type": "object"}},
                        # Backward compatibility shim: wrappers map graph_definition -> nodes/edges.
                        "graph_definition": {"type": "object"},
                    },
                    required=["name"],
                    additional_properties=True,
                ),
                "contract": {
                    "summary": "Create a draft visual RAG pipeline.",
                    "required_fields": ["name", "nodes|graph_definition"],
                    "example_payload": {
                        "tenant_slug": "acme",
                        "name": "FAQ Pipeline",
                        "pipeline_type": "retrieval",
                        "nodes": [
                            {"id": "n1", "category": "input", "operator": "query_input", "position": {"x": 80, "y": 120}, "config": {}},
                            {"id": "n2", "category": "retrieval", "operator": "knowledge_store_lookup", "position": {"x": 360, "y": 120}, "config": {"knowledge_store_id": "ks-123"}},
                        ],
                        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
                    },
                    "failure_codes": ["VALIDATION_ERROR", "SENSITIVE_ACTION_APPROVAL_REQUIRED"],
                    "notes": [
                        "Before constructing unfamiliar RAG operators, call rag.operators.catalog then rag.operators.schema.",
                        "For new pipelines, every node must include category, operator, and position; edges must include stable ids.",
                    ],
                },
            },
            "rag.update_visual_pipeline": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "pipeline_id": {"type": "string"},
                        "id": {"type": "string"},
                        "tenant_slug": {"type": "string"},
                        "patch": {"type": "object"},
                    },
                    additional_properties=True,
                ),
                "contract": {
                    "summary": "Patch an existing visual RAG pipeline.",
                    "required_fields": ["pipeline_id|id", "patch"],
                    "example_payload": {
                        "pipeline_id": "pipe-123",
                        "tenant_slug": "acme",
                        "patch": {"description": "patched"},
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
                        "tenant_slug": {"type": "string"},
                    },
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Get the persisted graph for a visual pipeline.",
                    "required_fields": ["pipeline_id|id"],
                    "example_payload": {"pipeline_id": "pipe-123", "tenant_slug": "acme"},
                    "failure_codes": ["NOT_FOUND"],
                },
            },
            "rag.graph.validate_patch": {
                "mutation": False,
                "payload_schema": _payload_schema(
                    properties={
                        "pipeline_id": {"type": "string"},
                        "id": {"type": "string"},
                        "tenant_slug": {"type": "string"},
                        "operations": {"type": "array", "items": {"type": "object"}},
                    },
                    required=["operations"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Validate schema-aware graph mutation operations for a visual pipeline without persisting.",
                    "required_fields": ["pipeline_id|id", "operations"],
                    "example_payload": {
                        "pipeline_id": "pipe-123",
                        "tenant_slug": "acme",
                        "operations": [{"op": "set_node_config_value", "node_id": "lookup_1", "path": "top_k", "value": 8}],
                    },
                    "failure_codes": ["NOT_FOUND", "VALIDATION_ERROR"],
                },
            },
            "rag.graph.apply_patch": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "pipeline_id": {"type": "string"},
                        "id": {"type": "string"},
                        "tenant_slug": {"type": "string"},
                        "operations": {"type": "array", "items": {"type": "object"}},
                    },
                    required=["operations"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Apply validated graph mutation operations to a visual pipeline and return persisted validation state.",
                    "required_fields": ["pipeline_id|id", "operations"],
                    "example_payload": {
                        "pipeline_id": "pipe-123",
                        "tenant_slug": "acme",
                        "operations": [{"op": "rewire_edge", "edge_id": "e1", "target": "answer_1"}],
                    },
                    "failure_codes": ["NOT_FOUND", "VALIDATION_ERROR"],
                },
            },
            "rag.graph.attach_knowledge_store_to_node": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "pipeline_id": {"type": "string"},
                        "id": {"type": "string"},
                        "tenant_slug": {"type": "string"},
                        "node_id": {"type": "string"},
                        "knowledge_store_id": {"type": "string"},
                    },
                    required=["node_id", "knowledge_store_id"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Attach a knowledge store to an existing pipeline node without rebuilding the whole graph.",
                    "required_fields": ["pipeline_id|id", "node_id", "knowledge_store_id"],
                    "example_payload": {"pipeline_id": "pipe-123", "node_id": "lookup_1", "knowledge_store_id": "ks-123", "tenant_slug": "acme"},
                    "failure_codes": ["NOT_FOUND", "VALIDATION_ERROR"],
                },
            },
            "rag.graph.set_pipeline_node_config": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "pipeline_id": {"type": "string"},
                        "id": {"type": "string"},
                        "tenant_slug": {"type": "string"},
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
                    "example_payload": {"pipeline_id": "pipe-123", "node_id": "lookup_1", "path": "top_k", "value": 8, "tenant_slug": "acme"},
                    "failure_codes": ["NOT_FOUND", "VALIDATION_ERROR"],
                },
            },
            "rag.compile_visual_pipeline": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "pipeline_id": {"type": "string"},
                        "id": {"type": "string"},
                        "tenant_slug": {"type": "string"},
                    },
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Compile a visual pipeline and return validation results.",
                    "required_fields": ["pipeline_id|id"],
                    "example_payload": {"pipeline_id": "pipe-123", "tenant_slug": "acme"},
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
                        "tenant_slug": {"type": "string"},
                    },
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Get compiled executable pipeline metadata.",
                    "required_fields": ["exec_id|executable_pipeline_id|id"],
                    "example_payload": {"exec_id": "exec-123", "tenant_slug": "acme"},
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
                        "tenant_slug": {"type": "string"},
                    },
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Get executable pipeline input schema.",
                    "required_fields": ["exec_id|executable_pipeline_id|id"],
                    "example_payload": {"exec_id": "exec-123", "tenant_slug": "acme"},
                    "failure_codes": ["NOT_FOUND"],
                },
            },
            "rag.create_job": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "executable_pipeline_id": {"type": "string"},
                        "tenant_slug": {"type": "string"},
                        "input_params": {"type": "object"},
                    },
                    required=["executable_pipeline_id", "tenant_slug"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Run a pipeline job against an executable pipeline.",
                    "required_fields": ["executable_pipeline_id", "tenant_slug"],
                    "example_payload": {
                        "executable_pipeline_id": "exec-123",
                        "tenant_slug": "acme",
                        "input_params": {"query": "hello"},
                    },
                    "failure_codes": ["VALIDATION_ERROR", "TENANT_MISMATCH"],
                },
            },
            "rag.get_job": {
                "mutation": False,
                "payload_schema": _payload_schema(
                    properties={
                        "job_id": {"type": "string"},
                        "id": {"type": "string"},
                        "tenant_slug": {"type": "string"},
                    },
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Get pipeline job execution state.",
                    "required_fields": ["job_id|id"],
                    "example_payload": {"job_id": "job-123", "tenant_slug": "acme"},
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
                "payload_schema": _payload_schema(
                    properties={
                        "status": {"type": "string"},
                        "skip": {"type": "integer", "minimum": 0},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                        "compact": {"type": "boolean"},
                    }
                ),
                "contract": {
                    "summary": "List agents.",
                    "required_fields": [],
                    "example_payload": {"status": "draft", "limit": 50, "skip": 0},
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
                        "slug": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    required=["name", "slug"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Create a draft agent shell with the minimal valid graph skeleton.",
                    "required_fields": ["name", "slug"],
                    "example_payload": {
                        "name": "FAQ Agent",
                        "slug": "faq-agent",
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
                        "slug": {"type": "string"},
                        "graph_definition": {"type": "object"},
                        "description": {"type": "string"},
                    },
                    required=["name", "slug", "graph_definition"],
                    additional_properties=True,
                ),
                "contract": {
                    "summary": "Create a draft agent with a valid non-empty graph_definition.",
                    "required_fields": ["name", "slug", "graph_definition"],
                    "example_payload": {
                        "name": "FAQ Agent",
                        "slug": "faq-agent",
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
                "payload_schema": _payload_schema(
                    properties={
                        "agent_id": {"type": "string"},
                        "id": {"type": "string"},
                        "patch": {"type": "object"},
                    },
                    additional_properties=True,
                ),
                "contract": {
                    "summary": "Patch an existing agent.",
                    "required_fields": ["agent_id|id", "patch"],
                    "example_payload": {"agent_id": "agent-123", "patch": {"description": "updated"}},
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
                    "summary": "Validate schema-aware graph mutation operations for an agent without persisting.",
                    "required_fields": ["agent_id|id", "operations"],
                    "example_payload": {
                        "agent_id": "agent-123",
                        "operations": [{"op": "append_unique_node_config_list_item", "node_id": "assistant", "path": "tools", "value": "tool-123"}],
                    },
                    "failure_codes": ["NOT_FOUND", "VALIDATION_ERROR"],
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
                    "summary": "Apply validated graph mutation operations to an agent and return persisted validation state.",
                    "required_fields": ["agent_id|id", "operations"],
                    "example_payload": {
                        "agent_id": "agent-123",
                        "operations": [{"op": "set_node_config_value", "node_id": "assistant", "path": "instructions", "value": "Use web search when needed."}],
                    },
                    "failure_codes": ["NOT_FOUND", "VALIDATION_ERROR"],
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
                    "failure_codes": ["NOT_FOUND", "VALIDATION_ERROR"],
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
                    "failure_codes": ["NOT_FOUND", "VALIDATION_ERROR"],
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
                    "failure_codes": ["NOT_FOUND", "VALIDATION_ERROR"],
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
                    "failure_codes": ["NOT_FOUND", "VALIDATION_ERROR"],
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
                "payload_schema": _payload_schema(
                    properties={
                        "agent_id": {"type": "string"},
                        "id": {"type": "string"},
                        "validation": {"type": "object"},
                    },
                    additional_properties=True,
                ),
                "contract": {
                    "summary": "Validate an agent definition.",
                    "required_fields": ["agent_id|id"],
                    "example_payload": {"agent_id": "agent-123", "validation": {"strict": True}},
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
                    "summary": "Validate persisted agent graph by id with compiler and runtime reference checks.",
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
                        "agent_slug": {"type": "string"},
                        "slug": {"type": "string"},
                        "input": {"type": "string"},
                        "messages": {"type": "array"},
                        "context": {"type": "object"},
                    },
                    additional_properties=True,
                ),
                "contract": {
                    "summary": "Execute an agent run.",
                    "required_fields": ["agent_id|id|agent_slug|slug"],
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
            "tools.list": {"mutation": False, "payload_schema": _payload_schema(properties={}), "contract": {"summary": "List tools.", "required_fields": [], "example_payload": {}, "failure_codes": []}},
            "tools.get": {
                "mutation": False,
                "payload_schema": _payload_schema(properties={"tool_id": {"type": "string"}, "id": {"type": "string"}}),
                "contract": {"summary": "Get tool.", "required_fields": ["tool_id|id"], "example_payload": {"tool_id": "tool-123"}, "failure_codes": ["NOT_FOUND"]},
            },
            "tools.create_or_update": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={"tool_id": {"type": "string"}, "id": {"type": "string"}, "name": {"type": "string"}, "slug": {"type": "string"}, "schema": {"type": "object"}, "config_schema": {"type": "object"}},
                    additional_properties=True,
                ),
                "contract": {"summary": "Create or update tool draft.", "required_fields": ["name|tool_id"], "example_payload": {"name": "My Tool", "slug": "my-tool"}, "failure_codes": ["VALIDATION_ERROR"]},
            },
            "tools.publish": {
                "mutation": True,
                "payload_schema": _payload_schema(properties={"tool_id": {"type": "string"}, "id": {"type": "string"}}),
                "contract": {"summary": "Publish tool version (explicit publish intent required).", "required_fields": ["tool_id|id"], "example_payload": {"tool_id": "tool-123"}, "failure_codes": ["DRAFT_FIRST_POLICY_DENIED", "SENSITIVE_ACTION_APPROVAL_REQUIRED"]},
            },
            "artifacts.list": {"mutation": False, "payload_schema": _payload_schema(properties={}), "contract": {"summary": "List artifacts.", "required_fields": [], "example_payload": {}, "failure_codes": []}},
            "artifacts.get": {
                "mutation": False,
                "payload_schema": _payload_schema(properties={"artifact_id": {"type": "string"}, "id": {"type": "string"}}),
                "contract": {"summary": "Get artifact.", "required_fields": ["artifact_id|id"], "example_payload": {"artifact_id": "artifact-123"}, "failure_codes": ["NOT_FOUND"]},
            },
            "artifacts.create": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={
                        "slug": {"type": "string"},
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
                    required=["slug", "display_name", "kind", "runtime"],
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "Create a canonical draft artifact.",
                    "required_fields": ["slug", "display_name", "kind", "runtime"],
                    "example_payload": {
                        "slug": "normalize-docs",
                        "display_name": "Normalize Docs",
                        "description": "Tool implementation artifact.",
                        "kind": "tool_impl",
                        "runtime": {
                            "source_files": [{"path": "main.py", "content": "async def execute(inputs, config, context):\n    return {\"ok\": True}"}],
                            "entry_module_path": "main.py",
                            "python_dependencies": [],
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
                                "source_files": [{"path": "main.py", "content": "async def execute(inputs, config, context):\n    return inputs"}],
                                "entry_module_path": "main.py",
                                "python_dependencies": [],
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
                "payload_schema": _payload_schema(
                    properties={
                        "capability_type": {"type": "string"},
                        "is_active": {"type": "boolean"},
                        "skip": {"type": "integer", "minimum": 0},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                    },
                    additional_properties=False,
                ),
                "contract": {
                    "summary": "List models.",
                    "required_fields": [],
                    "example_payload": {"capability_type": "chat", "is_active": True, "limit": 50},
                    "failure_codes": [],
                },
            },
            "models.create_or_update": {
                "mutation": True,
                "payload_schema": _payload_schema(properties={"model_id": {"type": "string"}, "id": {"type": "string"}, "name": {"type": "string"}, "slug": {"type": "string"}}, additional_properties=True),
                "contract": {"summary": "Create or update model.", "required_fields": ["name|model_id"], "example_payload": {"name": "Model A", "slug": "model-a"}, "failure_codes": ["VALIDATION_ERROR"]},
            },
            "credentials.list": {"mutation": False, "payload_schema": _payload_schema(properties={}), "contract": {"summary": "List credentials.", "required_fields": [], "example_payload": {}, "failure_codes": []}},
            "credentials.create_or_update": {
                "mutation": True,
                "payload_schema": _payload_schema(properties={"credential_id": {"type": "string"}, "id": {"type": "string"}, "name": {"type": "string"}, "category": {"type": "string"}}, additional_properties=True),
                "contract": {"summary": "Create or update credential.", "required_fields": ["name|credential_id"], "example_payload": {"name": "OpenAI", "category": "api"}, "failure_codes": ["VALIDATION_ERROR"]},
            },
            "knowledge_stores.list": {
                "mutation": False,
                "payload_schema": _payload_schema(properties={"tenant_slug": {"type": "string"}}, additional_properties=False),
                "contract": {"summary": "List knowledge stores.", "required_fields": ["tenant_slug"], "example_payload": {"tenant_slug": "acme"}, "failure_codes": []},
            },
            "knowledge_stores.create_or_update": {
                "mutation": True,
                "payload_schema": _payload_schema(properties={"store_id": {"type": "string"}, "id": {"type": "string"}, "tenant_slug": {"type": "string"}, "name": {"type": "string"}}, additional_properties=True),
                "contract": {"summary": "Create or update knowledge store.", "required_fields": ["tenant_slug", "name|store_id"], "example_payload": {"tenant_slug": "acme", "name": "kb"}, "failure_codes": ["VALIDATION_ERROR"]},
            },
        },
    },
    "platform-governance": {
        "name": "Platform Governance",
        "description": "Domain tool for auth delegation, workload security, and orchestration primitives.",
        "actions": {
            "auth.create_delegation_grant": {"mutation": True, "payload_schema": _payload_schema(properties={"principal_id": {"type": "string"}, "requested_scopes": {"type": "array"}}, additional_properties=True), "contract": {"summary": "Create delegation grant.", "required_fields": ["principal_id", "requested_scopes"], "example_payload": {"principal_id": "p1", "requested_scopes": ["agents.execute"]}, "failure_codes": ["VALIDATION_ERROR"]}},
            "auth.mint_workload_token": {"mutation": True, "payload_schema": _payload_schema(properties={"principal_id": {"type": "string"}, "scope_subset": {"type": "array"}}, additional_properties=True), "contract": {"summary": "Mint workload token.", "required_fields": ["principal_id"], "example_payload": {"principal_id": "p1", "scope_subset": ["agents.execute"]}, "failure_codes": ["SENSITIVE_ACTION_APPROVAL_REQUIRED"]}},
            "workload_security.list_pending": {"mutation": False, "payload_schema": _payload_schema(properties={}), "contract": {"summary": "List pending workload policies.", "required_fields": [], "example_payload": {}, "failure_codes": []}},
            "workload_security.approve_policy": {"mutation": True, "payload_schema": _payload_schema(properties={"principal_id": {"type": "string"}, "approved_scopes": {"type": "array"}}, required=["principal_id"], additional_properties=True), "contract": {"summary": "Approve workload policy.", "required_fields": ["principal_id"], "example_payload": {"principal_id": "p1", "approved_scopes": ["agents.execute"]}, "failure_codes": ["NOT_FOUND"]}},
            "workload_security.reject_policy": {"mutation": True, "payload_schema": _payload_schema(properties={"principal_id": {"type": "string"}}, required=["principal_id"], additional_properties=True), "contract": {"summary": "Reject workload policy.", "required_fields": ["principal_id"], "example_payload": {"principal_id": "p1"}, "failure_codes": ["NOT_FOUND"]}},
            "workload_security.list_approvals": {"mutation": False, "payload_schema": _payload_schema(properties={"subject_type": {"type": "string"}, "subject_id": {"type": "string"}, "action_scope": {"type": "string"}}, additional_properties=True), "contract": {"summary": "List action approvals.", "required_fields": [], "example_payload": {"subject_type": "tool", "subject_id": "tool-1"}, "failure_codes": []}},
            "workload_security.decide_approval": {"mutation": True, "payload_schema": _payload_schema(properties={"approval_id": {"type": "string"}, "decision": {"type": "string", "enum": ["approved", "rejected"]}, "notes": {"type": "string"}}, required=["approval_id", "decision"], additional_properties=True), "contract": {"summary": "Decide approval request.", "required_fields": ["approval_id", "decision"], "example_payload": {"approval_id": "ap-1", "decision": "approved"}, "failure_codes": ["NOT_FOUND"]}},
            "orchestration.spawn_run": {"mutation": True, "payload_schema": _payload_schema(properties={"caller_run_id": {"type": "string"}, "target_agent_slug": {"type": "string"}, "scope_subset": {"type": "array"}, "mapped_input_payload": {"type": "object"}}, additional_properties=True), "contract": {"summary": "Spawn child run.", "required_fields": ["caller_run_id", "target_agent_slug"], "example_payload": {"caller_run_id": "run-1", "target_agent_slug": "worker"}, "failure_codes": ["VALIDATION_ERROR"]}},
            "orchestration.spawn_group": {"mutation": True, "payload_schema": _payload_schema(properties={"caller_run_id": {"type": "string"}, "targets": {"type": "array"}, "scope_subset": {"type": "array"}}, required=["caller_run_id", "targets"], additional_properties=True), "contract": {"summary": "Spawn a parallel group.", "required_fields": ["caller_run_id", "targets"], "example_payload": {"caller_run_id": "run-1", "targets": [{"target_agent_slug": "worker"}]}, "failure_codes": ["VALIDATION_ERROR"]}},
            "orchestration.join": {"mutation": False, "payload_schema": _payload_schema(properties={"caller_run_id": {"type": "string"}, "orchestration_group_id": {"type": "string"}}, additional_properties=True), "contract": {"summary": "Join orchestration group.", "required_fields": ["caller_run_id", "orchestration_group_id"], "example_payload": {"caller_run_id": "run-1", "orchestration_group_id": "grp-1"}, "failure_codes": ["NOT_FOUND"]}},
            "orchestration.cancel_subtree": {"mutation": True, "payload_schema": _payload_schema(properties={"caller_run_id": {"type": "string"}, "run_id": {"type": "string"}}, required=["caller_run_id", "run_id"], additional_properties=True), "contract": {"summary": "Cancel subtree run.", "required_fields": ["caller_run_id", "run_id"], "example_payload": {"caller_run_id": "run-1", "run_id": "run-2"}, "failure_codes": ["NOT_FOUND"]}},
            "orchestration.evaluate_and_replan": {"mutation": True, "payload_schema": _payload_schema(properties={"caller_run_id": {"type": "string"}, "run_id": {"type": "string"}}, required=["caller_run_id", "run_id"], additional_properties=True), "contract": {"summary": "Evaluate and replan run.", "required_fields": ["caller_run_id", "run_id"], "example_payload": {"caller_run_id": "run-1", "run_id": "run-2"}, "failure_codes": ["VALIDATION_ERROR"]}},
            "orchestration.query_tree": {"mutation": False, "payload_schema": _payload_schema(properties={"run_id": {"type": "string"}}, required=["run_id"], additional_properties=False), "contract": {"summary": "Query run tree.", "required_fields": ["run_id"], "example_payload": {"run_id": "run-1"}, "failure_codes": ["NOT_FOUND"]}},
        },
    },
}


def build_platform_domain_tool_schema(tool_slug: str, tool_spec: Dict[str, Any]) -> Dict[str, Any]:
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
                "request_metadata": {
                    "type": "object",
                    "properties": {
                        "trace_id": {"type": "string"},
                        "request_id": {"type": "string"},
                        "reason": {"type": "string"},
                        "source": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
                "tool_slug": {"const": tool_slug},
                "tenant_id": {"type": "string"},
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
            "request_metadata": {"type": "object"},
            "tool_slug": {"type": "string", "const": tool_slug},
            "tenant_id": {"type": "string"},
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
                    "tool_slug": {"type": ["string", "null"]},
                },
                "additionalProperties": True,
            },
        },
        "additionalProperties": True,
    }
    return {"input": input_schema, "output": output_schema}


def build_architect_graph_definition(model_id: str, tool_ids: list[str] | None = None) -> dict:
    instructions = (
        "You are Platform Architect v1.2. "
        "You must plan and execute directly through visible domain tools only: platform-rag, platform-agents, "
        "platform-assets, platform-governance, architect-worker-binding-prepare, architect-worker-binding-get-state, architect-worker-binding-persist-artifact, "
        "architect-worker-spawn, architect-worker-spawn-group, architect-worker-get-run, architect-worker-await, "
        "architect-worker-respond, architect-worker-join, architect-worker-cancel. "
        "Never call architect.run or any meta action. "
        "Use only exact canonical action IDs from tool schemas (for example: agents.create_shell, rag.create_pipeline_shell, "
        "artifacts.create, artifacts.update, artifacts.create_test_run). Never invent aliases like create_agent/register_asset. "
        "Every Platform SDK call must use canonical top-level action and payload fields. "
        "Never wrap a tool call inside query, text, value, or markdown. "
        "Workflow policy: extract intent and constraints, build a step plan, prefer direct deterministic domain mutations "
        "for local work, use dedicated architect-worker tools for async or long-running delegated work, validate after "
        "each mutation, and repair/replan with a hard max of 2 repair loops. "
        "Prefer semantic graph helpers first (agents.graph.add_tool_to_agent_node, agents.graph.set_agent_model, "
        "agents.graph.set_agent_instructions, rag.graph.attach_knowledge_store_to_node, "
        "rag.graph.set_pipeline_node_config). Use agents.graph.apply_patch or rag.graph.apply_patch only when a helper "
        "does not cover the requested mutation. "
        "For first-time agent creation, prefer agents.create_shell over agents.create unless you intentionally need to supply a full graph_definition. "
        "For first-time RAG pipeline creation, prefer rag.create_pipeline_shell over rag.create_visual_pipeline unless you intentionally need to supply a full nodes/edges graph. "
        "For rag.create_visual_pipeline, pass nodes/edges at payload top-level (graph_definition is backward-compatible only). "
        "For agent graph discovery use agents.nodes.catalog and agents.nodes.schema only. "
        "For RAG pipeline operator discovery use rag.operators.catalog and rag.operators.schema only. "
        "Never use agents.nodes.* to discover RAG operators and never invent unsupported actions like rag.nodes.catalog. "
        "Never create empty graphs: agents and pipelines must include a minimal working node/edge skeleton. "
        "For agents.create specifically, graph_definition must include exactly one start node, at least one end node, "
        "and at least one control edge from start to a downstream node. "
        "Before introducing unfamiliar agent node types, call agents.nodes.catalog first and agents.nodes.schema for all node_types[] in one call. "
        "Before introducing unfamiliar RAG operators, call rag.operators.catalog first and rag.operators.schema for all operator_ids[] in one call. "
        "After each draft graph mutation, call agents.nodes.validate on the target agent id and repair based on "
        "returned structured errors/warnings. "
        "Do not call raw orchestration.* actions through platform-governance for worker delegation; use the dedicated architect-worker tools instead. "
        "For artifact metadata/runtime/contract lifecycle work, use platform-assets canonical artifact actions directly. "
        "For code-heavy or multi-file artifact authoring, prepare an artifact_shared_draft binding with architect-worker-binding-prepare using only canonical top-level fields for the selected mode. "
        "The normal new-binding flow is prepare_mode=create_new_draft with title_prompt plus draft_seed.kind. "
        "Do not construct a full draft_snapshot for normal artifact creation; full draft_snapshot is reserved for the advanced seed_snapshot mode only. "
        "spawn the artifact worker asynchronously with architect-worker-spawn or architect-worker-spawn-group using objective as a top-level field, then wait with architect-worker-await. "
        "Use architect-worker-get-run only for one-off inspection/debugging, not as a tight polling loop. "
        "If architect-worker-await returns waiting_for_input, answer the child with architect-worker-respond or explicitly surface the blocker to the user. "
        "If architect-worker-await returns completed, failed, or cancelled, then decide the next step from worker state. "
        "When completion succeeded for a binding-backed artifact task, call architect-worker-binding-persist-artifact as the normal persistence step. "
        "Use architect-worker-binding-get-state only when inspection, export, or debugging is specifically needed. "
        "Do not invent nested fields like task.instructions, task.title, task.worker_agent, or generic binding_payload wrappers. "
        "Do not invent non-canonical binding fields such as create, files, entrypoint, or text. "
        "Worker runs may mutate only their binding-backed working state; they never save or publish canonical artifacts by themselves. "
        "If you used an artifact worker binding for a create/update task, you must not end the run after spawn/join alone: before final completion "
        "you must either persist the canonical artifact through architect-worker-binding-persist-artifact, or return an explicit blocker explaining why "
        "persistence could not be completed. "
        "Do not treat successful worker completion as task completion by itself. "
        "Never burn tool iterations on repeated immediate architect-worker-get-run calls; architect-worker-await is the normal waiting primitive. "
        "Do not repeatedly respawn a worker on the same writable artifact binding unless the prior run is terminal and you have a concrete reason to retry. "
        "If the worker is waiting for input, the next required step is architect-worker-respond or an explicit user-facing blocker. "
        "If the worker finished and no blocker exists, the next required step is architect-worker-binding-persist-artifact. "
        "After delegated artifact changes, persist with architect-worker-binding-persist-artifact, optionally run artifacts.create_test_run, "
        "and only then publish if explicit publish intent is present. "
        "For RAG shell creation, use rag.create_pipeline_shell first, then refine the pipeline through graph helpers or canonical update actions. "
        "If the same mutation action fails twice with the same normalized error, stop mutating, summarize the blocker, "
        "and report the target resource, attempted action, normalized failure code, last validation details, whether any "
        "mutation succeeded, and the recommended next repair action. "
        "If a Platform SDK call fails due to non-canonical input or unsupported action, do not keep retrying the same malformed branch. "
        "If a node you are creating/updating requires model_id (for example agent/llm/classify) and model_id is "
        "missing or rejected, call platform-assets with action models.list first, select a valid active chat-capable "
        "model id from the response, and retry the mutation. Do not ask the user for model_id unless models.list "
        "returns no usable models. "
        "Draft-first is mandatory: do not call publish/promote actions unless objective_flags.allow_publish=true "
        "in user-provided input. "
        "Runtime tenant context is authoritative for platform mutations. Never ask the user for tenant_id, "
        "never rely on a user-supplied tenant override, and operate only inside the current runtime tenant. "
        "Idempotency keys and request metadata should be autogenerated from runtime context when absent; "
        "do not block on asking the user for them unless a caller explicitly requires custom values. "
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
