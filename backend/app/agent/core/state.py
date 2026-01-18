from typing import Annotated, Any, Dict, List, Optional, TypedDict
import operator

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages

from app.agent.core.interfaces import Document


class AgentState(TypedDict):
    """
    State of the agent execution graph.
    """
    # Conversation history
    messages: Annotated[List[BaseMessage], add_messages]
    
    # Current query being processed (for RAG)
    query: Optional[str]
    
    # Retrieved context
    context: str
    retrieved_docs: List[Dict[str, Any]]  # Keeping Dict for compatibility with existing frontend for now
    
    # Reasoning and artifacts
    reasoning_items: Annotated[List[Dict[str, Any]], operator.add]
    reasoning_steps_parsed: Annotated[List[Dict[str, Any]], operator.add]
    
    # File attachments
    files: Optional[List[Dict[str, Any]]]
    
    # Execution trace
    steps: Annotated[List[str], operator.add]
    
    # Error handling
    error: Optional[str]
