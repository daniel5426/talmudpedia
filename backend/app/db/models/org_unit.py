from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import Field
from enum import Enum

from .base import MongoModel, PyObjectId


class OrgUnitType(str, Enum):
    ORG = "org"
    DEPT = "dept"
    TEAM = "team"


class OrgUnit(MongoModel):
    tenant_id: PyObjectId
    parent_id: Optional[PyObjectId] = None
    name: str
    slug: str
    type: OrgUnitType
    metadata: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OrgMembership(MongoModel):
    tenant_id: PyObjectId
    user_id: PyObjectId
    org_unit_id: PyObjectId
    joined_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "active"
