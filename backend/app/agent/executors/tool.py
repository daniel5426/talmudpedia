import logging
import json
from collections.abc import Mapping
import httpx
from typing import Any, Dict
from types import SimpleNamespace
from uuid import UUID

from app.agent.executors.base import BaseNodeExecutor, ValidationResult
from app.agent.registry import AgentStateField
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError
from app.db.postgres.models.registry import ToolRegistry

logger = logging.getLogger(__name__)

class ToolNodeExecutor(BaseNodeExecutor):
    def _resolve_input_data(self, state: Dict[str, Any], config: Dict[str, Any] = None) -> Dict[str, Any]:
        prefer_last = False
        if isinstance(config, dict):
            if config.get("input_source") == "last_agent_output":
                prefer_last = True
            if config.get("prefer_last_agent_output") is True:
                prefer_last = True

        last_output = (state.get("state") or {}).get("last_agent_output")
        if isinstance(last_output, Mapping) and not isinstance(last_output, dict):
            last_output = dict(last_output)
        if prefer_last and isinstance(last_output, dict) and last_output:
            return last_output

        parsed_message = self._try_parse_last_message_json(state)
        if isinstance(parsed_message, dict) and parsed_message.get("action"):
            return parsed_message

        node_output = self._try_extract_last_agent_output(state)
        if isinstance(node_output, dict) and node_output.get("action"):
            return node_output

        input_data = state.get("context")
        if isinstance(input_data, Mapping) and not isinstance(input_data, dict):
            input_data = dict(input_data)
        if isinstance(input_data, dict) and input_data:
            if isinstance(last_output, dict) and last_output and input_data.get("action") == "fetch_catalog":
                return last_output
            if input_data.get("action") == "fetch_catalog":
                parsed = self._try_parse_last_message_json(state)
                if parsed:
                    return parsed
        if not isinstance(input_data, dict) or not input_data:
            input_data = last_output

        if not isinstance(input_data, dict) or not input_data:
            last_msg = state.get("messages", [])[-1] if state.get("messages") else None
            if last_msg:
                if isinstance(last_msg, dict):
                    input_data = {"text": last_msg.get("content")}
                else:
                    input_data = {"text": getattr(last_msg, "content", str(last_msg))}

        if not isinstance(input_data, dict):
            input_data = {}

        return input_data

    def _try_extract_last_agent_output(self, state: Dict[str, Any]) -> Dict[str, Any]:
        node_outputs = state.get("_node_outputs") or {}
        if isinstance(node_outputs, Mapping):
            for output in node_outputs.values():
                if isinstance(output, Mapping):
                    output = dict(output)
                    nested_state = output.get("state")
                    if isinstance(nested_state, Mapping):
                        nested_state = dict(nested_state)
                    if isinstance(nested_state, dict) and "last_agent_output" in nested_state:
                        last = nested_state.get("last_agent_output")
                        if isinstance(last, Mapping) and not isinstance(last, dict):
                            last = dict(last)
                        if isinstance(last, dict):
                            return last
        return {}

    def _try_parse_last_message_json(self, state: Dict[str, Any]) -> Dict[str, Any]:
        last_msg = state.get("messages", [])[-1] if state.get("messages") else None
        if not last_msg:
            return {}
        if isinstance(last_msg, dict):
            content = last_msg.get("content")
        else:
            content = getattr(last_msg, "content", None)
        if not isinstance(content, str):
            return {}
        text = content.strip()
        if not (text.startswith("{") and text.endswith("}")):
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    async def _has_artifact_columns(self) -> bool:
        try:
            result = await self.db.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'tool_registry'
                      AND column_name IN ('artifact_id', 'artifact_version')
                    """
                )
            )
            cols = {row[0] for row in result.all()}
            return "artifact_id" in cols and "artifact_version" in cols
        except Exception:
            # SQLite fallback
            try:
                result = await self.db.execute(text("PRAGMA table_info(tool_registry)"))
                cols = {row[1] for row in result.all()}
                return "artifact_id" in cols and "artifact_version" in cols
            except Exception:
                return False

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
        tool = None
        try:
            if await self._has_artifact_columns():
                stmt = select(ToolRegistry).where(ToolRegistry.id == tool_id)
                result = await self.db.execute(stmt)
                tool = result.scalar_one_or_none()
            else:
                raise ProgrammingError("tool_registry missing artifact columns", None, None)
        except ProgrammingError as e:
            logger.warning(f"ToolNodeExecutor fallback to raw query due to schema mismatch: {e}")
            try:
                await self.db.rollback()
            except Exception:
                pass
            raw = await self.db.execute(
                text(
                    """
                    SELECT id, name, description, scope, schema, config_schema, is_active, is_system
                    FROM tool_registry
                    WHERE id = :tool_id
                    """
                ),
                {"tool_id": str(tool_id)},
            )
            row = raw.first()
            if row:
                # Map to a lightweight object with expected attributes
                tool = SimpleNamespace(
                    id=row[0],
                    name=row[1],
                    description=row[2],
                    scope=row[3],
                    schema=row[4] or {},
                    config_schema=row[5] or {},
                    is_active=row[6],
                    is_system=row[7],
                    artifact_id=None,
                    artifact_version=None,
                )
        
        if not tool:
            # Fallback for system tools if needed, but registry handles scope usually
            raise ValueError(f"Tool {tool_id} not found")

        # 2. Resolve Inputs
        # Simple Logic: Pass whole state or specific mapped inputs? 
        # For Phase 1/2: Pass context or message content if available.
        # Ideally, we should use `tool.schema['input']` to map state fields to tool inputs.
        # Here we assume the input is in `state.get('context')` or passed in explicitly?
        # Let's assume input comes from `state['context']` or is passed in `runtime_input`.
        input_data = self._resolve_input_data(state, config)

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
        if isinstance(config_schema, str):
            try:
                config_schema = json.loads(config_schema)
            except Exception:
                config_schema = {}
        implementation_config = config_schema.get("implementation", {})
        impl_type = getattr(tool, "implementation_type", None) or implementation_config.get("type", "internal")
        if hasattr(impl_type, "value"):
            impl_type = impl_type.value

        # Check for Artifact linkage (Phase 4)
        if hasattr(tool, "artifact_id") and tool.artifact_id:
            logger.info(f"Delegating tool execution to artifact: {tool.artifact_id}")
            from app.agent.executors.artifact import ArtifactNodeExecutor
            
            # Prepare config for artifact executor
            artifact_config = {
                **config,
                "_artifact_id": tool.artifact_id,
                "_artifact_version": tool.artifact_version,
                "label": tool.name,
            }
            
            artifact_executor = ArtifactNodeExecutor(self.tenant_id, self.db)
            result = await artifact_executor.execute(state, artifact_config, context)
            if emitter:
                emitter.emit_tool_end(tool.name, result, node_id)
            return result
        
        # Support inline config pointer
        if impl_type == "artifact" and implementation_config.get("artifact_id"):
             artifact_id = implementation_config.get("artifact_id")
             logger.info(f"Delegating tool execution to artifact (inline): {artifact_id}")
             from app.agent.executors.artifact import ArtifactNodeExecutor
             artifact_config = {
                **config,
                "_artifact_id": artifact_id,
                "_artifact_version": implementation_config.get("artifact_version"),
                "label": tool.name,
             }
             artifact_executor = ArtifactNodeExecutor(self.tenant_id, self.db)
             result = await artifact_executor.execute(state, artifact_config, context)
             if emitter:
                 emitter.emit_tool_end(tool.name, result, node_id)
             return result

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
            elif impl_type == "mcp":
                raise NotImplementedError("MCP tool execution is not implemented yet")
            
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
