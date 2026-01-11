from typing import Optional, List
from datetime import datetime
from pydantic import Field, BaseModel
from enum import Enum

from .base import MongoModel, PyObjectId


class Action(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    ADMIN = "admin"


class ResourceType(str, Enum):
    INDEX = "index"
    PIPELINE = "pipeline"
    JOB = "job"
    TENANT = "tenant"
    ORG_UNIT = "org_unit"
    ROLE = "role"
    MEMBERSHIP = "membership"
    AUDIT = "audit"


class Permission(BaseModel):
    resource_type: ResourceType
    action: Action

    def __hash__(self):
        return hash((self.resource_type, self.action))

    def __eq__(self, other):
        if isinstance(other, Permission):
            return self.resource_type == other.resource_type and self.action == other.action
        return False


class ActorType(str, Enum):
    USER = "user"
    SERVICE = "service"
    AGENT = "agent"


class Role(MongoModel):
    tenant_id: PyObjectId
    name: str
    description: Optional[str] = None
    permissions: List[Permission] = []
    is_system: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RoleAssignment(MongoModel):
    tenant_id: PyObjectId
    user_id: PyObjectId
    actor_type: ActorType = ActorType.USER
    role_id: PyObjectId
    scope_id: PyObjectId
    scope_type: str
    assigned_by: PyObjectId
    assigned_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
