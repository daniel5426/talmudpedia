"""Graph Schema - Pydantic models for agent graph validation."""
import hashlib
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict, model_validator

from app.agent.graph.ir import GRAPH_SPEC_V4

OPAQUE_BRANCH_ID_PREFIX = "branch_"


def _is_opaque_branch_id(value: str) -> bool:
    return value.startswith(OPAQUE_BRANCH_ID_PREFIX) and len(value) > len(OPAQUE_BRANCH_ID_PREFIX)


def _make_opaque_branch_id(seed: str, used_ids: set[str]) -> str:
    attempt = 0
    while True:
        value = seed if attempt == 0 else f"{seed}:{attempt}"
        candidate = f"{OPAQUE_BRANCH_ID_PREFIX}{hashlib.sha1(value.encode('utf-8')).hexdigest()[:8]}"
        if candidate not in used_ids:
            used_ids.add(candidate)
            return candidate
        attempt += 1


def _normalize_named_branch_items(raw: Any, fallback_prefix: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        branch = dict(item)
        explicit_id = str(branch.get("id") or "").strip()
        name = str(branch.get("name") or "").strip()
        if _is_opaque_branch_id(explicit_id) and explicit_id not in used_ids:
            used_ids.add(explicit_id)
            branch["id"] = explicit_id
        else:
            branch["id"] = _make_opaque_branch_id(f"{fallback_prefix}:{name}:{idx}", used_ids)
        branch["name"] = name
        normalized.append(branch)
    return normalized


class NodeType(str, Enum):
    """Types of nodes in an agent graph."""
    INPUT = "input"
    START = "start" # Alias for INPUT
    OUTPUT = "output"
    END = "end" # Alias for OUTPUT
    TOOL_CALL = "tool_call"
    LOOP = "loop"
    PARALLEL = "parallel"
    TRANSFORM = "transform"
    SPEECH_TO_TEXT = "speech_to_text"
    RAG_PIPELINE = "rag_pipeline"
    SPAWN_RUN = "spawn_run"
    SPAWN_GROUP = "spawn_group"
    JOIN = "join"
    ROUTER = "router"
    JUDGE = "judge"
    REPLAN = "replan"
    CANCEL_SUBTREE = "cancel_subtree"


class EdgeType(str, Enum):
    """Types of edges in an agent graph."""
    CONTROL = "control"
    DATA = "data"


class AgentNodePosition(BaseModel):
    """Position of a node in the visual editor."""
    x: float
    y: float
    model_config = ConfigDict(extra="ignore")


class AgentNode(BaseModel):
    """A node in the agent graph."""
    id: str
    # Use string type to support dynamic artifact/tool nodes in addition to static enums.
    type: str
    position: AgentNodePosition
    label: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    data: Optional[dict[str, Any]] = None # React Flow data support
    
    # Field mapping for artifacts: maps input field names to expressions
    # Example: {"documents": "{{ upstream.ingest_node.output }}", "query": "{{ state.messages[-1].content }}"}
    input_mappings: Optional[dict[str, str]] = None
    
    model_config = ConfigDict(extra="ignore")

    @model_validator(mode='before')
    @classmethod
    def normalize_input_mappings(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Normalize inputMappings -> input_mappings
            if "input_mappings" not in data:
                if "inputMappings" in data:
                    data["input_mappings"] = data.get("inputMappings")
            nested_data = data.get("data") if isinstance(data.get("data"), dict) else {}
            if "config" not in data and isinstance(nested_data.get("config"), dict):
                data["config"] = nested_data.get("config")
            if "input_mappings" not in data and "inputMappings" in nested_data:
                data["input_mappings"] = nested_data.get("inputMappings")
            config = data.get("config")
            node_type = str(data.get("type") or nested_data.get("nodeType") or "")
            if isinstance(config, dict):
                normalized_config = dict(config)
                if node_type == "classify":
                    normalized_config["categories"] = _normalize_named_branch_items(normalized_config.get("categories"), "category")
                if node_type == "if_else":
                    normalized_config["conditions"] = _normalize_named_branch_items(normalized_config.get("conditions"), "condition")
                data["config"] = normalized_config
        return data


class AgentEdge(BaseModel):
    """An edge connecting nodes in the agent graph."""
    id: str
    source: str
    target: str
    type: EdgeType = EdgeType.CONTROL
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None
    label: Optional[str] = None
    condition: Optional[str] = None
    model_config = ConfigDict(extra="ignore")

    @model_validator(mode='before')
    @classmethod
    def normalize_handles(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "source_handle" not in data and "sourceHandle" in data:
                data["source_handle"] = data.get("sourceHandle")
            if "target_handle" not in data and "targetHandle" in data:
                data["target_handle"] = data.get("targetHandle")
        return data


class WorkflowInputDefinition(BaseModel):
    key: str
    type: str
    required: bool = False
    enabled: bool = True
    label: Optional[str] = None
    description: Optional[str] = None
    semantic_type: Optional[str] = None
    readonly: bool = True
    derived: bool = False

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict) and str(data.get("type") or "").strip().lower() == "array":
            data["type"] = "list"
        return data


class WorkflowContract(BaseModel):
    inputs: list[WorkflowInputDefinition] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class StateVariableDefinition(BaseModel):
    key: str
    type: str
    description: Optional[str] = None
    schema: Optional[dict[str, Any]] = None
    default_value: Optional[Any] = None

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "key" not in data and "name" in data:
                data["key"] = data.get("name")
            if "default_value" not in data and "default" in data:
                data["default_value"] = data.get("default")
            if str(data.get("type") or "").strip().lower() == "array":
                data["type"] = "list"
        return data


class StateContract(BaseModel):
    variables: list[StateVariableDefinition] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


def _default_workflow_inputs() -> list[dict[str, Any]]:
    return [
        {
            "key": "text",
            "type": "string",
            "required": False,
            "enabled": True,
            "label": "Text",
            "description": "Primary text input for the workflow",
            "semantic_type": "text",
            "readonly": True,
            "derived": False,
        },
        {
            "key": "files",
            "type": "list",
            "required": False,
            "enabled": True,
            "label": "Files",
            "description": "General uploaded files for the workflow",
            "semantic_type": "files",
            "readonly": True,
            "derived": False,
        },
        {
            "key": "audio",
            "type": "list",
            "required": False,
            "enabled": True,
            "label": "Audio",
            "description": "Audio attachments for speech or sound workflows",
            "semantic_type": "audio",
            "readonly": True,
            "derived": False,
        },
        {
            "key": "images",
            "type": "list",
            "required": False,
            "enabled": True,
            "label": "Images",
            "description": "Image attachments for vision-aware workflows",
            "semantic_type": "images",
            "readonly": True,
            "derived": False,
        },
    ]


def _normalize_workflow_contract(raw: Any) -> dict[str, Any]:
    inputs = raw.get("inputs") if isinstance(raw, dict) and isinstance(raw.get("inputs"), list) else []
    normalized: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    defaults_by_key = {item["key"]: dict(item) for item in _default_workflow_inputs()}
    legacy_key_map = {
        "input_as_text": "text",
        "attachments": "files",
        "audio_attachments": "audio",
        "primary_audio_attachment": "audio",
    }
    for item in inputs:
        if not isinstance(item, dict):
            continue
        raw_key = str(item.get("key") or "").strip()
        key = legacy_key_map.get(raw_key, raw_key)
        if not key or key in seen_keys:
            continue
        payload = {
            **defaults_by_key.get(key, {"key": key}),
            "enabled": bool(item.get("enabled", True)),
            "required": bool(item.get("required", False)),
        }
        normalized.append(payload)
        seen_keys.add(key)
    for default_item in _default_workflow_inputs():
        key = str(default_item["key"])
        if key in seen_keys:
            continue
        normalized.append(dict(default_item))
        seen_keys.add(key)
    return {"inputs": normalized}


def _normalize_state_contract(raw: Any, *, legacy_state_variables: list[dict[str, Any]]) -> dict[str, Any]:
    variables = raw.get("variables") if isinstance(raw, dict) and isinstance(raw.get("variables"), list) else None
    if variables is None:
        variables = legacy_state_variables
    return {"variables": list(variables or [])}


class AgentGraph(BaseModel):
    """The complete graph definition of an agent."""
    spec_version: Optional[str] = None
    workflow_contract: WorkflowContract = Field(default_factory=WorkflowContract)
    state_contract: StateContract = Field(default_factory=StateContract)
    nodes: list[AgentNode] = Field(default_factory=list)
    edges: list[AgentEdge] = Field(default_factory=list)
    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def normalize_graph_contracts(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        legacy_state_variables: list[dict[str, Any]] = []
        normalized_nodes: list[Any] = []
        for raw_node in payload.get("nodes") or []:
            if not isinstance(raw_node, dict):
                normalized_nodes.append(raw_node)
                continue
            node = dict(raw_node)
            node_type = str(node.get("type") or "").strip().lower()
            if node_type in {NodeType.INPUT.value, NodeType.START.value}:
                config = dict(node.get("config") or {}) if isinstance(node.get("config"), dict) else {}
                raw_state_variables = config.get("state_variables") if isinstance(config.get("state_variables"), list) else []
                legacy_state_variables = [dict(item) for item in raw_state_variables if isinstance(item, dict)]
                config.pop("state_variables", None)
                node["config"] = config
            normalized_nodes.append(node)

        payload["nodes"] = normalized_nodes
        payload["workflow_contract"] = _normalize_workflow_contract(payload.get("workflow_contract"))
        payload["state_contract"] = _normalize_state_contract(
            payload.get("state_contract"),
            legacy_state_variables=legacy_state_variables,
        )
        payload["spec_version"] = GRAPH_SPEC_V4
        return payload
    
    def get_node(self, node_id: str) -> Optional[AgentNode]:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None
    
    def get_input_nodes(self) -> list[AgentNode]:
        return [n for n in self.nodes if str(n.type) in (NodeType.INPUT.value, NodeType.START.value)]
    
    def get_output_nodes(self) -> list[AgentNode]:
        return [n for n in self.nodes if str(n.type) in (NodeType.OUTPUT.value, NodeType.END.value)]
    
    def get_outgoing_edges(self, node_id: str) -> list[AgentEdge]:
        return [e for e in self.edges if e.source == node_id]
    
    def get_incoming_edges(self, node_id: str) -> list[AgentEdge]:
        return [e for e in self.edges if e.target == node_id]

class ValueRef(BaseModel):
    namespace: str
    key: str
    node_id: Optional[str] = None
    expected_type: Optional[str] = None
    label: Optional[str] = None

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            namespace = str(data.get("namespace") or "").strip().lower()
            if namespace in {"node_outputs", "node_output", "upstream"}:
                data["namespace"] = "node_output"
            elif namespace:
                data["namespace"] = namespace
            if str(data.get("expected_type") or "").strip().lower() == "array":
                data["expected_type"] = "list"
        return data


class EndOutputBinding(BaseModel):
    json_pointer: str
    value_ref: ValueRef

    model_config = ConfigDict(extra="ignore")


class EndOutputSchema(BaseModel):
    name: Optional[str] = None
    mode: str = "simple"
    schema: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class MemoryConfig(BaseModel):
    """Configuration for agent memory."""
    short_term_enabled: bool = True
    short_term_max_messages: int = 20
    long_term_enabled: bool = False
    long_term_index_id: Optional[str] = None
    model_config = ConfigDict(extra="forbid")


class ExecutionConstraints(BaseModel):
    """Constraints for agent execution."""
    timeout_seconds: int = 300
    max_tokens: Optional[int] = None
    max_iterations: int = 10
    allow_parallel_tools: bool = True
    model_config = ConfigDict(extra="forbid")
