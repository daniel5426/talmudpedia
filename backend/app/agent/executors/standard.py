import logging
from typing import Any, Dict, List

from app.agent.executors.base import BaseNodeExecutor, ValidationResult
from app.agent.registry import AgentOperatorRegistry, AgentOperatorSpec, AgentStateField, AgentExecutorRegistry
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from app.services.model_resolver import ModelResolver
from app.agent.core.llm_adapter import LLMProviderAdapter

logger = logging.getLogger(__name__)

# =============================================================================
# Control Flow Executors
# =============================================================================

class StartNodeExecutor(BaseNodeExecutor):
    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        # Pass-through - Start node just initializes the graph
        logger.debug("Executing START node")
        return {}

class EndNodeExecutor(BaseNodeExecutor):
    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        # Pass-through - End node marks completion
        logger.debug("Executing END node")
        return {}

# =============================================================================
# Reasoning Executors
# =============================================================================

class LLMNodeExecutor(BaseNodeExecutor):
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
        formatted_messages = []
        
        for msg in current_messages:
            if isinstance(msg, dict):
                role = msg.get("role")
                content = msg.get("content")
                if role == "user":
                    formatted_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    formatted_messages.append(AIMessage(content=content))
                elif role == "system":
                    formatted_messages.append(SystemMessage(content=content))
                else:
                    formatted_messages.append(HumanMessage(content=str(content)))
            elif isinstance(msg, BaseMessage):
                formatted_messages.append(msg)
            else:
                formatted_messages.append(HumanMessage(content=str(msg)))
        
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
                    
                    # Handle reasoning content if supported by adapter/model
                    r_content = chunk.message.additional_kwargs.get("reasoning_content", "") if hasattr(chunk, 'message') else ""
                    if r_content:
                        reasoning_buffer += r_content
                        # Emit reasoning update as a tool start event with specific name
                        if emitter:
                            # Use a stable node_id for the reasoning step so it merges correctly in frontend
                            reasoning_node_id = f"{node_id}_reasoning"
                            emitter.emit_tool_start("Reasoning Process", {"message": reasoning_buffer}, reasoning_node_id)

                    if token_content:
                        full_content += token_content
                        # Explicitly emit token event
                        if emitter:
                            emitter.emit_token(token_content, node_id)
            except NotImplementedError:
                # Non-streaming fallback
                logger.warning(f"Streaming not supported for model {model_id}, using non-streaming fallback")
                response = await adapter.ainvoke(formatted_messages, system_prompt=system_prompt)
                full_content = response.content
                # Emit entire content as single token batch
                if emitter:
                    emitter.emit_token(full_content, node_id)
            except Exception as stream_error:
                # If streaming fails, fallback to ainvoke
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

# =============================================================================
# Registration
# =============================================================================

def register_standard_operators():
    # Start Node
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="start",
        category="control",
        display_name="Start",
        description="Entry point for the agent",
        reads=[],
        writes=[AgentStateField.MESSAGE_HISTORY],
        ui={
            "icon": "Play",
            "color": "#6b7280",
            "inputType": "any",
            "outputType": "message",
            "configFields": []
        }
    ))
    AgentExecutorRegistry.register("start", StartNodeExecutor)

    # End Node
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="end",
        category="control",
        display_name="End",
        description="Exit point for the agent",
        reads=[AgentStateField.MESSAGE_HISTORY, AgentStateField.FINAL_OUTPUT],
        writes=[],
        ui={
            "icon": "Square",
            "color": "#6b7280",
            "inputType": "any",
            "outputType": "any",
            "configFields": []
        }
    ))
    AgentExecutorRegistry.register("end", EndNodeExecutor)

    # LLM Node
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="llm",
        category="reasoning",
        display_name="LLM",
        description="Call a language model for reasoning",
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
            "color": "#8b5cf6",
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

    # Register Real Executors
    from app.agent.executors.tool import ToolNodeExecutor
    from app.agent.executors.rag import RAGNodeExecutor
    from app.agent.executors.logic import ConditionalNodeExecutor, ParallelNodeExecutor
    from app.agent.executors.interaction import HumanInputNodeExecutor

    # Tool
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="tool", category="action", display_name="Tool", description="Invoke a registered tool",
        reads=[], writes=[AgentStateField.OBSERVATIONS], # And maybe context
        ui={
            "icon": "Wrench", "color": "#3b82f6", "inputType": "context", "outputType": "result",
            "configFields": [
                 {"name": "tool_id", "label": "Tool", "fieldType": "tool", "required": True, "description": "Select a tool to invoke"}
            ]
        }
    ))
    AgentExecutorRegistry.register("tool", ToolNodeExecutor)

    # RAG
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="rag", category="action", display_name="RAG Lookup", description="Retrieve context from knowledge base",
        reads=[AgentStateField.MESSAGE_HISTORY], writes=[AgentStateField.CONTEXT],
         ui={
            "icon": "Search", "color": "#3b82f6", "inputType": "message", "outputType": "context",
            "configFields": [
                 {"name": "pipeline_id", "label": "RAG Pipeline", "fieldType": "rag", "required": True, "description": "Select a RAG pipeline"},
                 {"name": "top_k", "label": "Results", "fieldType": "number", "required": False, "default": 5, "description": "Number of results to retrieve"}
            ]
        }
    ))
    AgentExecutorRegistry.register("rag", RAGNodeExecutor)

    # Conditional
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="conditional", category="logic", display_name="Conditional", description="Branch based on logic",
        reads=[AgentStateField.MESSAGE_HISTORY, AgentStateField.ROUTING_KEY], writes=[AgentStateField.ROUTING_KEY],
         ui={
            "icon": "GitBranch", "color": "#f59e0b", "inputType": "any", "outputType": "decision",
            "configFields": [
                {"name": "condition_type", "label": "Condition Type", "fieldType": "select", "required": True,
                 "options": [
                    {"value": "llm_decision", "label": "LLM Decision"},
                    {"value": "contains", "label": "Output Contains"},
                    {"value": "regex", "label": "Regex Match"}
                 ], "description": "How to evaluate the condition"},
                {"name": "condition_value", "label": "Condition Value", "fieldType": "string", "required": False, "description": "Value to check against"}
            ]
        }
    ))
    AgentExecutorRegistry.register("conditional", ConditionalNodeExecutor)

    # Parallel
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="parallel", category="logic", display_name="Parallel", description="Execute branches in parallel",
        reads=[], writes=[],
         ui={
            "icon": "GitFork", "color": "#f59e0b", "inputType": "any", "outputType": "context",
            "configFields": [
                 {"name": "wait_all", "label": "Wait for All", "fieldType": "boolean", "required": False, "default": True, "description": "Wait for all branches to complete"}
            ]
        }
    ))
    AgentExecutorRegistry.register("parallel", ParallelNodeExecutor)

    # Human Input
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="human_input", category="interaction", display_name="Human Input", description="Pause for human input",
        reads=[], writes=[AgentStateField.MESSAGE_HISTORY],
         ui={
            "icon": "UserCheck", "color": "#10b981", "inputType": "any", "outputType": "message",
            "configFields": [
                 {"name": "prompt", "label": "Prompt", "fieldType": "text", "required": False, "description": "Message shown to the human reviewer"},
                 {"name": "timeout_seconds", "label": "Timeout (seconds)", "fieldType": "number", "required": False, "default": 300, "description": "Max wait time"}
            ]
        }
    ))
    AgentExecutorRegistry.register("human_input", HumanInputNodeExecutor) 
