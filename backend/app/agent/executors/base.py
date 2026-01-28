from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.agent.registry import AgentStateField

class ValidationResult:
    def __init__(self, valid: bool, errors: list[str] = None):
        self.valid = valid
        self.errors = errors or []

class BaseNodeExecutor(ABC):
    """
    Abstract base class for all Agent Node Executors.
    Each node type in the graph must have a corresponding executor.
    """
    
    def __init__(self, tenant_id: UUID, db: Any):
        self.tenant_id = tenant_id
        self.db = db

    @abstractmethod
    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute the node logic.
        
        Args:
            state: The current state of the agent execution (read-only snapshot corresponding to 'reads')
            config: The configuration for this specific node instance
            context: Global execution context (user_id, runtime_env, etc.)
            
        Returns:
            Dict: The partial state update to be merged (corresponding to 'writes')
        """
        pass

    async def can_execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> bool:
        """
        Hook to check if the node can execute.
        Useful for HITL pauses, rate limits, or conditional guards.
        
        Returns:
            bool: True if execution should proceed, False to pause/skip.
        """
        return True

    async def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """
        Validate the node configuration at compile time or save time.
        Override this to add custom validation logic beyond JSON schema.
        """
        return ValidationResult(valid=True)
