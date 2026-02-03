"""
Agent Artifact Spec - Schema for agent-scoped artifacts.

This module defines the specification model for artifacts that appear
as nodes in the Agent Builder.
"""
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ArtifactScope(str, Enum):
    """Determines which Builder displays the artifact."""
    RAG_INGESTION = "rag_ingestion"
    RAG_RETRIEVAL = "rag_retrieval"
    AGENT = "agent"
    TOOL = "tool"


class AgentArtifactSpec(BaseModel):
    """
    Artifact specification for Agent nodes.
    
    This model represents an artifact that can be used as a node
    in the Agent Builder. It contains all metadata needed to:
    1. Display the artifact in the NodeCatalog
    2. Render the configuration panel
    3. Execute the artifact's handler
    """
    artifact_id: str = Field(..., description="Unique identifier for the artifact")
    display_name: str = Field(..., description="Human-readable name")
    version: str = Field(default="1.0.0", description="Semantic version")
    scope: ArtifactScope = Field(..., description="Which Builder shows this artifact")
    category: str = Field(..., description="Visual category: control, reasoning, action, logic, interaction, data")
    description: Optional[str] = Field(None, description="Brief description")
    
    # Data flow contract
    input_type: str = Field(default="any", description="Expected input type")
    output_type: str = Field(default="any", description="Output type produced")
    reads: List[str] = Field(default_factory=list, description="AgentStateField values this artifact reads")
    writes: List[str] = Field(default_factory=list, description="AgentStateField values this artifact writes")
    
    # Explicit input/output field definitions for field mapping
    inputs: List[Dict[str, Any]] = Field(default_factory=list, description="List of expected input fields with name, type, required, default")
    outputs: List[Dict[str, Any]] = Field(default_factory=list, description="List of output fields with name, type, description")
    
    # Configuration
    config_schema: Dict[str, Any] = Field(default_factory=dict, description="JSON Schema for config")
    
    # UI metadata
    ui: Dict[str, Any] = Field(default_factory=dict, description="Frontend rendering hints")
    
    # Optional metadata
    author: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    
    def to_agent_operator_spec(self) -> "AgentOperatorSpec":
        """
        Convert to AgentOperatorSpec for registry compatibility.
        
        Returns an AgentOperatorSpec that can be registered in
        AgentOperatorRegistry for frontend consumption.
        """
        from app.agent.registry import AgentOperatorSpec, AgentStateField
        
        # Map string field names to AgentStateField enums
        valid_reads = []
        for r in self.reads:
            try:
                valid_reads.append(AgentStateField(r))
            except ValueError:
                pass  # Skip invalid field names
        
        valid_writes = []
        for w in self.writes:
            try:
                valid_writes.append(AgentStateField(w))
            except ValueError:
                pass
        
        # Build UI config with artifact metadata
        ui_config = {
            **self.ui,
            "isArtifact": True,
            "artifactId": self.artifact_id,
            "artifactVersion": self.version,
            "inputType": self.input_type,
            "outputType": self.output_type,
            # Field mapping support
            "inputs": self.inputs,
            "outputs": self.outputs,
        }
        
        # Build config fields from schema
        config_fields = []
        if self.config_schema.get("properties"):
            for name, prop in self.config_schema["properties"].items():
                field = {
                    "name": name,
                    "label": prop.get("title", name),
                    "fieldType": self._map_json_type_to_field_type(prop.get("type", "string")),
                    "required": name in self.config_schema.get("required", []),
                    "description": prop.get("description"),
                }
                if "default" in prop:
                    field["default"] = prop["default"]
                if "enum" in prop:
                    field["options"] = [{"value": v, "label": v} for v in prop["enum"]]
                config_fields.append(field)
        
        ui_config["configFields"] = config_fields
        
        return AgentOperatorSpec(
            type=f"artifact:{self.artifact_id}",
            category=self.category,
            display_name=self.display_name,
            description=self.description or "",
            reads=valid_reads,
            writes=valid_writes,
            config_schema=self.config_schema,
            ui=ui_config
        )
    
    def _map_json_type_to_field_type(self, json_type: str) -> str:
        """Map JSON Schema types to frontend field types."""
        mapping = {
            "string": "string",
            "integer": "number",
            "number": "number",
            "boolean": "boolean",
            "array": "json",
            "object": "json",
        }
        return mapping.get(json_type, "string")
