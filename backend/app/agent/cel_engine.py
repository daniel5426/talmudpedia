"""
CEL Expression Engine - Restricted Profile

Provides a safe, sandboxed evaluation environment for Common Expression Language (CEL)
expressions within agent workflows.

Restrictions:
- ✅ Read-only access to state
- ✅ String operations, math, comparisons, boolean logic
- ✅ Small utility functions
- ❌ No user-defined functions
- ❌ No loops or recursion
- ❌ No mutation
"""

import logging
import re
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


@dataclass
class CELEvaluationResult:
    """Result of a CEL expression evaluation."""
    success: bool
    value: Any = None
    error: Optional[str] = None


@dataclass
class CELValidationResult:
    """Result of validating a CEL expression."""
    valid: bool
    errors: List[str]
    warnings: List[str]


# =============================================================================
# Restricted CEL Evaluator
# =============================================================================

class RestrictedCELEvaluator:
    """
    A restricted CEL evaluator that provides safe expression evaluation.
    
    This evaluator implements a subset of CEL with the following features:
    - Literals: strings, numbers, booleans, null
    - Operators: +, -, *, /, %, ==, !=, <, >, <=, >=, &&, ||, !
    - Accessors: dot notation (obj.field), index notation (list[0], map["key"])
    - Functions: Built-in utility functions only
    
    Security: Read-only access to state, no side effects, no loops.
    """
    
    # Allowed built-in functions
    ALLOWED_FUNCTIONS = {
        # String functions
        "upper": lambda s: str(s).upper() if s is not None else "",
        "lower": lambda s: str(s).lower() if s is not None else "",
        "trim": lambda s: str(s).strip() if s is not None else "",
        "size": lambda s: len(s) if s is not None else 0,
        "contains": lambda s, sub: sub in str(s) if s is not None else False,
        "startsWith": lambda s, prefix: str(s).startswith(prefix) if s is not None else False,
        "endsWith": lambda s, suffix: str(s).endswith(suffix) if s is not None else False,
        "replace": lambda s, old, new: str(s).replace(old, new) if s is not None else "",
        "split": lambda s, sep: str(s).split(sep) if s is not None else [],
        "join": lambda lst, sep: sep.join(str(x) for x in lst) if lst else "",
        
        # Math functions
        "abs": lambda x: abs(x) if x is not None else 0,
        "min": lambda *args: min(args) if args else 0,
        "max": lambda *args: max(args) if args else 0,
        "int": lambda x: int(x) if x is not None else 0,
        "float": lambda x: float(x) if x is not None else 0.0,
        "round": lambda x, n=0: round(x, n) if x is not None else 0,
        
        # Type functions
        "type": lambda x: type(x).__name__,
        "string": lambda x: str(x) if x is not None else "",
        "bool": lambda x: bool(x),
        
        # Collection functions
        "len": lambda x: len(x) if x is not None else 0,
        "keys": lambda d: list(d.keys()) if isinstance(d, dict) else [],
        "values": lambda d: list(d.values()) if isinstance(d, dict) else [],
        "has": lambda d, k: k in d if isinstance(d, dict) else False,
        "exists": lambda x: x is not None,
        "default": lambda x, default: x if x is not None else default,
    }
    
    # Patterns that are blocked for security
    BLOCKED_PATTERNS = [
        r'\bimport\b',
        r'\bexec\b',
        r'\beval\b',
        r'\bcompile\b',
        r'\b__\w+__\b',  # Dunder methods
        r'\bopen\b',
        r'\bfile\b',
        r'\bos\b',
        r'\bsys\b',
        r'\bsubprocess\b',
        r'\bglobals\b',
        r'\blocals\b',
        r'\bgetattr\b',
        r'\bsetattr\b',
        r'\bdelattr\b',
        r'\bfor\b',
        r'\bwhile\b',
        r'\bdef\b',
        r'\bclass\b',
        r'\blambda\b',
        r'\byield\b',
        r'\basync\b',
        r'\bawait\b',
    ]
    
    def __init__(self):
        self._blocked_regex = re.compile('|'.join(self.BLOCKED_PATTERNS), re.IGNORECASE)
    
    def validate(self, expression: str) -> CELValidationResult:
        """
        Validate a CEL expression for security and syntax.
        
        Args:
            expression: The CEL expression to validate
            
        Returns:
            CELValidationResult with validation status
        """
        errors = []
        warnings = []
        
        if not expression or not expression.strip():
            errors.append("Expression cannot be empty")
            return CELValidationResult(valid=False, errors=errors, warnings=warnings)
        
        # Check for blocked patterns
        blocked_match = self._blocked_regex.search(expression)
        if blocked_match:
            errors.append(f"Blocked keyword or pattern found: '{blocked_match.group()}'")
            return CELValidationResult(valid=False, errors=errors, warnings=warnings)
        
        # Check for balanced brackets/parentheses
        brackets = {'(': ')', '[': ']', '{': '}'}
        stack = []
        for char in expression:
            if char in brackets:
                stack.append(brackets[char])
            elif char in brackets.values():
                if not stack or stack.pop() != char:
                    errors.append("Unbalanced brackets or parentheses")
                    return CELValidationResult(valid=False, errors=errors, warnings=warnings)
        
        if stack:
            errors.append("Unbalanced brackets or parentheses")
            return CELValidationResult(valid=False, errors=errors, warnings=warnings)
        
        # Try to compile as Python expression (basic syntax check)
        try:
            compile(expression, '<cel>', 'eval')
        except SyntaxError as e:
            errors.append(f"Syntax error: {e.msg}")
            return CELValidationResult(valid=False, errors=errors, warnings=warnings)
        
        # Warnings for potentially expensive operations
        if expression.count('.') > 10:
            warnings.append("Expression has many nested accessors, may be hard to maintain")
        
        return CELValidationResult(valid=True, errors=errors, warnings=warnings)
    
    def evaluate(
        self,
        expression: str,
        state: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> CELEvaluationResult:
        """
        Evaluate a CEL expression against the given state.
        
        Args:
            expression: The CEL expression to evaluate
            state: The workflow state (read-only access)
            context: Optional step-local context (read-only access)
            
        Returns:
            CELEvaluationResult with the evaluation result or error
        """
        # Validate first
        validation = self.validate(expression)
        if not validation.valid:
            return CELEvaluationResult(
                success=False,
                error="; ".join(validation.errors)
            )
        
        # Build evaluation namespace (read-only copies)
        namespace = self._build_namespace(state, context)
        
        try:
            # Evaluate the expression in the restricted namespace
            result = eval(expression, {"__builtins__": {}}, namespace)
            return CELEvaluationResult(success=True, value=result)
        except NameError as e:
            return CELEvaluationResult(
                success=False,
                error=f"Unknown variable: {e}"
            )
        except KeyError as e:
            return CELEvaluationResult(
                success=False,
                error=f"Key not found: {e}"
            )
        except TypeError as e:
            return CELEvaluationResult(
                success=False,
                error=f"Type error: {e}"
            )
        except Exception as e:
            logger.warning(f"CEL evaluation error: {e}")
            return CELEvaluationResult(
                success=False,
                error=f"Evaluation error: {str(e)}"
            )
    
    def _build_namespace(
        self,
        state: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build the evaluation namespace with read-only state access.
        
        The workflow state structure is:
        {
            "state": {"user_defined_variable": "value", ...},  # persistent state
            "messages": [...],  # chat history
            "context": {...},  # ephemeral context
            ...
        }
        
        In expressions:
        - state.variable refers to state["state"]["variable"]
        - messages, context, etc are also accessible at top level
        - User-defined variables are also exposed directly for convenience
        """
        namespace = {}
        
        # Add built-in functions
        namespace.update(self.ALLOWED_FUNCTIONS)
        
        # Add boolean literals
        namespace['true'] = True
        namespace['false'] = False
        namespace['null'] = None
        namespace['True'] = True
        namespace['False'] = False
        namespace['None'] = None
        
        if state:
            # Extract the nested 'state' field (user-defined variables)
            user_state = state.get('state', {})
            if not isinstance(user_state, dict):
                user_state = {}
            
            # Expose 'state' as the user-defined variables (most common access pattern)
            namespace['state'] = self._freeze(user_state)
            
            # Also expose user state variables directly for convenience
            # (allows both state.counter and counter)
            for key, value in user_state.items():
                if key not in namespace:  # Don't override functions
                    namespace[key] = self._freeze(value)
            
            # Expose other workflow fields at top level
            for key, value in state.items():
                if key == 'state':
                    continue  # Already handled above
                if key not in namespace:  # Don't override functions or user vars
                    namespace[key] = self._freeze(value)
            
            # Also expose the entire workflow state as 'workflow' for advanced access
            namespace['workflow'] = self._freeze(state)
        
        # Add context if provided (overrides workflow context)
        if context:
            namespace['context'] = self._freeze(context)
        
        # Add input alias (common pattern)
        messages = state.get('messages', []) if state else []
        if 'input' not in namespace and messages:
            # Default 'input' to last user message content
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get('role') == 'user':
                    namespace['input'] = msg.get('content', '')
                    break
        elif 'input' not in namespace:
            namespace['input'] = state.get('input', '') if state else ''
        
        return namespace
    
    def _freeze(self, obj: Any) -> Any:
        """
        Create a read-only copy of an object for safe evaluation.
        Recursively freezes nested structures.
        """
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, dict):
            return FrozenDict({k: self._freeze(v) for k, v in obj.items()})
        if isinstance(obj, (list, tuple)):
            return tuple(self._freeze(item) for item in obj)
        # For other types, return as string to prevent method calls
        return str(obj)


class FrozenDict(dict):
    """
    A read-only dictionary that prevents mutation.
    Supports both bracket and dot notation access.
    """
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{key}'")
    
    def __setattr__(self, key, value):
        raise TypeError("Cannot modify frozen state")
    
    def __delattr__(self, key):
        raise TypeError("Cannot modify frozen state")
    
    def __setitem__(self, key, value):
        raise TypeError("Cannot modify frozen state")
    
    def __delitem__(self, key):
        raise TypeError("Cannot modify frozen state")
    
    def pop(self, *args):
        raise TypeError("Cannot modify frozen state")
    
    def popitem(self):
        raise TypeError("Cannot modify frozen state")
    
    def clear(self):
        raise TypeError("Cannot modify frozen state")
    
    def update(self, *args, **kwargs):
        raise TypeError("Cannot modify frozen state")
    
    def setdefault(self, *args):
        raise TypeError("Cannot modify frozen state")


# =============================================================================
# Template String Interpolation
# =============================================================================

class TemplateStringEvaluator:
    """
    Evaluates template strings with {{ variable }} interpolation.
    
    Example:
        "Hello, {{ state.user_name }}! You have {{ len(messages) }} messages."
    """
    
    TEMPLATE_PATTERN = re.compile(r'\{\{\s*(.+?)\s*\}\}')
    
    def __init__(self):
        self._cel = RestrictedCELEvaluator()
    
    def evaluate(
        self,
        template: str,
        state: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> CELEvaluationResult:
        """
        Evaluate a template string, replacing {{ expr }} with evaluated values.
        
        Args:
            template: Template string with {{ expression }} placeholders
            state: The workflow state
            context: Optional step-local context
            
        Returns:
            CELEvaluationResult with the interpolated string or error
        """
        if not template:
            return CELEvaluationResult(success=True, value="")
        
        errors = []
        
        def replace_match(match):
            expr = match.group(1)
            result = self._cel.evaluate(expr, state, context)
            if not result.success:
                errors.append(f"Expression '{expr}': {result.error}")
                return match.group(0)  # Keep original on error
            return str(result.value) if result.value is not None else ""
        
        interpolated = self.TEMPLATE_PATTERN.sub(replace_match, template)
        
        if errors:
            return CELEvaluationResult(
                success=False,
                value=interpolated,
                error="; ".join(errors)
            )
        
        return CELEvaluationResult(success=True, value=interpolated)
    
    def extract_variables(self, template: str) -> List[str]:
        """
        Extract all variable expressions from a template string.
        Useful for validation and autocomplete.
        """
        matches = self.TEMPLATE_PATTERN.findall(template)
        return [m.strip() for m in matches]


# =============================================================================
# Convenience Functions
# =============================================================================

# Global evaluator instances
_cel_evaluator = RestrictedCELEvaluator()
_template_evaluator = TemplateStringEvaluator()


def evaluate_cel(
    expression: str,
    state: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
) -> Any:
    """
    Convenience function to evaluate a CEL expression.
    
    Raises:
        ValueError: If evaluation fails
        
    Returns:
        The evaluated value
    """
    result = _cel_evaluator.evaluate(expression, state, context)
    if not result.success:
        raise ValueError(f"CEL evaluation failed: {result.error}")
    return result.value


def evaluate_template(
    template: str,
    state: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Convenience function to evaluate a template string.
    
    Raises:
        ValueError: If evaluation fails
        
    Returns:
        The interpolated string
    """
    result = _template_evaluator.evaluate(template, state, context)
    if not result.success:
        raise ValueError(f"Template evaluation failed: {result.error}")
    return result.value


def validate_cel(expression: str) -> CELValidationResult:
    """
    Convenience function to validate a CEL expression.
    """
    return _cel_evaluator.validate(expression)


def get_allowed_functions() -> List[str]:
    """
    Get list of allowed function names for autocomplete.
    """
    return sorted(RestrictedCELEvaluator.ALLOWED_FUNCTIONS.keys())
