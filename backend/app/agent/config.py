from typing import Optional

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-5.1"
    api_key: Optional[str] = None


class RetrievalConfig(BaseModel):
    provider: str = "vector"
    index_name: str = "talmudpedia"


class AgentConfig(BaseModel):
    workflow: str = "advanced_rag"
    llm: LLMConfig = Field(default_factory=LLMConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)


