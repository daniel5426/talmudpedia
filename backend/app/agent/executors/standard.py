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
        
        # 1. Resolve Model
        resolver = ModelResolver(self.db, self.tenant_id)
        try:
            provider = await resolver.resolve(model_id)
        except Exception as e:
            logger.error(f"Failed to resolve model {model_id}: {e}")
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

        # 3. Execute via Adapter
        try:
            adapter = LLMProviderAdapter(provider)
            
            # Pass execution config to adapter to enable streaming callbacks
            # The 'config' arg here comes from LangGraph's runtime config which contains callbacks
            runtime_config = context.get("langgraph_config", {}) if context else {}
            
            response = await adapter.ainvoke(
                formatted_messages, 
                config=runtime_config,
                system_prompt=system_prompt
            )
            
            return {
                "messages": [response]
                # In the future, we might parse reasoning steps here and return "observations" or "routing_key"
            }
        except Exception as e:
            logger.error(f"LLM execution failed: {e}")
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
