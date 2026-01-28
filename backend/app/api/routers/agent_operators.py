from typing import List
from fastapi import APIRouter
from app.agent.registry import AgentOperatorRegistry, AgentOperatorSpec
from app.agent.executors.standard import register_standard_operators

router = APIRouter(prefix="/agents/operators", tags=["agents"])

# Ensure standard operators are registered when this router is loaded
register_standard_operators()

@router.get("", response_model=List[AgentOperatorSpec])
def list_agent_operators():
    """
    List all available agent operators (nodes) for the builder catalog.
    """
    return AgentOperatorRegistry.list_operators()
