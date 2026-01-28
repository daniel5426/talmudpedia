from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field

class CompiledAgent(BaseModel):
    """
    Immutable snapshot of a compiled agent.
    This is what gets executed by the runtime.
    """
    agent_id: UUID
    version: int
    dag: Dict[str, Any] # Serialized graph structure
    config: Dict[str, Any] = Field(default_factory=dict) # Global config
    created_at: datetime = Field(default_factory=datetime.utcnow)
    hash: str # Checksum for integrity
    metadata: Dict[str, Any] = Field(default_factory=dict)
