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

    # Persistent user-defined state
    state: Annotated[Dict[str, Any], operator.or_]

    # Control flow
    next: Optional[str]
    branch_taken: Optional[str]
    loop_counters: Dict[str, int]
    approval_status: Optional[str]
    classification_result: Optional[str]

    # HITL inputs (carried in from initial input/resume payloads)
    approval: Optional[str]
    comment: Optional[str]
    input: Optional[str]
    message: Optional[str]
    
    # Current query being processed (for RAG)
    query: Optional[str]
    
    # Retrieved context
    context: Any
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

    # Internal: per-node outputs for field mapping ({{ upstream.node_id.field }})
    _node_outputs: Annotated[Dict[str, Any], operator.or_]

    # Transform node output (current step)
    transform_output: Annotated[Dict[str, Any], operator.or_]
