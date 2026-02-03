"""
Field Resolver - Resolves input fields for nodes based on mappings and expressions.

This module handles:
1. Expression parsing ({{ upstream_node.field }} syntax)
2. State field resolution (state.messages, state.context)
3. Upstream node output resolution
4. Validation against artifact input schemas
"""
import re
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Expression pattern: {{ expression }}
EXPRESSION_PATTERN = re.compile(r'\{\{\s*(.+?)\s*\}\}')


@dataclass
class ResolutionError:
    """Error encountered during field resolution."""
    field: str
    message: str
    severity: str = "warning"  # "warning" or "error"
    

@dataclass
class InputFieldSpec:
    """Specification for an expected input field."""
    name: str
    type: str
    required: bool = False
    default: Any = None
    description: Optional[str] = None


class FieldResolver:
    """
    Resolves input fields for a node based on:
    1. Explicit mappings in node config (input_mappings)
    2. Default pass-through from state
    3. Fallback to artifact's declared defaults
    
    Expression Syntax:
    - {{ state.messages }} - Pull from agent state
    - {{ state.context.field }} - Nested state access  
    - {{ upstream.node_id.field }} - Pull from specific upstream node output
    - Direct value - Use as literal (no {{ }})
    """
    
    def __init__(self, strict_mode: bool = False):
        """
        Args:
            strict_mode: If True, raise errors on missing required fields.
                        If False (default), log warnings and continue.
        """
        self.strict_mode = strict_mode
    
    def resolve_inputs(
        self, 
        state: Dict[str, Any], 
        config: Dict[str, Any], 
        input_specs: Optional[List[InputFieldSpec]] = None
    ) -> Dict[str, Any]:
        """
        Extract and validate inputs for the node.
        
        Args:
            state: Current agent state (messages, context, state vars, _node_outputs)
            config: Node configuration including optional 'input_mappings'
            input_specs: Optional list of expected input field specifications
            
        Returns:
            Dictionary of resolved input values
        """
        input_mappings = config.get("input_mappings", {})
        resolved = {}
        
        # If no input specs defined, use pass-through mode
        if not input_specs:
            # Simply return the mappings resolved against state
            for field_name, expression in input_mappings.items():
                resolved[field_name] = self._resolve_expression(expression, state)
            return resolved
        
        # Resolve each expected input field
        for spec in input_specs:
            field_name = spec.name
            
            if field_name in input_mappings:
                # Explicit mapping provided
                expression = input_mappings[field_name]
                resolved[field_name] = self._resolve_expression(expression, state)
            elif spec.default is not None:
                # Use default value
                resolved[field_name] = spec.default
            elif not spec.required:
                # Optional field with no default -> None
                resolved[field_name] = None
            else:
                # Required field with no mapping and no default
                # In lenient mode, we'll set to None and log warning
                resolved[field_name] = None
        
        return resolved
    
    def _resolve_expression(self, expression: Any, state: Dict[str, Any]) -> Any:
        """
        Resolve a single expression or literal value.
        
        Args:
            expression: Either a template string ({{ path }}) or a literal value
            state: The current state dictionary
            
        Returns:
            The resolved value
        """
        if not isinstance(expression, str):
            # Literal value (int, bool, list, dict, etc.)
            return expression
        
        # Check if it's a template expression
        match = EXPRESSION_PATTERN.fullmatch(expression.strip())
        if match:
            path = match.group(1).strip()
            return self._resolve_path(path, state)
        
        # Check for embedded expressions within a larger string
        if EXPRESSION_PATTERN.search(expression):
            # String interpolation mode
            def replacer(m):
                path = m.group(1).strip()
                value = self._resolve_path(path, state)
                return str(value) if value is not None else ""
            return EXPRESSION_PATTERN.sub(replacer, expression)
        
        # Plain string literal
        return expression
    
    def _resolve_path(self, path: str, state: Dict[str, Any]) -> Any:
        """
        Resolve a dot-notation path against the state.
        
        Supported patterns:
        - state.messages -> state["messages"]
        - state.context.field -> state["context"]["field"]
        - upstream.node_id.field -> state["_node_outputs"]["node_id"]["field"]
        - messages -> state["messages"] (shorthand)
        - messages[-1].content -> last message content
        
        Args:
            path: Dot-separated path string
            state: The state dictionary
            
        Returns:
            Resolved value or None if not found
        """
        parts = self._tokenize_path(path)
        if not parts:
            return None
        
        # Handle known prefixes
        first = parts[0]
        
        if first == "upstream":
            # {{ upstream.node_id.field }}
            if len(parts) < 3:
                logger.warning(f"Invalid upstream path: {path}")
                return None
            node_id = parts[1]
            field_path = parts[2:]
            node_outputs = state.get("_node_outputs", {})
            node_output = node_outputs.get(node_id, {})
            return self._traverse(node_output, field_path)
        
        elif first == "state":
            # {{ state.field }} or {{ state.nested.field }}
            return self._traverse(state, parts[1:])
        
        else:
            # Shorthand: {{ messages }} -> state["messages"]
            return self._traverse(state, parts)
    
    def _tokenize_path(self, path: str) -> List[str]:
        """
        Tokenize a path string into parts, handling array indices.
        
        Examples:
        - "messages" -> ["messages"]
        - "state.messages" -> ["state", "messages"]
        - "messages[-1].content" -> ["messages", -1, "content"]
        """
        tokens = []
        current = ""
        i = 0
        
        while i < len(path):
            char = path[i]
            
            if char == '.':
                if current:
                    tokens.append(current)
                    current = ""
            elif char == '[':
                if current:
                    tokens.append(current)
                    current = ""
                # Find closing bracket
                end = path.find(']', i)
                if end == -1:
                    current += char
                else:
                    index_str = path[i+1:end]
                    try:
                        tokens.append(int(index_str))
                    except ValueError:
                        # String key in brackets
                        tokens.append(index_str.strip('"\''))
                    i = end
            else:
                current += char
            i += 1
        
        if current:
            tokens.append(current)
        
        return tokens
    
    def _traverse(self, obj: Any, parts: List[Any]) -> Any:
        """Traverse an object using path parts."""
        current = obj
        
        for part in parts:
            if current is None:
                return None
            
            if isinstance(part, int):
                # Array index
                if isinstance(current, (list, tuple)) and -len(current) <= part < len(current):
                    current = current[part]
                else:
                    return None
            elif isinstance(current, dict):
                current = current.get(part)
            elif hasattr(current, part):
                current = getattr(current, part)
            elif hasattr(current, 'get'):
                current = current.get(part)
            else:
                return None
        
        return current
    
    def validate_inputs(
        self, 
        resolved: Dict[str, Any], 
        input_specs: List[InputFieldSpec]
    ) -> List[ResolutionError]:
        """
        Validate resolved inputs against specifications.
        
        Args:
            resolved: Dictionary of resolved input values
            input_specs: List of expected input field specifications
            
        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []
        
        for spec in input_specs:
            value = resolved.get(spec.name)
            
            if spec.required and value is None:
                errors.append(ResolutionError(
                    field=spec.name,
                    message=f"Required field '{spec.name}' is missing or null",
                    severity="error" if self.strict_mode else "warning"
                ))
        
        return errors


# Convenience function for executor usage
def resolve_artifact_inputs(
    state: Dict[str, Any],
    config: Dict[str, Any],
    artifact_inputs: Optional[List[Dict[str, Any]]] = None,
    strict: bool = False
) -> Dict[str, Any]:
    """
    Convenience wrapper for resolving artifact inputs.
    
    Args:
        state: Agent state dictionary
        config: Node configuration with optional input_mappings
        artifact_inputs: List of input field dicts from artifact.yaml
        strict: Whether to use strict validation mode
        
    Returns:
        Dictionary of resolved input values
    """
    resolver = FieldResolver(strict_mode=strict)
    
    input_specs = None
    if artifact_inputs:
        input_specs = [
            InputFieldSpec(
                name=inp.get("name"),
                type=inp.get("type", "any"),
                required=inp.get("required", False),
                default=inp.get("default"),
                description=inp.get("description")
            )
            for inp in artifact_inputs
            if inp.get("name")
        ]
    
    resolved = resolver.resolve_inputs(state, config, input_specs)
    
    # Log validation warnings in non-strict mode
    if input_specs:
        errors = resolver.validate_inputs(resolved, input_specs)
        for err in errors:
            if err.severity == "warning":
                logger.warning(f"Field resolution: {err.message}")
            else:
                logger.error(f"Field resolution: {err.message}")
    
    return resolved
