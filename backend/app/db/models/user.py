from typing import Optional
from datetime import datetime
from pydantic import Field, EmailStr
from .base import MongoModel

class User(MongoModel):
    email: EmailStr
    hashed_password: str
    full_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    role: str = "user"
    avatar: Optional[str] = None
    token_usage: int = 0
