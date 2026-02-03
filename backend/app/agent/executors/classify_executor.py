import logging
from typing import Any, Dict, List
from langchain_core.messages import SystemMessage
from app.agent.executors.base import BaseNodeExecutor, ValidationResult
from app.agent.execution.emitter import active_emitter
from app.agent.core.llm_adapter import LLMProviderAdapter
logger = logging.getLogger(__name__)



class ClassifyNodeExecutor(BaseNodeExecutor):
    """
    Executor for Classify node.
    Uses an LLM to classify the state into one of the defined categories.
    """
    
    async def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        errors = []
        if not config.get("model_id"):
            errors.append("Missing 'model_id'")
        
        categories = config.get("categories", [])
        if not categories or len(categories) < 2:
            errors.append("Must have at least 2 categories")
            
        return ValidationResult(valid=len(errors) == 0, errors=errors)

    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        logger.debug("Executing Classify node")
        
        node_id = context.get("node_id", "classify") if context else "classify"
        categories = config.get("categories", [])
        model_id = config.get("model_id")
        instructions = config.get("instructions", "Classify the input.")
        
        # 1. Construct Classification Prompt
        category_lines = []
        for cat in categories:
            name = cat.get("name")
            desc = cat.get("description", "")
            category_lines.append(f"- {name}: {desc}")
            
        prompt = f"""{instructions}

Available Categories:
{chr(10).join(category_lines)}

Based on the context, determine the most appropriate category.
Respond ONLY with the category name. Do not include any other text."""

        # 2. Add System Prompt to messages
        messages = state.get("messages", [])
        formatted_messages = self._format_messages(messages)
        formatted_messages.append(SystemMessage(content=prompt))
        
        # 3. Call LLM (using parent logic for resolution/adapter)
        # We reuse the specific LLM call logic but enforce text output
        
        resolver = ModelResolver(self.db, self.tenant_id)
        provider = await resolver.resolve(model_id)
        adapter = LLMProviderAdapter(provider)
        
        # Emit reasoning/start
        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        if emitter:
             emitter.emit_node_start(node_id, config.get("name", "Classify"), "classify", {"categories": len(categories)})

        response_content = ""
        try:
             # Non-streaming for classification is usually safer/faster
             response = await adapter.ainvoke(formatted_messages)
             response_content = response.content.strip()
             
             # Basic cleanup (remove quotes or periods if model adds them)
             response_content = response_content.replace('"', '').replace("'", "").rstrip(".")
             
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            if emitter:
                emitter.emit_error(str(e), node_id)
            raise e
            
        if emitter:
            emitter.emit_node_end(node_id, config.get("name", "Classify"), "classify", {"selected": response_content})

        # 4. Match result to category
        selected_category = "else" # Default
        for cat in categories:
            if cat.get("name") == response_content:
                selected_category = response_content
                break
                
        # If exact match failed, try case-insensitive
        if selected_category == "else":
             for cat in categories:
                if cat.get("name").lower() == response_content.lower():
                    selected_category = cat.get("name")
                    break
        
        logger.info(f"Classify node '{node_id}' selected: {selected_category}")
        
        return {
            "next": selected_category,
            "branch_taken": selected_category,
            "classification_result": response_content
        }

    def get_output_handles(self, config: Dict[str, Any]) -> List[str]:
        categories = config.get("categories", [])
        return [c.get("name") for c in categories]
