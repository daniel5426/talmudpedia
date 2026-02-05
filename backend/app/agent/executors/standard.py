import logging
import json
import re
from typing import Any, Dict, List, Optional

from app.agent.executors.base import BaseNodeExecutor, ValidationResult
from app.agent.registry import AgentOperatorRegistry, AgentOperatorSpec, AgentStateField, AgentExecutorRegistry
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from app.services.model_resolver import ModelResolver
from app.agent.core.llm_adapter import LLMProviderAdapter
from app.agent.cel_engine import evaluate_template

logger = logging.getLogger(__name__)

# =============================================================================
# Control Flow Executors
# =============================================================================

class StartNodeExecutor(BaseNodeExecutor):
    """
    Entry point executor.
    Initializes state variables from configuration.
    """
    
    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        logger.debug("Executing START node")
        
        # Initialize state variables from config
        state_vars = config.get("state_variables", [])
        input_vars = config.get("input_variables", [])
        
        initial_state = {}
        
        # Set up state variables with defaults
        for var in state_vars:
            name = var.get("name")
            default = var.get("default")
            if name:
                initial_state[name] = default
        
        # Input variables are expected to come from the user input
        # They're defined here for documentation/validation
        
        if initial_state:
            return {"state": initial_state}
        return {}


class EndNodeExecutor(BaseNodeExecutor):
    """
    Exit point executor.
    Extracts specified output from state.
    """
    
    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        logger.debug("Executing END node")
        
        output_variable = config.get("output_variable")
        output_message = config.get("output_message")
        
        result = {}
        
        if output_variable:
            # Extract from state
            state_vars = state.get("state", {})
            if output_variable in state_vars:
                result["final_output"] = state_vars[output_variable]
            elif output_variable in state:
                result["final_output"] = state[output_variable]
        
        if output_message:
            # Interpolate template with state
            try:
                interpolated = evaluate_template(output_message, state)
                result["final_output"] = interpolated
            except Exception as e:
                logger.warning(f"Failed to interpolate output message: {e}")
                result["final_output"] = output_message
        
        return result


# =============================================================================
# Reasoning Executors
# =============================================================================

class LLMNodeExecutor(BaseNodeExecutor):
    """
    Simple LLM node executor (demoted - kept for backward compatibility).
    For new workflows, use ReasoningNodeExecutor (Agent node) instead.
    """
    
    async def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        if not config.get("model_id"):
            return ValidationResult(valid=False, errors=["Missing 'model_id' in configuration"])
        return ValidationResult(valid=True)

    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        logger.debug(f"Executing LLM node with config: {config.keys()}")
        
        system_prompt = config.get("system_prompt", None)
        model_id = config.get("model_id")
        
        # Extract emitter from ContextVar (global implicit context)
        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        
        node_id = context.get("node_id", "llm_node") if context else "llm_node"
        node_name = context.get("node_name", "LLM") if context else "LLM"
        
        # 1. Resolve Model
        resolver = ModelResolver(self.db, self.tenant_id)
        try:
            provider = await resolver.resolve(model_id)
        except Exception as e:
            logger.error(f"Failed to resolve model {model_id}: {e}")
            if emitter:
                emitter.emit_error(str(e), node_id)
            raise ValueError(f"Failed to resolve model: {e}")

        # 2. Prepare Messages
        current_messages = state.get("messages", [])
        formatted_messages = self._format_messages(current_messages)
        
        logger.debug(f"LLM Exec Input Messages: {len(formatted_messages)}")

        # 3. Execute via Adapter with explicit token emission
        try:
            adapter = LLMProviderAdapter(provider)
            full_content = ""
            
            # Emit node start
            if emitter:
                emitter.emit_node_start(node_id, node_name, "llm", {"message_count": len(formatted_messages)})
            
            # Stream tokens explicitly
            try:
                reasoning_buffer = ""
                async for chunk in adapter._astream(formatted_messages, system_prompt=system_prompt):
                    token_content = chunk.message.content if hasattr(chunk, 'message') else ""
                    
                    # Handle reasoning content if supported
                    r_content = chunk.message.additional_kwargs.get("reasoning_content", "") if hasattr(chunk, 'message') else ""
                    if r_content:
                        reasoning_buffer += r_content
                        if emitter:
                            reasoning_node_id = f"{node_id}_reasoning"
                            emitter.emit_tool_start("Reasoning Process", {"message": reasoning_buffer}, reasoning_node_id)

                    if token_content:
                        full_content += token_content
                        if emitter:
                            emitter.emit_token(token_content, node_id)
            except NotImplementedError:
                logger.warning(f"Streaming not supported for model {model_id}, using non-streaming fallback")
                response = await adapter.ainvoke(formatted_messages, system_prompt=system_prompt)
                full_content = response.content
                if emitter:
                    emitter.emit_token(full_content, node_id)
            except Exception as stream_error:
                logger.warning(f"Streaming failed: {stream_error}, using non-streaming fallback")
                response = await adapter.ainvoke(formatted_messages, system_prompt=system_prompt)
                full_content = response.content
                if emitter:
                    emitter.emit_token(full_content, node_id)
            
            # Emit node end
            if emitter:
                emitter.emit_node_end(node_id, node_name, "llm", {"content_length": len(full_content)})
            
            return {
                "messages": [AIMessage(content=full_content)]
            }

        except Exception as e:
            logger.error(f"LLM execution failed: {e}")
            if emitter:
                emitter.emit_error(str(e), node_id)
            raise e
    
    def _format_messages(self, messages: List[Any]) -> List[BaseMessage]:
        """Convert messages to LangChain format."""
        formatted = []
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role")
                content = msg.get("content")
                if role == "user":
                    formatted.append(HumanMessage(content=content))
                elif role == "assistant":
                    formatted.append(AIMessage(content=content))
                elif role == "system":
                    formatted.append(SystemMessage(content=content))
                else:
                    formatted.append(HumanMessage(content=str(content)))
            elif isinstance(msg, BaseMessage):
                formatted.append(msg)
            else:
                formatted.append(HumanMessage(content=str(msg)))
        return formatted


