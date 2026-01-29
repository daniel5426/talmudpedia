from enum import Enum
from typing import Any, Dict, Optional, List
from pydantic import BaseModel

class ExecutionMode(str, Enum):
    DEBUG = "debug"         # Playground/Builder: All events, full fidelity
    PRODUCTION = "production" # End-User: Client-safe events only, specific taxonomy

class EventVisibility(str, Enum):
    INTERNAL = "internal"       # Debug only (raw inputs, tool calls, thinking)
    CLIENT_SAFE = "client_safe" # Safe for end-users (final tokens, status updates)

class ExecutionEvent(BaseModel):
    event: str
    data: Any
    run_id: str
    span_id: Optional[str] = None
    name: Optional[str] = None
    visibility: EventVisibility = EventVisibility.INTERNAL
    tags: List[str] = []
    metadata: Dict[str, Any] = {}
