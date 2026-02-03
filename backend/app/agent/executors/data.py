"""
Data Executors - Transform and Set State

Provides executors for data manipulation operators:
- TransformNodeExecutor: Reshape data using CEL expressions
- SetStateNodeExecutor: Explicitly set state variables
"""

import logging
from typing import Any, Dict, List

from app.agent.executors.base import BaseNodeExecutor, ValidationResult
from app.agent.cel_engine import evaluate_cel, validate_cel, CELValidationResult

logger = logging.getLogger(__name__)


class TransformNodeExecutor(BaseNodeExecutor):
    """
    Executor for the Transform node.
    
    Reshapes data using CEL expressions or literal object mappings.
    Results are written to the persistent state.
    
    Modes:
    - expressions: Each mapping uses a CEL expression
    - object: Mappings are literal values
    """
    
    async def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate transform mappings at compile time."""
        errors = []
        mappings = config.get("mappings", [])
        mode = config.get("mode", "expressions")
        
        if not mappings:
            errors.append("Transform node requires at least one mapping")
            return ValidationResult(valid=False, errors=errors)
        
        for i, mapping in enumerate(mappings):
            key = mapping.get("key")
            value = mapping.get("value")
            
            if not key:
                errors.append(f"Mapping {i+1}: Missing output key")
                continue
            
            if value is None:
                errors.append(f"Mapping {i+1}: Missing value expression")
                continue
            
            # Validate CEL expression in expressions mode
            if mode == "expressions":
                validation = validate_cel(value)
                if not validation.valid:
                    errors.append(f"Mapping '{key}': {'; '.join(validation.errors)}")
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)
    
    async def execute(
        self,
        state: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Execute transform mappings.
        
        Args:
            state: Current workflow state
            config: Node configuration with mappings and mode
            context: Execution context
            
        Returns:
            State update with transformed values in 'state' field
        """
        mappings = config.get("mappings", [])
        mode = config.get("mode", "expressions")
        
        # Get current state variables
        current_state = state.get("state", {})
        if not isinstance(current_state, dict):
            current_state = {}
        
        result = {}
        
        for mapping in mappings:
            key = mapping.get("key")
            value = mapping.get("value")
            
            if not key:
                continue
            
            try:
                if mode == "expressions":
                    # Evaluate CEL expression
                    evaluated = evaluate_cel(value, state, context)
                    result[key] = evaluated
                else:
                    # Literal value
                    result[key] = value
                    
                logger.debug(f"Transform: {key} = {result[key]}")
                
            except Exception as e:
                logger.error(f"Transform mapping '{key}' failed: {e}")
                # Continue with other mappings, store error
                result[key] = None
                result[f"_error_{key}"] = str(e)
        
        # Merge results into state variables
        updated_state = {**current_state, **result}
        
        return {
            "state": updated_state,
            "transform_output": result
        }


class SetStateNodeExecutor(BaseNodeExecutor):
    """
    Executor for the Set State node.
    
    Explicitly sets state variables using CEL expressions or literal values.
    Similar to Transform but semantically different - for explicit state management.
    """
    
    async def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate state assignments at compile time."""
        errors = []
        assignments = config.get("assignments", [])
        
        if not assignments:
            errors.append("Set State node requires at least one assignment")
            return ValidationResult(valid=False, errors=errors)
        
        for i, assignment in enumerate(assignments):
            variable = assignment.get("variable")
            value = assignment.get("value")
            
            if not variable:
                errors.append(f"Assignment {i+1}: Missing variable name")
                continue
            
            # Check variable name is valid (no dots for top-level)
            if '.' in variable:
                errors.append(f"Assignment {i+1}: Variable name cannot contain dots. Use Transform for nested updates.")
                continue
            
            if value is None:
                errors.append(f"Assignment {i+1}: Missing value")
                continue
            
            # Validate CEL expression if it looks like one
            if isinstance(value, str) and any(c in value for c in '+-*/%=<>&|()'):
                validation = validate_cel(value)
                if not validation.valid:
                    errors.append(f"Variable '{variable}': {'; '.join(validation.errors)}")
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)
    
    async def execute(
        self,
        state: Dict[str, Any],
        config: Dict[str, Any],
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Execute state assignments.
        
        Args:
            state: Current workflow state
            config: Node configuration with assignments
            context: Execution context
            
        Returns:
            State update with assigned values in 'state' field
        """
        assignments = config.get("assignments", [])
        is_expression = config.get("is_expression", True)
        
        # Get current state variables
        current_state = state.get("state", {})
        if not isinstance(current_state, dict):
            current_state = {}
        
        result = {}
        
        for assignment in assignments:
            variable = assignment.get("variable")
            value = assignment.get("value")
            
            if not variable:
                continue
            
            try:
                if is_expression and isinstance(value, str):
                    # Try to evaluate as CEL expression
                    try:
                        evaluated = evaluate_cel(value, state, context)
                        result[variable] = evaluated
                    except ValueError:
                        # Not a valid expression, use as literal
                        result[variable] = value
                else:
                    # Literal value
                    result[variable] = value
                    
                logger.debug(f"Set State: {variable} = {result[variable]}")
                
            except Exception as e:
                logger.error(f"Set state '{variable}' failed: {e}")
                result[variable] = None
        
        # Merge results into state variables
        updated_state = {**current_state, **result}
        
        return {
            "state": updated_state
        }
