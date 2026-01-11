from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import Field
from enum import Enum

from .base import MongoModel, PyObjectId


class TenantStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"


class Tenant(MongoModel):
    name: str
    slug: str
    status: TenantStatus = TenantStatus.ACTIVE
    settings: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
