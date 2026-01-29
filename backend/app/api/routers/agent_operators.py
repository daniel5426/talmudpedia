from typing import List, Dict, Any
from fastapi import APIRouter
from app.agent.registry import AgentOperatorRegistry, AgentOperatorSpec
from app.agent.executors.standard import register_standard_operators

router = APIRouter(prefix="/agents/operators", tags=["agents"])

# Ensure standard operators are registered when this router is loaded
register_standard_operators()

@router.get("")
def list_agent_operators() -> List[Dict[str, Any]]:
    """
    List all available agent operators (nodes) for the builder catalog.
    """
    operators = AgentOperatorRegistry.list_operators()
    # Manually serialize to ensure enum values are converted to strings
    return [op.model_dump() for op in operators]
