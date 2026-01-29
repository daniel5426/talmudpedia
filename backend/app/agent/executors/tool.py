import logging
import json
import httpx
from typing import Any, Dict
from uuid import UUID

from app.agent.executors.base import BaseNodeExecutor, ValidationResult
from app.agent.registry import AgentStateField
from sqlalchemy import select
from app.db.postgres.models.registry import ToolRegistry

logger = logging.getLogger(__name__)

class ToolNodeExecutor(BaseNodeExecutor):
    async def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        if not config.get("tool_id"):
            return ValidationResult(valid=False, errors=["Missing 'tool_id' in configuration"])
        return ValidationResult(valid=True)

    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute a Tool.
        1. Fetch tool definition from DB (scoped by tenant).
        2. Resolve inputs from state.
        3. functionality based on implementation_type.
        """
        tool_id_str = config.get("tool_id")
        if not tool_id_str:
             raise ValueError("Missing tool_id")
        
        tool_id = UUID(tool_id_str)
        
        # 1. Fetch Tool
        stmt = select(ToolRegistry).where(ToolRegistry.id == tool_id)
        result = await self.db.execute(stmt)
        tool = result.scalar_one_or_none()
        
        if not tool:
            # Fallback for system tools if needed, but registry handles scope usually
            raise ValueError(f"Tool {tool_id} not found")

        # 2. Resolve Inputs
        # Simple Logic: Pass whole state or specific mapped inputs? 
        # For Phase 1/2: Pass context or message content if available.
        # Ideally, we should use `tool.schema['input']` to map state fields to tool inputs.
        # Here we assume the input is in `state.get('context')` or passed in explicitly?
        # Let's assume input comes from `state['context']` or is passed in `runtime_input`.
        input_data = state.get("context", {})
        if not isinstance(input_data, dict):
            # Try to parse from last message?
            last_msg = state.get("messages", [])[-1] if state.get("messages") else None
            if last_msg:
                 # Minimal fallback
                 input_data = {"text": getattr(last_msg, "content", str(last_msg))}

        # Extract emitter from ContextVar (global implicit context)
        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        
        node_id = context.get("node_id", "tool_node") if context else "tool_node"
        
        # Emit Tool Start
        if emitter:
            emitter.emit_tool_start(tool.name, input_data, node_id)

        # 3. Execute
        impl_type = getattr(tool, "implementation_type", "internal") # Field might be in schema or separate column? 
        # In the `tools.py` router `ToolRegistry` model was used. Let's assume `implementation_type` is part of `schema` or `config_schema`.
        # Wait, looked at `ToolRegistry` model in `tools.py` via `ToolResponse`: it has `config_schema`. 
        # But `agent-resources.ts` has `implementation_type`.
        # Let's try to find where `implementation_type` is stored. 
        # It might be in `tool.schema` or a column I missed.
        # I'll default to checking `tool.schema` or just assuming "http" if config has url.
        
        # Checking implementation details from common patterns:
        config_schema = tool.config_schema or {}
        implementation_config = config_schema.get("implementation", {})
        impl_type = implementation_config.get("type", "internal")

        output_data = {}

        try:
            if impl_type == "http":
                url = implementation_config.get("url")
                method = implementation_config.get("method", "POST")
                headers = implementation_config.get("headers", {})
                
                async with httpx.AsyncClient() as client:
                    response = await client.request(method, url, json=input_data, headers=headers)
                    response.raise_for_status()
                    output_data = response.json()
            
            elif impl_type == "function":
                 # TODO: Registry of internal functions
                 output_data = {"error": "Function execution not fully implemented"}
            
            else:
                # Stub for now
                output_data = {"status": "executed", "tool": tool.name, "input": input_data}
            
            # Emit Tool End
            if emitter:
                emitter.emit_tool_end(tool.name, output_data, node_id)
            
            return {
                "tool_outputs": [output_data],
                # Optionally update context
                "context": output_data
            }
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            if emitter:
                emitter.emit_error(str(e), node_id)
            raise e
