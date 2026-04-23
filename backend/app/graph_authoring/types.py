from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


EditorKind = Literal["generic", "start", "end", "classify", "set_state"]


class BranchingHint(BaseModel):
    kind: str
    field: str | None = None
    id_key: str | None = None
    label_key: str | None = None
    static_handles: list[str] = Field(default_factory=list)
    default_handles: list[str] = Field(default_factory=list)


class GraphHints(BaseModel):
    editor: EditorKind = "generic"
    branching: BranchingHint | None = None


class NodeCatalogItem(BaseModel):
    type: str
    title: str
    description: str | None = None
    category: str
    input_type: str
    output_type: str
    required_config_fields: list[str] = Field(default_factory=list)
    icon: str | None = None
    color: str | None = None
    editor: EditorKind | None = None


class NodeAuthoringSpec(BaseModel):
    type: str
    title: str
    description: str | None = None
    category: str
    input_type: str
    output_type: str
    config_schema: dict[str, Any] = Field(default_factory=dict)
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    field_contracts: dict[str, Any] | None = None
    graph_hints: GraphHints | None = None
    node_template: dict[str, Any] | None = None
    normalization_defaults: dict[str, Any] = Field(default_factory=dict)
