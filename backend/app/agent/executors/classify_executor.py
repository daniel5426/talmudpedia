import logging
from typing import Any, Dict, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from app.agent.executors.base import BaseNodeExecutor, ValidationResult
from app.agent.cel_engine import evaluate_template
from app.agent.graph.contracts import normalize_value_ref, resolve_runtime_value_ref
from app.agent.core.llm_adapter import LLMProviderAdapter
from app.services.model_resolver import ModelResolver
from app.services.resource_policy_service import ResourcePolicySnapshot
logger = logging.getLogger(__name__)


def _policy_snapshot_from_state(state: Dict[str, Any]) -> ResourcePolicySnapshot | None:
    if not isinstance(state, dict):
        return None
    context = state.get("context")
    if not isinstance(context, dict):
        nested_state = state.get("state")
        if isinstance(nested_state, dict):
            context = nested_state.get("context")
    if not isinstance(context, dict):
        return None
    return ResourcePolicySnapshot.from_payload(context.get("resource_policy_snapshot"))



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
            category_id = str(category.get("id") or "").strip() or name or f"category_{idx}"
            description = str(category.get("description", ""))
            if description:
                try:
                    description = evaluate_template(description, state)
                except Exception as exc:
                    logger.warning(f"Failed to interpolate classify category description: {exc}")
            normalized_categories.append(
                {
                    "id": category_id,
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
        if not source_text:
            workflow_input = state.get("workflow_input") if isinstance(state.get("workflow_input"), dict) else {}
            if workflow_input:
                for key in ("text", "input_as_text"):
                    raw = workflow_input.get(key)
                    if raw not in (None, ""):
                        source_text = raw if isinstance(raw, str) else str(raw)
                        break
        if not source_text:
            messages = state.get("messages", [])
            for message in reversed(messages if isinstance(messages, list) else []):
                if isinstance(message, dict) and str(message.get("role") or "").lower() == "user":
                    content = message.get("content")
                    if content not in (None, ""):
                        source_text = content if isinstance(content, str) else str(content)
                        break
        source_text = str(source_text or "").strip()
        if not source_text:
            raise ValueError("Classify node requires an input value to classify")
        
        # 1. Construct Classification Prompt
        category_lines = []
        for cat in normalized_categories:
            name = cat["name"]
            desc = cat.get("description", "")
            category_lines.append(f"- {name}: {desc}")
            
        prompt = f"""{instructions}

Available Categories:
{chr(10).join(category_lines)}

Based on the context, determine the most appropriate category.
Respond ONLY with the category name. Do not include any other text."""

        # 2. Build a narrow classify-only prompt to avoid generic assistant replies.
        formatted_messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=source_text),
        ]
        
        # 3. Call LLM (using resolver + adapter)
        resolver = ModelResolver(self.db, self.organization_id)
        provider = await resolver.resolve(model_id, policy_snapshot=_policy_snapshot_from_state(state))
        adapter = LLMProviderAdapter(provider)
        
        # Emit reasoning/start
        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        if emitter:
            emitter.emit_node_start(
                node_id,
                config.get("name", "Classify"),
                "classify",
                {"categories": len(normalized_categories), "input_length": len(source_text)},
            )

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

        # 4. Match result to category
        selected_category = "else" # Default
        selected_handle = "else"
        normalized_response = response_content.strip().lower()
        for cat in normalized_categories:
            if cat["name"].lower() == normalized_response:
                selected_category = cat["name"]
                selected_handle = cat["id"]
                break
        if selected_handle == "else":
            for cat in normalized_categories:
                if cat["name"].lower() in normalized_response:
                    selected_category = cat["name"]
                    selected_handle = cat["id"]
                    break

        if emitter:
            emitter.emit_node_end(
                node_id,
                config.get("name", "Classify"),
                "classify",
                {
                    "selected": selected_category,
                    "branch_label": selected_category,
                    "branch_id": selected_handle,
                    "branch_taken": selected_handle,
                    "classification_result": response_content,
                },
            )
        
        logger.info(f"Classify node '{node_id}' selected: {selected_category} ({selected_handle})")
        
        return {
            "next": selected_handle,
            "branch_id": selected_handle,
            "branch_label": selected_category,
            "branch_taken": selected_handle,
            "classification_result": response_content,
            "category": selected_category,
        }

    def get_output_handles(self, config: Dict[str, Any]) -> List[str]:
        categories = config.get("categories", [])
        handles = []
        for idx, category in enumerate(categories):
            if not isinstance(category, dict):
                continue
            name = str(category.get("name") or "").strip()
            handles.append(str(category.get("id") or "").strip() or name or f"category_{idx}")
        handles.append("else")
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
