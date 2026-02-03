from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
from enum import Enum

class ArtifactType(str, Enum):
    DRAFT = "draft"
    PROMOTED = "promoted"
    BUILTIN = "builtin"

class ArtifactScope(str, Enum):
    RAG = "rag"
    AGENT = "agent"
    BOTH = "both"

class ArtifactConfigField(BaseModel):
    name: str
    type: str # string, integer, float, boolean, json, select, etc.
    label: Optional[str] = None
    required: bool = False
    default: Any = None
    description: Optional[str] = None
    options: Optional[List[Any]] = None
    placeholder: Optional[str] = None


class ArtifactInputField(BaseModel):
    """Defines an expected input field for an artifact."""
    name: str
    type: str  # string, object, array, raw_documents, message, etc.
    required: bool = False
    default: Any = None
    description: Optional[str] = None
    

class ArtifactOutputField(BaseModel):
    """Defines an output field produced by an artifact."""
    name: str
    type: str  # string, object, array, normalized_documents, etc.
    description: Optional[str] = None

class ArtifactSchema(BaseModel):
    id: str  # UUID for drafts, string slug for promoted/builtin
    name: str # The internal slug name
    display_name: str
    description: Optional[str] = None
    category: str
    input_type: str
    output_type: str
    version: str
    type: ArtifactType
    scope: ArtifactScope
    author: Optional[str] = None
    tags: List[str] = []
    config_schema: List[Dict[str, Any]] = [] # Flexible list of config fields
    created_at: Optional[datetime] = None
    updated_at: datetime
    python_code: Optional[str] = None
    reads: List[str] = []
    writes: List[str] = []
    
    # Input/output field definitions for field mapping
    inputs: List[Dict[str, Any]] = []  # List of ArtifactInputField dicts
    outputs: List[Dict[str, Any]] = [] # List of ArtifactOutputField dicts
    
    # For promoted artifacts
    path: Optional[str] = None 
    
class ArtifactCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    category: str = "custom"
    input_type: str = "raw_documents"
    output_type: str = "raw_documents"
    scope: ArtifactScope = ArtifactScope.RAG
    python_code: str
    config_schema: List[Dict[str, Any]] = []
    reads: List[str] = []
    writes: List[str] = []
    inputs: List[Dict[str, Any]] = []
    outputs: List[Dict[str, Any]] = []

class ArtifactUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    input_type: Optional[str] = None
    output_type: Optional[str] = None
    scope: Optional[ArtifactScope] = None
    python_code: Optional[str] = None
    config_schema: Optional[List[Dict[str, Any]]] = None
    reads: Optional[List[str]] = None
    writes: Optional[List[str]] = None

class ArtifactTestRequest(BaseModel):
    artifact_id: Optional[str] = None # If testing existing one
    python_code: Optional[str] = None # If testing with unsaved code
    input_data: Any
    config: Dict[str, Any] = {}
    input_type: str = "raw_documents"
    output_type: str = "raw_documents"

class ArtifactTestResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0

class ArtifactPromoteRequest(BaseModel):
    namespace: str = "custom"
    version: Optional[str] = None
