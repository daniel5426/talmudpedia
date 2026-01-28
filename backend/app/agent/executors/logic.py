import re
import logging
from typing import Any, Dict
from app.agent.executors.base import BaseNodeExecutor, ValidationResult

logger = logging.getLogger(__name__)

class ConditionalNodeExecutor(BaseNodeExecutor):
    async def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        if not config.get("condition_type"):
            return ValidationResult(valid=False, errors=["Missing 'condition_type'"])
        return ValidationResult(valid=True)

    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Evaluate condition and return routing key.
        LangGraph uses this routing key to determine the next edge.
        """
        condition_type = config.get("condition_type")
        value_to_check = config.get("condition_value")
        
        # Determine target text to check
        target_text = ""
        messages = state.get("messages", [])
        if messages:
            target_text = str(messages[-1].content) # simplified

        result = False
        
        if condition_type == "contains":
            result = value_to_check in target_text
        elif condition_type == "regex":
            result = bool(re.search(value_to_check, target_text))
        elif condition_type == "llm_decision":
             # Decision already made by previous LLM and stored in routing_key?
             # Or we look for specific structured output?
             # For now, check if routing_key matches value
             result = state.get("next") == value_to_check

        # Return the branch decision
        # In LangGraph conditional edges, we often return the name of the next node or a boolean
        # Here we return a 'branch' key that the edge condition function will read
        return {
            "branch": "true" if result else "false",
            "condition_result": result
        }

class ParallelNodeExecutor(BaseNodeExecutor):
    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        # Parallel execution is handled by Graph topology.
        # This node just passes state through or fans out data if needed.
        return {}
