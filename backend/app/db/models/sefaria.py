from typing import List, Dict, Optional, Any
from pydantic import Field
from .base import MongoModel

class Index(MongoModel):
    title: str
    categories: List[str]
    schema_structure: Dict[str, Any] = Field(alias="schema")  # The node tree structure from Sefaria
    order: Optional[List[int]] = None

class Text(MongoModel):
    title: str
    versionTitle: str
    versionSource: Optional[str] = None
    language: str
    chapter: List[Any]  # Can be list of strings or nested lists
    
class Link(MongoModel):
    refs: List[str]
    type: str
    anchorText: Optional[str] = None
    generated_by: Optional[str] = None
