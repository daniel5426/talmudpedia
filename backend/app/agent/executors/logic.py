"""
Logic Executors - If/Else, While, Conditional

Provides executors for logic/control flow operators:
- IfElseNodeExecutor: Multi-condition branching with CEL expressions
- WhileNodeExecutor: Loop execution with safety limits
- ConditionalNodeExecutor: Legacy conditional (kept for backward compatibility)
- ParallelNodeExecutor: Parallel branch execution
"""

import re
import logging
from typing import Any, Dict, List, Optional

from app.agent.executors.base import BaseNodeExecutor, ValidationResult
from app.agent.cel_engine import evaluate_cel, validate_cel

logger = logging.getLogger(__name__)


class IfElseNodeExecutor(BaseNodeExecutor):
    """
    Executor for the If/Else node.
    
    Evaluates multiple conditions in order and routes to the first matching branch.
    Uses restricted CEL expressions for conditions.
    
    Output handles are dynamically generated based on conditions:
    - Each condition can have an optional name (becomes handle label)
    - Final "else" handle is always present
    """
    
    async def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate conditions at compile time."""
        errors = []
        conditions = config.get("conditions", [])
        
        if not conditions:
            # At minimum, node routes to "else" if no conditions
            return ValidationResult(valid=True, errors=[])
        
        for i, condition in enumerate(conditions):
            expression = condition.get("expression")
            
            if not expression:
                errors.append(f"Condition {i+1}: Missing expression")
                continue
            
            validation = validate_cel(expression)
            if not validation.valid:
                errors.append(f"Condition {i+1}: {'; '.join(validation.errors)}")
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)
    
    async def execute(
        self,
        state: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Evaluate conditions and determine routing.
        
        Returns:
            State update with:
            - 'next': The branch to take (condition name or index, or "else")
            - 'branch_taken': Same as 'next' for tracing
            - 'condition_results': Debug info about all condition evaluations
        """
        conditions = config.get("conditions", [])
        condition_results = []

        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        node_id = context.get("node_id", "if_else") if context else "if_else"
        node_name = context.get("node_name", "If/Else") if context else "If/Else"
        if emitter:
            emitter.emit_node_start(node_id, node_name, "if_else", {"conditions": len(conditions)})
        
        for i, condition in enumerate(conditions):
            expression = condition.get("expression", "")
            name = condition.get("name") or f"condition_{i}"
            
            try:
                result = evaluate_cel(expression, state, context)
                condition_results.append({
                    "name": name,
                    "expression": expression,
                    "result": result
                })
                
                if result:
                    logger.debug(f"If/Else: Branch '{name}' matched (expression: {expression})")
                    result = {
                        "next": name,
                        "branch_taken": name,
                        "condition_results": condition_results
                    }
                    if emitter:
                        emitter.emit_node_end(node_id, node_name, "if_else", {"branch_taken": name})
                    return result
                    
            except Exception as e:
                logger.warning(f"If/Else condition '{name}' evaluation error: {e}")
                condition_results.append({
                    "name": name,
                    "expression": expression,
                    "result": False,
                    "error": str(e)
                })
        
        # No condition matched, take "else" branch
        logger.debug("If/Else: No conditions matched, taking 'else' branch")
        result = {
            "next": "else",
            "branch_taken": "else",
            "condition_results": condition_results
        }
        if emitter:
            emitter.emit_node_end(node_id, node_name, "if_else", {"branch_taken": "else"})
        return result
    
    def get_output_handles(self, config: Dict[str, Any]) -> List[str]:
        """
        Get dynamic output handle names based on conditions.
        Used by graph compiler to set up edges.
        """
        conditions = config.get("conditions", [])
        handles = []
        
        for i, condition in enumerate(conditions):
            name = condition.get("name") or f"condition_{i}"
            handles.append(name)
        
        handles.append("else")  # Always have else
        return handles


