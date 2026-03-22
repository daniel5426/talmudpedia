import logging
from typing import Any, Dict, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from app.agent.executors.base import BaseNodeExecutor, ValidationResult
from app.agent.cel_engine import evaluate_template
from app.agent.graph.contracts import normalize_value_ref, resolve_runtime_value_ref
from app.agent.core.llm_adapter import LLMProviderAdapter
from app.services.model_resolver import ModelResolver
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
        normalized_categories = []
        for idx, category in enumerate(categories):
            if not isinstance(category, dict):
                continue
            name = str(category.get("name") or "").strip() or f"category_{idx}"
            description = str(category.get("description", ""))
            if description:
                try:
                    description = evaluate_template(description, state)
                except Exception as exc:
                    logger.warning(f"Failed to interpolate classify category description: {exc}")
            normalized_categories.append(
                {
                    "name": name,
                    "description": description,
                }
            )
        model_id = config.get("model_id")
        instructions = config.get("instructions", "Classify the input.")
        if instructions:
            try:
                instructions = evaluate_template(instructions, state)
            except Exception as exc:
                logger.warning(f"Failed to interpolate classify instructions: {exc}")

        source_text = None
        if isinstance(config.get("input_source"), dict):
            source_value = resolve_runtime_value_ref(state=state, value_ref=normalize_value_ref(config.get("input_source")))
            if source_value is not None:
                source_text = source_value if isinstance(source_value, str) else str(source_value)
        
        # 1. Construct Classification Prompt
        category_lines = []
        for cat in normalized_categories:
            name = cat["name"]
            desc = cat.get("description", "")
            category_lines.append(f"- {name}: {desc}")
            
        prompt = f"""{instructions}

Available Categories:
{chr(10).join(category_lines)}

Input To Classify:
{source_text or ""}

Based on the context, determine the most appropriate category.
Respond ONLY with the category name. Do not include any other text."""

        # 2. Add System Prompt to messages
        messages = state.get("messages", [])
        formatted_messages = self._format_messages(messages)
        formatted_messages.append(SystemMessage(content=prompt))
        
        # 3. Call LLM (using resolver + adapter)
        resolver = ModelResolver(self.db, self.tenant_id)
        provider = await resolver.resolve(model_id)
        adapter = LLMProviderAdapter(provider)
        
        # Emit reasoning/start
        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        if emitter:
            emitter.emit_node_start(node_id, config.get("name", "Classify"), "classify", {"categories": len(normalized_categories)})

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
        normalized_response = response_content.strip().lower()
        for cat in normalized_categories:
            if cat["name"].lower() == normalized_response:
                selected_category = cat["name"]
                break
        
        logger.info(f"Classify node '{node_id}' selected: {selected_category}")
        
        return {
            "next": selected_category,
            "branch_taken": selected_category,
            "classification_result": response_content
        }

    def get_output_handles(self, config: Dict[str, Any]) -> List[str]:
        categories = config.get("categories", [])
        handles = []
        for idx, category in enumerate(categories):
            if not isinstance(category, dict):
                continue
            handles.append(str(category.get("name") or "").strip() or f"category_{idx}")
        return handles

    def _format_messages(self, messages: List[Any]) -> List[BaseMessage]:
        formatted: List[BaseMessage] = []
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
