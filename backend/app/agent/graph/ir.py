from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

GRAPH_SPEC_V1 = "1.0"
GRAPH_SPEC_V2 = "2.0"

ORCHESTRATION_V2_NODE_TYPES = {
    "spawn_run",
    "spawn_group",
    "join",
    "router",
    "judge",
    "replan",
    "cancel_subtree",
}


class GraphIRNode(BaseModel):
    id: str
    type: str
    config: Dict[str, Any] = Field(default_factory=dict)
    input_mappings: Optional[Dict[str, str]] = None
    data: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="ignore")


class GraphIREdge(BaseModel):
    id: str
    source: str
    target: str
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None
    type: Optional[str] = None
    label: Optional[str] = None
    condition: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class RoutingMap(BaseModel):
    handles: List[str] = Field(default_factory=list)
    edges: Dict[str, str] = Field(default_factory=dict)
    default_handle: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class GraphIR(BaseModel):
    schema_version: str = "1.0"
    nodes: List[GraphIRNode] = Field(default_factory=list)
    edges: List[GraphIREdge] = Field(default_factory=list)
    entry_point: Optional[str] = None
    exit_nodes: List[str] = Field(default_factory=list)
    routing_maps: Dict[str, RoutingMap] = Field(default_factory=dict)
    interrupt_before: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")
