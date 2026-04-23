from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

class CustomOperatorBase(BaseModel):
    name: str
    display_name: str
    category: str
    description: Optional[str] = None
    python_code: str
    input_type: str
    output_type: str
    config_schema: List[Dict[str, Any]] = []
    is_active: bool = True

class CustomOperatorCreate(CustomOperatorBase):
    pass

class CustomOperatorUpdate(BaseModel):
    display_name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    python_code: Optional[str] = None
    input_type: Optional[str] = None
    output_type: Optional[str] = None
    config_schema: Optional[List[Dict[str, Any]]] = None
    is_active: Optional[bool] = None

class CustomOperatorResponse(CustomOperatorBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    version: str
    created_at: datetime
    updated_at: datetime
    created_by: Optional[uuid.UUID] = None

class CustomOperatorTestRequest(BaseModel):
    python_code: str
    input_data: Any
    config: Dict[str, Any] = {}
    input_type: str = "raw_documents"
    output_type: str = "raw_documents"

class CustomOperatorTestResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0
