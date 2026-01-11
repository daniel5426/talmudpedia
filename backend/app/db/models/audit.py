from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import Field
from enum import Enum

from .base import MongoModel, PyObjectId
from .rbac import Action, ResourceType, ActorType


class AuditResult(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


class AuditLog(MongoModel):
    tenant_id: PyObjectId
    org_unit_id: Optional[PyObjectId] = None

    actor_id: PyObjectId
    actor_type: ActorType
    actor_email: str

    action: Action
    resource_type: ResourceType
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None

    result: AuditResult
    failure_reason: Optional[str] = None

    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    request_params: Optional[Dict[str, Any]] = None

    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: Optional[int] = None