class WhileNodeExecutor(BaseNodeExecutor):
    """
    Executor for the While node.
    
    Loops while a condition is true, with safety limits to prevent infinite loops.
    
    Output handles:
    - "loop": Continue looping (body execution)
    - "exit": Exit loop (condition false or max iterations reached)
    """
    
    DEFAULT_MAX_ITERATIONS = 10
    
    async def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate while configuration at compile time."""
        errors = []
        warnings = []
        
        condition = config.get("condition")
        max_iterations = config.get("max_iterations")
        
        if not condition:
            errors.append("While node requires a condition expression")
            return ValidationResult(valid=False, errors=errors)
        
        validation = validate_cel(condition)
        if not validation.valid:
            errors.append(f"Condition: {'; '.join(validation.errors)}")
        
        # Warning for no max_iterations (complexity warning)
        if max_iterations is None:
            warnings.append(f"No max_iterations set, defaulting to {self.DEFAULT_MAX_ITERATIONS}")
        elif max_iterations > 100:
            warnings.append(f"max_iterations ({max_iterations}) is very high, may cause performance issues")
        
        result = ValidationResult(valid=len(errors) == 0, errors=errors)
        # Note: Our ValidationResult doesn't have warnings, but we log them
        for w in warnings:
            logger.warning(f"While node validation warning: {w}")
        
        return result
    
    async def execute(
        self,
        state: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Evaluate while condition and determine routing.
        
        Returns:
            State update with:
            - 'next': "loop" or "exit"
            - 'loop_counters': Updated iteration counts
        """
        condition = config.get("condition", "false")
        max_iterations = config.get("max_iterations", self.DEFAULT_MAX_ITERATIONS)
        
        node_id = context.get("node_id", "while") if context else "while"
        
        # Get current iteration count
        loop_counters = state.get("loop_counters", {})
        if not isinstance(loop_counters, dict):
            loop_counters = {}
        
        current_iteration = loop_counters.get(node_id, 0)
        
        # Check if we've hit max iterations
        if current_iteration >= max_iterations:
            logger.info(f"While loop '{node_id}' hit max iterations ({max_iterations}), exiting")
            return {
                "next": "exit",
                "loop_counters": {**loop_counters, node_id: current_iteration}
            }
        
        # Evaluate condition
        try:
            result = evaluate_cel(condition, state, context)
            
            if result:
                # Continue looping
                new_iteration = current_iteration + 1
                logger.debug(f"While loop '{node_id}' iteration {new_iteration}/{max_iterations}")
                return {
                    "next": "loop",
                    "loop_counters": {**loop_counters, node_id: new_iteration}
                }
            else:
                # Condition false, exit
                logger.debug(f"While loop '{node_id}' condition false, exiting")
                return {
                    "next": "exit",
                    "loop_counters": {**loop_counters, node_id: current_iteration}
                }
                
        except Exception as e:
            logger.error(f"While loop condition evaluation failed: {e}")
            # On error, exit loop for safety
            return {
                "next": "exit",
                "loop_counters": {**loop_counters, node_id: current_iteration},
                "error": str(e)
            }


class ConditionalNodeExecutor(BaseNodeExecutor):
    """
    Legacy Conditional node executor.
    Kept for backward compatibility with existing agents.
    
    For new workflows, use IfElseNodeExecutor instead.
    """
    
    async def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        if not config.get("condition_type"):
            return ValidationResult(valid=False, errors=["Missing 'condition_type'"])
        return ValidationResult(valid=True)

    async def execute(
        self,
        state: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
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
            last_msg = messages[-1]
            if isinstance(last_msg, dict):
                target_text = str(last_msg.get("content", ""))
            elif hasattr(last_msg, "content"):
                target_text = str(last_msg.content)
            else:
                target_text = str(last_msg)

        result = False
        
        if condition_type == "contains":
            result = value_to_check in target_text
        elif condition_type == "regex":
            result = bool(re.search(value_to_check, target_text))
        elif condition_type == "llm_decision":
            result = state.get("next") == value_to_check
        elif condition_type == "cel":
            # New: Support CEL expressions in legacy node
            try:
                result = evaluate_cel(value_to_check, state, context)
            except Exception as e:
                logger.error(f"CEL evaluation in conditional: {e}")
                result = False

        return {
            "next": "true" if result else "false",
            "branch_taken": "true" if result else "false",
            "condition_result": result
        }


class ParallelNodeExecutor(BaseNodeExecutor):
    """
    Executor for Parallel node.
    
    Parallel execution is handled by Graph topology, not this executor.
    This node just passes state through or fans out data if needed.
    """
    
    async def execute(
        self,
        state: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        # Parallel execution is handled by Graph topology.
        # This node just passes state through.
        logger.debug("Parallel node executed (pass-through)")
        return {}
