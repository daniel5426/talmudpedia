from typing import List, Optional
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

class Message(BaseModel):
    role: str
    content: str
    citations: Optional[List[Citation]] = None
    reasoning_steps: Optional[List[ReasoningStep]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Chat(MongoModel):
    title: str
    messages: List[Message] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
