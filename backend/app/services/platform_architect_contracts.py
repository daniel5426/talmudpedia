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
            "artifacts.create_or_update_draft": {
                "mutation": True,
                "payload_schema": _payload_schema(
                    properties={"artifact_id": {"type": "string"}, "id": {"type": "string"}, "namespace": {"type": "string"}, "version": {"type": "string"}, "content": {"type": ["string", "object", "array"]}},
                    additional_properties=True,
                ),
                "contract": {"summary": "Create or update draft artifact.", "required_fields": ["namespace", "content|files"], "example_payload": {"namespace": "custom", "content": "print('hello')"}, "failure_codes": ["VALIDATION_ERROR"]},
            },
            "artifacts.promote": {
                "mutation": True,
                "payload_schema": _payload_schema(properties={"artifact_id": {"type": "string"}, "id": {"type": "string"}, "namespace": {"type": "string"}}),
                "contract": {"summary": "Promote artifact draft (explicit publish intent required).", "required_fields": ["artifact_id|id"], "example_payload": {"artifact_id": "artifact-123", "namespace": "custom"}, "failure_codes": ["DRAFT_FIRST_POLICY_DENIED", "SENSITIVE_ACTION_APPROVAL_REQUIRED"]},
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
        if action_spec.get("mutation"):
            variant["required"] = ["action", "payload", "idempotency_key", "request_metadata", "tenant_id"]
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
        "You are Platform Architect v1.1. "
        "You must plan and execute directly through visible domain tools only: platform-rag, platform-agents, "
        "platform-assets, platform-governance. "
        "Never call architect.run or any meta action. "
        "Use only exact canonical action IDs from tool schemas (for example: agents.create, rag.create_visual_pipeline, "
        "artifacts.create_or_update_draft). Never invent aliases like create_agent/register_asset. "
        "Workflow policy: extract intent and constraints, build a step plan, execute one tool call at a time, "
        "validate after each mutation, and repair/replan with a hard max of 2 repair loops. "
        "For rag.create_visual_pipeline, pass nodes/edges at payload top-level (graph_definition is backward-compatible only). "
        "Never create empty graphs: agents and pipelines must include a minimal working node/edge skeleton. "
        "For agents.create specifically, graph_definition must include exactly one start node, at least one end node, "
        "and at least one control edge from start to a downstream node. "
        "Before introducing unfamiliar node types, call agents.nodes.catalog first. "
        "For any node set you plan to add/update, call agents.nodes.schema once with all node types in node_types[]. "
        "After each draft graph mutation, call agents.nodes.validate on the target agent id and repair based on "
        "returned structured errors/warnings. "
        "If a node you are creating/updating requires model_id (for example agent/llm/classify) and model_id is "
        "missing or rejected, call platform-assets with action models.list first, select a valid active chat-capable "
        "model id from the response, and retry the mutation. Do not ask the user for model_id unless models.list "
        "returns no usable models. "
        "Draft-first is mandatory: do not call publish/promote actions unless objective_flags.allow_publish=true "
        "in user-provided input. "
        "Always include tenant_id, idempotency_key, and request_metadata on mutating calls. "
        "Return only final machine-readable JSON report."
    )

    output_schema = {
        "type": "object",
        "properties": {
            "run_id": {"type": "string"},
            "tenant_id": {"type": ["string", "null"]},
            "status": {"type": "string"},
            "objective": {"type": ["string", "null"]},
            "summary": {"type": "string"},
            "plan": {
                "type": "object",
                "properties": {
                    "total_steps": {"type": "integer"},
                    "completed_steps": {"type": "integer"},
                    "failed_steps": {"type": "integer"},
                    "repaired_steps": {"type": "integer"},
                },
                "additionalProperties": True,
            },
            "resources": {
                "type": "object",
                "properties": {
                    "agents": {"type": "array"},
                    "rag_pipelines": {"type": "array"},
                    "artifacts": {"type": "array"},
                    "tools": {"type": "array"},
                },
                "additionalProperties": True,
            },
            "validation": {
                "type": "object",
                "properties": {
                    "pipeline_validation": {"type": "array"},
                    "agent_validation": {"type": "array"},
                    "tests": {"type": "array"},
                },
                "additionalProperties": True,
            },
            "observability": {
                "type": "object",
                "properties": {
                    "trace_id": {"type": ["string", "null"]},
                    "tool_calls": {"type": "array"},
                    "decision_events": {"type": "array"},
                },
                "additionalProperties": True,
            },
            "failures": {"type": "array", "items": {"type": "object"}},
            "next_actions": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "run_id",
            "tenant_id",
            "status",
            "objective",
            "summary",
            "plan",
            "resources",
            "validation",
            "observability",
            "failures",
            "next_actions",
        ],
        "additionalProperties": True,
    }

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
                    "reasoning_effort": "medium",
                    "tools": list(tool_ids or []),
                    "output_format": "json",
                    "output_schema": output_schema,
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
