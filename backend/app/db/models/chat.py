from typing import List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field
from .base import MongoModel

class Citation(BaseModel):
    title: str
    url: str
    description: str

class ReasoningStep(BaseModel):
    step: str
    status: str
    message: str
    citations: Optional[List[Citation]] = None

class Message(BaseModel):
    role: str
    content: str
    citations: Optional[List[Citation]] = None
    reasoning_steps: Optional[List[ReasoningStep]] = None
    reasoning_items: Optional[List[Any]] = None  # Stores raw output items including encrypted reasoning
    thinking_duration_ms: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Chat(MongoModel):
    title: str
    messages: List[Message] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