class ReasoningNodeExecutor(BaseNodeExecutor):
    """
    Primary reasoning executor (Agent node).
    
    Enhanced LLM with:
    - Tool binding at invocation
    - Structured output (JSON mode)
    - Reasoning effort parameter
    - Chat history toggle
    
    Internal name: ReasoningNodeExecutor
    User-facing name: Agent
    """
    
    REASONING_EFFORT_MAP = {
        "low": {"temperature": 0.3, "max_tokens": 1000},
        "medium": {"temperature": 0.7, "max_tokens": 2000},
        "high": {"temperature": 0.9, "max_tokens": 4000},
    }

    _JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
    
    async def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        errors = []
        
        if not config.get("model_id"):
            errors.append("Missing 'model_id' in configuration")
        
        # Validate output schema if provided
        if config.get("output_format") == "json" and config.get("output_schema"):
            schema = config.get("output_schema")
            if not isinstance(schema, dict):
                errors.append("output_schema must be a valid JSON Schema object")
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    def _extract_json_payload(self, text: Optional[str]) -> Optional[Any]:
        if not isinstance(text, str) or not text.strip():
            return None

        trimmed = text.strip()

        # 1) Code fence blocks first
        for match in self._JSON_FENCE_RE.finditer(trimmed):
            candidate = match.group(1).strip()
            if not candidate:
                continue
            try:
                return json.loads(candidate)
            except Exception:
                continue

        # 2) Direct JSON
        if (trimmed.startswith("{") and trimmed.endswith("}")) or (
            trimmed.startswith("[") and trimmed.endswith("]")
        ):
            try:
                return json.loads(trimmed)
            except Exception:
                pass

        # 3) Embedded JSON object
        first = trimmed.find("{")
        last = trimmed.rfind("}")
        if first != -1 and last != -1 and last > first:
            candidate = trimmed[first:last + 1]
            try:
                return json.loads(candidate)
            except Exception:
                return None

        return None

    def _normalize_tool_call(self, payload: Any) -> Optional[Dict[str, Any]]:
        if payload is None:
            return None

        if isinstance(payload, list):
            for item in payload:
                normalized = self._normalize_tool_call(item)
                if normalized:
                    return normalized
            return None

        if not isinstance(payload, dict):
            return None

        candidate = payload.get("tool_call") or payload.get("toolCall") or payload
        if isinstance(candidate, list):
            for item in candidate:
                normalized = self._normalize_tool_call(item)
                if normalized:
                    return normalized
            return None
        if not isinstance(candidate, dict):
            return None

        tool_id = candidate.get("tool_id") or candidate.get("toolId") or candidate.get("toolID")
        tool_name = candidate.get("tool")

        if "input" in candidate:
            input_data = candidate.get("input")
        elif "args" in candidate:
            input_data = candidate.get("args")
        elif "parameters" in candidate:
            input_data = candidate.get("parameters")
        else:
            input_data = {}

        if input_data is None:
            input_data = {}
        if not isinstance(input_data, dict):
            input_data = {"value": input_data}

        if not tool_id and not tool_name:
            return None

        return {
            "tool_id": tool_id,
            "tool_name": tool_name,
            "input": input_data,
        }

    async def _resolve_tool_id(self, tool_call: Dict[str, Any], configured_tools: List[Any]) -> Optional[str]:
        if not configured_tools:
            return None

        configured = [str(tool) for tool in configured_tools if tool]

        tool_id = tool_call.get("tool_id")
        if tool_id:
            tool_id_str = str(tool_id)
            if tool_id_str in configured:
                return tool_id_str
            return None

        tool_name = tool_call.get("tool_name")
        if not tool_name:
            return None

        tool_name_lower = str(tool_name).lower()
        if tool_name in configured:
            return str(tool_name)

        if not self.db:
            return None

        try:
            from uuid import UUID
            from sqlalchemy import select
            from app.db.postgres.models.registry import ToolRegistry

            tool_ids = []
            for raw in configured:
                try:
                    tool_ids.append(UUID(str(raw)))
                except Exception:
                    continue

            if not tool_ids:
                return None

            result = await self.db.execute(select(ToolRegistry).where(ToolRegistry.id.in_(tool_ids)))
            tools = result.scalars().all()
        except Exception:
            return None

        for tool in tools:
            if not tool:
                continue
            name = str(tool.name).lower() if tool.name else ""
            slug = str(tool.slug).lower() if getattr(tool, "slug", None) else ""
            if tool_name_lower in (name, slug):
                return str(tool.id)

        return None

    def _build_tool_state(self, state: Dict[str, Any], tool_input: Dict[str, Any]) -> Dict[str, Any]:
        tool_state = dict(state or {})
        nested_state = dict(tool_state.get("state") or {})
        nested_state["last_agent_output"] = tool_input
        tool_state["state"] = nested_state
        tool_state["context"] = tool_input
        return tool_state

    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        logger.debug(f"Executing Agent (Reasoning) node")
        
        model_id = config.get("model_id")
        instructions = config.get("instructions", "")  # System prompt
        include_chat_history = config.get("include_chat_history", True)
        reasoning_effort = config.get("reasoning_effort", "medium")
        output_format = config.get("output_format", "text")
        output_schema = config.get("output_schema")
        tools = config.get("tools", [])  # Tool IDs to bind
        
        # Extract emitter
        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        
        node_id = context.get("node_id", "agent_node") if context else "agent_node"
        node_name = config.get("name", "Agent")
        
        # Resolve model
        resolver = ModelResolver(self.db, self.tenant_id)
        try:
            provider = await resolver.resolve(model_id)
        except Exception as e:
            logger.error(f"Failed to resolve model {model_id}: {e}")
            if emitter:
                emitter.emit_error(str(e), node_id)
            raise ValueError(f"Failed to resolve model: {e}")
        
        # Prepare messages
        if include_chat_history:
            messages = state.get("messages", [])
        else:
            # Only use the last user message
            messages = state.get("messages", [])[-1:] if state.get("messages") else []
        
        formatted_messages = self._format_messages(messages)
        
        # Apply reasoning effort settings
        effort_settings = self.REASONING_EFFORT_MAP.get(reasoning_effort, {})
        temperature = config.get("temperature", effort_settings.get("temperature", 0.7))
        max_tokens = config.get("max_tokens", effort_settings.get("max_tokens", 2000))
        
        # Interpolate instructions with state
        if instructions:
            try:
                instructions = evaluate_template(instructions, state)
            except Exception as e:
                logger.warning(f"Failed to interpolate instructions: {e}")
        
        # Execute
        try:
            adapter = LLMProviderAdapter(provider)
            full_content = ""
            
            if emitter:
                emitter.emit_node_start(node_id, node_name, "agent", {
                    "model": model_id,
                    "reasoning_effort": reasoning_effort,
                    "tools_count": len(tools)
                })
            
            # TODO: Tool binding - will be implemented when we have tool resolution
            # For now, tools are just logged
            if tools:
                logger.info(f"Agent node has {len(tools)} tools configured (binding TBD)")
            
            # Stream tokens
            try:
                async for chunk in adapter._astream(formatted_messages, system_prompt=instructions):
                    token_content = chunk.message.content if hasattr(chunk, 'message') else ""
                    if token_content:
                        full_content += token_content
                        if emitter:
                            emitter.emit_token(token_content, node_id)
            except (NotImplementedError, Exception) as e:
                logger.warning(f"Streaming failed/unsupported: {e}, using non-streaming")
                response = await adapter.ainvoke(formatted_messages, system_prompt=instructions)
                full_content = response.content
                if emitter:
                    emitter.emit_token(full_content, node_id)
            
            if emitter:
                emitter.emit_node_end(node_id, node_name, "agent", {"content_length": len(full_content)})
            
            # Handle structured output
            result_content = full_content
            if output_format == "json":
                try:
                    result_content = json.loads(full_content)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON output, returning raw string")

            state_update = {
                "messages": [AIMessage(content=full_content)],
                "state": {
                    **(state.get("state", {})),
                    "last_agent_output": result_content
                }
            }
            if config.get("write_output_to_context") and isinstance(result_content, dict):
                state_update["context"] = result_content

            tool_output_payload = None
            if tools:
                tool_payload = self._extract_json_payload(full_content)
                tool_call = self._normalize_tool_call(tool_payload)
                if not tool_call and isinstance(result_content, dict):
                    tool_call = self._normalize_tool_call(result_content)

                if tool_call:
                    resolved_tool_id = await self._resolve_tool_id(tool_call, tools)
                    if resolved_tool_id:
                        tool_input = tool_call.get("input") or {}
                        if not isinstance(tool_input, dict):
                            tool_input = {"value": tool_input}
                        tool_state = self._build_tool_state(state, tool_input)

                        from app.agent.executors.tool import ToolNodeExecutor
                        tool_executor = ToolNodeExecutor(self.tenant_id, self.db)
                        tool_context = {
                            "node_id": f"{node_id}::tool::{resolved_tool_id}",
                            "node_name": f"Tool:{resolved_tool_id}",
                        }
                        tool_result = await tool_executor.execute(
                            tool_state,
                            {"tool_id": resolved_tool_id},
                            tool_context,
                        )

                        if isinstance(tool_result, dict):
                            if "tool_outputs" in tool_result:
                                state_update["tool_outputs"] = tool_result.get("tool_outputs")
                            if "context" in tool_result:
                                state_update["context"] = tool_result.get("context")
                            tool_output_payload = tool_result.get("context")
                            if tool_output_payload is None and tool_result.get("tool_outputs"):
                                tool_outputs = tool_result.get("tool_outputs")
                                if isinstance(tool_outputs, list) and tool_outputs:
                                    tool_output_payload = tool_outputs[0]
                        else:
                            tool_output_payload = tool_result

                        if tool_output_payload is not None:
                            state_update["state"]["last_agent_output"] = tool_output_payload

            return state_update

        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            if emitter:
                emitter.emit_error(str(e), node_id)
            raise e
    
    def _format_messages(self, messages: List[Any]) -> List[BaseMessage]:
        """Convert messages to LangChain format."""
        formatted = []
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role")
                content = msg.get("content")
                if role == "user":
                    formatted.append(HumanMessage(content=content))
                elif role == "assistant":
                    formatted.append(AIMessage(content=content))
                elif role == "system":
                    formatted.append(SystemMessage(content=content))
                else:
                    formatted.append(HumanMessage(content=str(content)))
            elif isinstance(msg, BaseMessage):
                formatted.append(msg)
            else:
                formatted.append(HumanMessage(content=str(msg)))
        return formatted


# =============================================================================
# Registration
# =============================================================================

def register_standard_operators():
    """Register all standard agent operators."""
    
    # =========================================================================
    # Control Flow
    # =========================================================================
    
    # Start Node
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="start",
        category="control",
        display_name="Start",
        description="Entry point for the agent. Initialize variables here.",
        reads=[],
        writes=[AgentStateField.MESSAGE_HISTORY, AgentStateField.STATE_VARIABLES],
        ui={
            "icon": "Play",
            "color": "#6b7280",
            "inputType": "any",
            "outputType": "message",
            "configFields": [
                {"name": "input_variables", "label": "Input Variables", "fieldType": "variable_list", "required": False, 
                 "description": "Define expected input variables with types"},
                {"name": "state_variables", "label": "State Variables", "fieldType": "variable_list", "required": False,
                 "description": "Initialize persistent state variables with defaults"}
            ]
        }
    ))
    AgentExecutorRegistry.register("start", StartNodeExecutor)

    # End Node
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="end",
        category="control",
        display_name="End",
        description="Exit point. Specify what to return.",
        reads=[AgentStateField.MESSAGE_HISTORY, AgentStateField.STATE_VARIABLES, AgentStateField.FINAL_OUTPUT],
        writes=[AgentStateField.FINAL_OUTPUT],
        ui={
            "icon": "Square",
            "color": "#6b7280",
            "inputType": "any",
            "outputType": "any",
            "configFields": [
                {"name": "output_variable", "label": "Output Variable", "fieldType": "variable_selector", "required": False,
                 "description": "Select a state variable to return"},
                {"name": "output_message", "label": "Output Message", "fieldType": "template_string", "required": False,
                 "description": "Template message with {{ variable }} interpolation"}
            ]
        }
    ))
    AgentExecutorRegistry.register("end", EndNodeExecutor)

    # =========================================================================
    # Reasoning
    # =========================================================================
    
    # Agent Node (Primary - ReasoningNodeExecutor)
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="agent",
        category="reasoning",
        display_name="Agent",
        description="Primary reasoning node with tools and structured output",
        reads=[AgentStateField.MESSAGE_HISTORY, AgentStateField.STATE_VARIABLES, AgentStateField.MEMORY],
        writes=[AgentStateField.MESSAGE_HISTORY, AgentStateField.STATE_VARIABLES],
        config_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "title": "Name"},
                "model_id": {"type": "string", "title": "Model"},
                "instructions": {"type": "string", "title": "Instructions"},
                "include_chat_history": {"type": "boolean", "title": "Include Chat History", "default": True},
                "reasoning_effort": {"type": "string", "title": "Reasoning Effort", "enum": ["low", "medium", "high"]},
                "output_format": {"type": "string", "title": "Output Format", "enum": ["text", "json"]},
                "tools": {"type": "array", "items": {"type": "string"}, "title": "Tools"}
            },
            "required": ["model_id"]
        },
        ui={
            "icon": "Bot",
            "color": "#8b5cf6",
            "inputType": "message",
            "outputType": "message",
            "configFields": [
                {"name": "name", "label": "Name", "fieldType": "string", "required": False, "description": "Agent display name"},
                {"name": "model_id", "label": "Model", "fieldType": "model", "required": True, "description": "Select a chat model"},
                {"name": "instructions", "label": "Instructions", "fieldType": "text", "required": False, "description": "System prompt with {{ variable }} support"},
                {"name": "include_chat_history", "label": "Include Chat History", "fieldType": "boolean", "required": False, "default": True},
                {"name": "reasoning_effort", "label": "Reasoning Effort", "fieldType": "select", "required": False, "default": "medium",
                 "options": [
                    {"value": "low", "label": "Low"},
                    {"value": "medium", "label": "Medium"},
                    {"value": "high", "label": "High"}
                 ]},
                {"name": "output_format", "label": "Output Format", "fieldType": "select", "required": False, "default": "text",
                 "options": [
                    {"value": "text", "label": "Text"},
                    {"value": "json", "label": "JSON"}
                 ]},
                {"name": "tools", "label": "Tools", "fieldType": "tool_list", "required": False, "description": "Attach tools to the agent"},
                {"name": "temperature", "label": "Temperature", "fieldType": "number", "required": False, "description": "Override reasoning effort temperature"},
            ]
        }
    ))
    AgentExecutorRegistry.register("agent", ReasoningNodeExecutor)

    # Classify Node
    from app.agent.executors.classify_executor import ClassifyNodeExecutor
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="classify",
        category="reasoning",
        display_name="Classify",
        description="Classify input into categories using LLM",
        reads=[AgentStateField.MESSAGE_HISTORY, AgentStateField.STATE_VARIABLES],
        writes=[AgentStateField.ROUTING_KEY, AgentStateField.BRANCH_TAKEN],
        ui={
            "icon": "ListFilter", # Will need to add this icon map in frontend
            "color": "#8b5cf6",
            "inputType": "message",
            "outputType": "decision",
            "dynamicHandles": True,
            "configFields": [
                {"name": "name", "label": "Name", "fieldType": "string", "required": False},
                {"name": "model_id", "label": "Model", "fieldType": "model", "required": True, "description": "Model used for classification"},
                {"name": "instructions", "label": "Instructions", "fieldType": "text", "required": False, "description": "Additional context for classification"},
                {"name": "categories", "label": "Categories", "fieldType": "category_list", "required": True, "description": "Define classification categories"}
            ]
        }
    ))
    AgentExecutorRegistry.register("classify", ClassifyNodeExecutor)

    # LLM Node (Demoted - Simple completion)
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="llm",
        category="reasoning",
        display_name="LLM (Simple)",
        description="Simple LLM completion. Use Agent for complex workflows.",
        reads=[AgentStateField.MESSAGE_HISTORY, AgentStateField.MEMORY],
        writes=[AgentStateField.MESSAGE_HISTORY, AgentStateField.ROUTING_KEY],
        config_schema={
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "title": "Model"},
                "system_prompt": {"type": "string", "title": "System Prompt"},
                "temperature": {"type": "number", "title": "Temperature", "default": 0.7}
            },
            "required": ["model_id"]
        },
        ui={
            "icon": "Brain",
            "color": "#a78bfa",  # Lighter purple to indicate secondary
            "inputType": "message",
            "outputType": "message",
            "configFields": [
                {"name": "model_id", "label": "Model", "fieldType": "model", "required": True, "description": "Select a chat model"},
                {"name": "system_prompt", "label": "System Prompt", "fieldType": "text", "required": False, "description": "Instructions for the LLM"},
                {"name": "temperature", "label": "Temperature", "fieldType": "number", "required": False, "default": 0.7, "description": "Creativity (0-1)"},
            ]
        }
    ))
    AgentExecutorRegistry.register("llm", LLMNodeExecutor)

    # =========================================================================
    # Data Operators
    # =========================================================================
    
    from app.agent.executors.data import TransformNodeExecutor, SetStateNodeExecutor
    
    # Transform Node
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="transform",
        category="data",
        display_name="Transform",
        description="Reshape data using expressions",
        reads=[AgentStateField.STATE_VARIABLES, AgentStateField.CONTEXT],
        writes=[AgentStateField.STATE_VARIABLES, AgentStateField.TRANSFORM_OUTPUT],
        ui={
            "icon": "Sparkles",
            "color": "#06b6d4",
            "inputType": "any",
            "outputType": "any",
            "configFields": [
                {"name": "name", "label": "Name", "fieldType": "string", "required": False},
                {"name": "mode", "label": "Mode", "fieldType": "select", "required": False, "default": "expressions",
                 "options": [
                    {"value": "expressions", "label": "Expressions (CEL)"},
                    {"value": "object", "label": "Literal Values"}
                 ]},
                {"name": "mappings", "label": "Mappings", "fieldType": "mapping_list", "required": True,
                 "description": "Key-value mappings (key = CEL expression in expression mode)"}
            ]
        }
    ))
    AgentExecutorRegistry.register("transform", TransformNodeExecutor)
    
    # Set State Node
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="set_state",
        category="data",
        display_name="Set State",
        description="Explicitly set state variables",
        reads=[AgentStateField.STATE_VARIABLES],
        writes=[AgentStateField.STATE_VARIABLES],
        ui={
            "icon": "Database",
            "color": "#06b6d4",
            "inputType": "any",
            "outputType": "any",
            "configFields": [
                {"name": "name", "label": "Name", "fieldType": "string", "required": False},
                {"name": "assignments", "label": "Assignments", "fieldType": "assignment_list", "required": True,
                 "description": "Variable assignments (value can be CEL expression)"},
                {"name": "is_expression", "label": "Values are Expressions", "fieldType": "boolean", "required": False, "default": True}
            ]
        }
    ))
    AgentExecutorRegistry.register("set_state", SetStateNodeExecutor)

    # =========================================================================
    # Logic Operators
    # =========================================================================
    
    from app.agent.executors.logic import IfElseNodeExecutor, WhileNodeExecutor, ConditionalNodeExecutor, ParallelNodeExecutor
    
    # If/Else Node (New)
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="if_else",
        category="logic",
        display_name="If/Else",
        description="Multi-condition branching with CEL expressions",
        reads=[AgentStateField.STATE_VARIABLES, AgentStateField.MESSAGE_HISTORY],
        writes=[AgentStateField.ROUTING_KEY, AgentStateField.BRANCH_TAKEN],
        ui={
            "icon": "GitBranch",
            "color": "#f59e0b",
            "inputType": "any",
            "outputType": "decision",
            "dynamicHandles": True,  # Handles are generated from conditions
            "configFields": [
                {"name": "conditions", "label": "Conditions", "fieldType": "condition_list", "required": False,
                 "description": "Conditions evaluated in order. First match wins."}
            ]
        }
    ))
    AgentExecutorRegistry.register("if_else", IfElseNodeExecutor)
    
    # While Node (New)
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="while",
        category="logic",
        display_name="While",
        description="Loop while condition is true",
        reads=[AgentStateField.STATE_VARIABLES, AgentStateField.LOOP_COUNTERS],
        writes=[AgentStateField.ROUTING_KEY, AgentStateField.LOOP_COUNTERS],
        ui={
            "icon": "RefreshCw",
            "color": "#f59e0b",
            "inputType": "any",
            "outputType": "decision",
            "staticHandles": ["loop", "exit"],  # Fixed output handles
            "configFields": [
                {"name": "name", "label": "Name", "fieldType": "string", "required": False},
                {"name": "condition", "label": "Condition", "fieldType": "expression", "required": True,
                 "description": "CEL expression - loop while true"},
                {"name": "max_iterations", "label": "Max Iterations", "fieldType": "number", "required": False, "default": 10,
                 "description": "Safety limit to prevent infinite loops"}
            ]
        }
    ))
    AgentExecutorRegistry.register("while", WhileNodeExecutor)

    # Conditional (Legacy - kept for backward compatibility)
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="conditional",
        category="logic",
        display_name="Conditional (Legacy)",
        description="Legacy conditional. Use If/Else for new workflows.",
        reads=[AgentStateField.MESSAGE_HISTORY, AgentStateField.ROUTING_KEY],
        writes=[AgentStateField.ROUTING_KEY, AgentStateField.BRANCH_TAKEN],
        ui={
            "icon": "GitBranch",
            "color": "#d97706",  # Darker orange to indicate legacy
            "inputType": "any",
            "outputType": "decision",
            "configFields": [
                {"name": "condition_type", "label": "Condition Type", "fieldType": "select", "required": True,
                 "options": [
                    {"value": "llm_decision", "label": "LLM Decision"},
                    {"value": "contains", "label": "Output Contains"},
                    {"value": "regex", "label": "Regex Match"},
                    {"value": "cel", "label": "CEL Expression"}
                 ], "description": "How to evaluate the condition"},
                {"name": "condition_value", "label": "Condition Value", "fieldType": "string", "required": False, "description": "Value to check against"}
            ]
        }
    ))
    AgentExecutorRegistry.register("conditional", ConditionalNodeExecutor)

    # Parallel
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="parallel",
        category="logic",
        display_name="Parallel",
        description="Execute branches in parallel",
        reads=[],
        writes=[],
        ui={
            "icon": "GitFork",
            "color": "#f59e0b",
            "inputType": "any",
            "outputType": "context",
            "configFields": [
                {"name": "wait_all", "label": "Wait for All", "fieldType": "boolean", "required": False, "default": True, "description": "Wait for all branches to complete"}
            ]
        }
    ))
    AgentExecutorRegistry.register("parallel", ParallelNodeExecutor)

    # =========================================================================
    # Actions
    # =========================================================================
    
    from app.agent.executors.tool import ToolNodeExecutor
    from app.agent.executors.tool import ToolNodeExecutor
    from app.agent.executors.rag import RetrievalNodeExecutor, VectorSearchNodeExecutor

    # Tool
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="tool",
        category="action",
        display_name="Tool",
        description="Invoke a registered tool",
        reads=[AgentStateField.STATE_VARIABLES],
        writes=[AgentStateField.OBSERVATIONS, AgentStateField.CONTEXT],
        ui={
            "icon": "Wrench",
            "color": "#3b82f6",
            "inputType": "context",
            "outputType": "result",
            "configFields": [
                {"name": "tool_id", "label": "Tool", "fieldType": "tool", "required": True, "description": "Select a tool to invoke"}
            ]
        }
    ))
    AgentExecutorRegistry.register("tool", ToolNodeExecutor)

    # Retrieval (Pipeline)
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="rag", # Keeping type="rag" for backward compatibility in graph, but UI shows "Retrieval"
        category="action",
        display_name="Retrieval",
        description="Execute a Retrieval Pipeline",
        reads=[AgentStateField.MESSAGE_HISTORY, AgentStateField.STATE_VARIABLES],
        writes=[AgentStateField.CONTEXT],
        ui={
            "icon": "Search",
            "color": "#3b82f6",
            "inputType": "message",
            "outputType": "context",
            "configFields": [
                {"name": "pipeline_id", "label": "Retrieval Pipeline", "fieldType": "retrieval_pipeline_select", "required": True, "description": "Select a Retrieval Pipeline"},
                {"name": "query", "label": "Query Template", "fieldType": "template_string", "required": False, 
                 "description": "Query with {{ variable }} interpolation. Leave empty to use last message."},
                {"name": "top_k", "label": "Max Results", "fieldType": "number", "required": False, "default": 10, "description": "Number of results to retrieve"}
            ]
        }
    ))
    AgentExecutorRegistry.register("rag", RetrievalNodeExecutor)
    
    # Vector Search (Direct Store)
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="vector_search",
        category="action",
        display_name="Vector Search",
        description="Search a Knowledge Store directly",
        reads=[AgentStateField.MESSAGE_HISTORY, AgentStateField.STATE_VARIABLES],
        writes=[AgentStateField.CONTEXT],
        ui={
            "icon": "Database",
            "color": "#3b82f6",
            "inputType": "message",
            "outputType": "context",
            "configFields": [
                {"name": "knowledge_store_id", "label": "Knowledge Store", "fieldType": "knowledge_store_select", "required": True, "description": "Select a Knowledge Store"},
                {"name": "query", "label": "Query Template", "fieldType": "template_string", "required": False, 
                 "description": "Query with {{ variable }} interpolation. Leave empty to use last message."},
                {"name": "top_k", "label": "Max Results", "fieldType": "number", "required": False, "default": 10, "description": "Number of results to retrieve"}
            ]
        }
    ))
    AgentExecutorRegistry.register("vector_search", VectorSearchNodeExecutor)

    # =========================================================================
    # Interaction
    # =========================================================================
    
    from app.agent.executors.interaction import HumanInputNodeExecutor

    # User Approval (renamed from Human Input)
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="user_approval",
        category="interaction",
        display_name="User Approval",
        description="Pause for user approval or rejection",
        reads=[AgentStateField.STATE_VARIABLES],
        writes=[AgentStateField.MESSAGE_HISTORY, AgentStateField.APPROVAL_STATUS, AgentStateField.ROUTING_KEY],
        ui={
            "icon": "UserCheck",
            "color": "#10b981",
            "inputType": "any",
            "outputType": "decision",
            "staticHandles": ["approve", "reject"],
            "configFields": [
                {"name": "name", "label": "Name", "fieldType": "string", "required": False},
                {"name": "message", "label": "Message", "fieldType": "template_string", "required": False, 
                 "description": "Message shown to user with {{ variable }} support"},
                {"name": "timeout_seconds", "label": "Timeout (seconds)", "fieldType": "number", "required": False, "default": 300},
                {"name": "require_comment", "label": "Require Comment", "fieldType": "boolean", "required": False, "default": False}
            ]
        }
    ))
    AgentExecutorRegistry.register("user_approval", HumanInputNodeExecutor)
    
    # Human Input (Legacy)
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="human_input",
        category="interaction",
        display_name="Human Input (Legacy)",
        description="Legacy human input. Use User Approval for new workflows.",
        reads=[],
        writes=[AgentStateField.MESSAGE_HISTORY],
        ui={
            "icon": "UserCheck",
            "color": "#059669",  # Darker green to indicate legacy
            "inputType": "any",
            "outputType": "message",
            "configFields": [
                {"name": "prompt", "label": "Prompt", "fieldType": "text", "required": False, "description": "Message shown to the human reviewer"},
                {"name": "timeout_seconds", "label": "Timeout (seconds)", "fieldType": "number", "required": False, "default": 300, "description": "Max wait time"}
            ]
        }
    ))
    AgentExecutorRegistry.register("human_input", HumanInputNodeExecutor)
    
    # =========================================================================
    # Artifacts (Dynamic Registration)
    # =========================================================================
    try:
        _register_artifact_operators()
    except Exception as e:
        logger.error(f"Failed to register artifact operators: {e}")

    logger.info("Registered all standard agent operators")


def _register_artifact_operators():
    """Register all agent-scoped artifacts as operators."""
    from app.services.artifact_registry import get_artifact_registry
    from app.agent.executors.artifact import ArtifactNodeExecutor
    
    registry = get_artifact_registry()
    # Refresh to ensure we have latest artifacts
    registry.refresh()
    
    agent_artifacts = registry.get_agent_artifacts()
    
    for artifact_spec in agent_artifacts:
        try:
            operator_spec = artifact_spec.to_agent_operator_spec()
            AgentOperatorRegistry.register(operator_spec)
            AgentExecutorRegistry.register(operator_spec.type, ArtifactNodeExecutor)
            logger.info(f"Registered artifact operator: {operator_spec.type}")
        except Exception as e:
            logger.error(f"Failed to register artifact {artifact_spec.artifact_id}: {e}")
            
    logger.info(f"Registered {len(agent_artifacts)} artifact operators for Agent Builder")
 
