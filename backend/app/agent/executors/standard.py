import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select

from app.agent.execution.types import EventVisibility
from app.agent.execution.run_task_registry import is_run_cancel_requested
from app.agent.graph.contracts import (
    build_default_end_output_bindings,
    build_default_end_output_schema,
    infer_runtime_value_type,
    materialize_end_output,
    normalize_state_variable_definition,
    normalize_value_type,
    value_types_compatible,
)
from app.agent.execution.tool_input_contracts import (
    get_tool_execution_config,
    get_tool_input_schema,
    is_strict_tool_input,
    parse_schema_dict,
    sanitize_schema_dict,
)
from app.agent.executors.base import BaseNodeExecutor, ValidationResult
from app.agent.registry import AgentOperatorRegistry, AgentOperatorSpec, AgentStateField, AgentExecutorRegistry
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, create_model
from app.services.model_resolver import ModelResolver
from app.agent.core.llm_adapter import LLMProviderAdapter, extract_usage_payload_from_message
from app.agent.cel_engine import evaluate_template
from app.services.model_limits_service import ModelLimitsService
from app.services.prompt_snapshot_service import PromptSnapshotService
from app.services.prompt_reference_resolver import PromptReferenceResolver
from app.services.run_invocation_service import RunInvocationService
from app.services.token_counter_service import TokenCounterService
from app.services.resource_policy_service import ResourcePolicySnapshot
from app.services.mcp_service import McpRuntimeService
from app.db.postgres.models.agents import AgentRun, RunStatus

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


def _tool_model_name(tool_name: str, suffix: str) -> str:
    return f"{tool_name.title().replace('-', '_').replace(' ', '_')}{suffix}"


def _tool_result_max_chars() -> int:
    raw = str(os.getenv("AGENT_TOOL_RESULT_MAX_CHARS") or "6000").strip()
    try:
        value = int(raw)
    except Exception:
        value = 6000
    return max(512, value)


def _truncate_tool_result_text(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "... [truncated]"


def _serialize_message_for_accounting(message: Any) -> dict[str, Any]:
    if isinstance(message, dict):
        return dict(message)
    payload: dict[str, Any] = {
        "role": getattr(message, "type", None) or message.__class__.__name__,
        "content": getattr(message, "content", None),
    }
    tool_calls = getattr(message, "tool_calls", None)
    if isinstance(tool_calls, list) and tool_calls:
        payload["tool_calls"] = tool_calls
    name = getattr(message, "name", None)
    if name:
        payload["name"] = name
    return payload


def _serialize_tool_for_accounting(tool: Any) -> dict[str, Any]:
    return {
        "name": str(getattr(tool, "name", None) or getattr(tool, "slug", None) or ""),
        "description": getattr(tool, "description", None),
        "input_schema": getattr(tool, "input_schema", None),
        "parameter_schema": getattr(tool, "parameter_schema", None),
    }


def _truncate_tool_result_payload(payload: Any, *, limit: int) -> Any:
    if payload is None or isinstance(payload, (bool, int, float)):
        return payload
    if isinstance(payload, str):
        return _truncate_tool_result_text(payload, limit=limit)
    if isinstance(payload, (dict, list)):
        try:
            rendered = json.dumps(payload, ensure_ascii=False)
        except Exception:
            rendered = str(payload)
        if len(rendered) <= limit:
            return payload
        return {
            "_truncated": True,
            "_original_type": type(payload).__name__,
            "_original_chars": len(rendered),
            "preview": _truncate_tool_result_text(rendered, limit=limit),
        }
    rendered = str(payload)
    if len(rendered) <= limit:
        return payload
    return _truncate_tool_result_text(rendered, limit=limit)


def _merge_usage_payloads(*payloads: dict[str, int] | None) -> dict[str, int] | None:
    totals: dict[str, int] = {}
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            try:
                parsed = int(value)
            except Exception:
                continue
            if parsed < 0:
                continue
            totals[key] = totals.get(key, 0) + parsed
    return totals or None


def _json_schema_type_to_python(
    schema: dict[str, Any],
    *,
    model_name: str,
) -> Any:
    any_of = schema.get("anyOf")
    one_of = schema.get("oneOf")
    union_specs = any_of if isinstance(any_of, list) else one_of if isinstance(one_of, list) else None
    if union_specs:
        non_null_specs = [
            item for item in union_specs
            if not (isinstance(item, dict) and item.get("type") == "null")
        ]
        if len(non_null_specs) == 1 and isinstance(non_null_specs[0], dict):
            return _json_schema_type_to_python(non_null_specs[0], model_name=model_name)
        return Any

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        non_null_types = [item for item in schema_type if item != "null"]
        if len(non_null_types) == 1:
            schema_type = non_null_types[0]
        else:
            return Any

    if schema_type == "string":
        return str
    if schema_type == "integer":
        return int
    if schema_type == "number":
        return float
    if schema_type == "boolean":
        return bool
    if schema_type == "array":
        items = schema.get("items")
        item_type = Any
        if isinstance(items, dict):
            item_type = _json_schema_type_to_python(items, model_name=f"{model_name}Item")
        return List[item_type]
    if schema_type == "object" or isinstance(schema.get("properties"), dict):
        properties = schema.get("properties")
        if not isinstance(properties, dict) or not properties:
            return Dict[str, Any]
        required = set(schema.get("required", []) or [])
        fields: Dict[str, tuple[Any, Any]] = {}
        for prop_name, prop_schema in properties.items():
            if not isinstance(prop_schema, dict):
                continue
            child_type = _json_schema_type_to_python(prop_schema, model_name=f"{model_name}_{prop_name.title()}")
            if prop_name not in required:
                child_type = Optional[child_type]
            description = prop_schema.get("description") if isinstance(prop_schema.get("description"), str) else None
            default = ... if prop_name in required else None
            field_def = Field(default=default, description=description) if description else default
            fields[prop_name] = (child_type, field_def)
        if not fields:
            return Dict[str, Any]
        return create_model(model_name, **fields)
    return Any


def _build_tool_args_schema(tool_name: str, input_schema: dict[str, Any]) -> type[BaseModel]:
    model_name = _tool_model_name(tool_name, "Args")
    if not isinstance(input_schema, dict) or input_schema.get("type") != "object":
        return create_model(model_name, input=(Dict[str, Any], ...))

    properties = input_schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        return create_model(model_name, input=(Optional[Dict[str, Any]], None))

    required = set(input_schema.get("required", []) or [])
    fields: Dict[str, tuple[Any, Any]] = {}
    for prop_name, prop_schema in properties.items():
        if not isinstance(prop_schema, dict):
            continue
        field_type = _json_schema_type_to_python(
            prop_schema,
            model_name=_tool_model_name(tool_name, f"_{prop_name.title()}"),
        )
        if prop_name not in required:
            field_type = Optional[field_type]
        description = prop_schema.get("description") if isinstance(prop_schema.get("description"), str) else None
        default = ... if prop_name in required else None
        field_def = Field(default=default, description=description) if description else default
        fields[prop_name] = (field_type, field_def)

    return create_model(model_name, **fields) if fields else create_model(model_name)


def _normalize_model_tool_args(call_args: Any, tool_record: Any | None) -> dict[str, Any]:
    if isinstance(call_args, dict):
        return call_args
    _ = tool_record
    return {"raw_input": call_args}


def _resolve_quota_max_output_tokens(state: Dict[str, Any]) -> Optional[int]:
    if not isinstance(state, dict):
        return None
    context = state.get("context")
    if not isinstance(context, dict):
        nested_state = state.get("state")
        if isinstance(nested_state, dict):
            context = nested_state.get("context")
    if not isinstance(context, dict):
        return None
    raw = context.get("quota_max_output_tokens")
    try:
        parsed = int(raw)
        if parsed > 0:
            return parsed
    except Exception:
        return None
    return None


def _build_recoverable_error_update(
    *,
    state: Dict[str, Any],
    error: Exception,
    node_id: str,
    node_name: str,
    existing_messages: Optional[List[BaseMessage]] = None,
    last_agent_output: Any = None,
    tool_outputs: Optional[List[Any]] = None,
    last_context: Any = None,
) -> Dict[str, Any]:
    error_text = str(error)
    rendered = f"[{node_name}] runtime error: {error_text}"
    merged_messages = list(existing_messages or [])
    merged_messages.append(AIMessage(content=rendered))

    state_payload = state.get("state", {}) if isinstance(state, dict) else {}
    if not isinstance(state_payload, dict):
        state_payload = {}

    next_state = {
        **state_payload,
        "last_agent_output": last_agent_output if last_agent_output is not None else rendered,
        "last_error": {
            "code": "NODE_RUNTIME_ERROR",
            "node_id": node_id,
            "node_name": node_name,
            "message": error_text,
        },
    }

    update: Dict[str, Any] = {
        "messages": merged_messages,
        "state": next_state,
        "error": error_text,
    }
    if tool_outputs is not None:
        update["tool_outputs"] = tool_outputs
    if last_context is not None:
        update["context"] = last_context
    return update

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
        
        state_vars = config.get("state_variables", [])
        workflow_input = state.get("workflow_input", {})
        if not isinstance(workflow_input, dict):
            workflow_input = {}
        input_text = workflow_input.get("text")
        if input_text is None:
            input_text = workflow_input.get("input_as_text")
        if input_text is None:
            input_text = state.get("input")
        workflow_input = {
            "text": str(input_text or ""),
            "input_as_text": str(input_text or ""),
            **workflow_input,
        }

        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        node_id = context.get("node_id", "start") if context else "start"
        node_name = context.get("node_name", "Start") if context else "Start"
        if emitter:
            emitter.emit_node_start(
                node_id,
                node_name,
                "start",
                {"state_variables": len(state_vars), "workflow_inputs": len(workflow_input)},
            )
        
        seeded_state = state.get("state", {})
        if not isinstance(seeded_state, dict):
            seeded_state = {}
        initial_state = dict(seeded_state)
        state_types: Dict[str, str] = {}
        
        # Set up state variables with defaults
        for raw_var in state_vars:
            var = normalize_state_variable_definition(raw_var)
            key = var.get("key")
            value_type = normalize_value_type(var.get("type"))
            if not key:
                continue
            state_types[key] = value_type
            if "default_value" not in var:
                continue
            default = var.get("default_value")
            if key in initial_state:
                continue
            if default is None or value_types_compatible(value_type, infer_runtime_value_type(default)):
                initial_state[key] = default

        result: Dict[str, Any] = {
            "workflow_input": workflow_input,
            "state": initial_state,
            "state_types": state_types,
        }
        if emitter:
            emitter.emit_internal_event(
                "workflow.start_seeded",
                {
                    "workflow_input": list(workflow_input.keys()),
                    "state": list(initial_state.keys()),
                },
                node_id=node_id,
                category="workflow_contract",
            )
            emitter.emit_node_end(node_id, node_name, "start", {"keys": list(result.keys())})
        return result


class EndNodeExecutor(BaseNodeExecutor):
    """
    Exit point executor.
    Extracts specified output from state.
    """
    
    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        logger.debug("Executing END node")

        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        node_id = context.get("node_id", "end") if context else "end"
        node_name = context.get("node_name", "End") if context else "End"
        if emitter:
            emitter.emit_node_start(
                node_id,
                node_name,
                "end",
                {"has_schema": isinstance(config.get("output_schema"), dict)},
            )
        
        result = {}

        if isinstance(config.get("output_schema"), dict) or isinstance(config.get("output_bindings"), list):
            try:
                # End owns the workflow return contract only. Presentation-facing
                # assistant text is derived elsewhere from assistant-visible output.
                result["final_output"] = materialize_end_output(config=config, state=state)
                if emitter:
                    emitter.emit_internal_event(
                        "workflow.end_materialized",
                        {
                            "node_id": node_id,
                            "node_name": node_name,
                            "schema_name": (config.get("output_schema") or {}).get("name"),
                            "binding_count": len(config.get("output_bindings") or []),
                            "final_output": result["final_output"],
                        },
                        node_id=node_id,
                        category="workflow_contract",
                    )
            except Exception as e:
                logger.warning(f"Failed to materialize end output: {e}")
                if emitter:
                    emitter.emit_internal_event(
                        "workflow.end_validation_failed",
                        {"error": str(e)},
                        node_id=node_id,
                        category="workflow_contract",
                    )
                raise
        else:
            output_variable = config.get("output_variable")
            output_message = config.get("output_message")
            if output_variable:
                state_vars = state.get("state", {})
                if output_variable in state_vars:
                    result["final_output"] = state_vars[output_variable]
                elif output_variable in state:
                    result["final_output"] = state[output_variable]
            if output_message:
                try:
                    interpolated = evaluate_template(output_message, state)
                    result["final_output"] = interpolated
                except Exception as e:
                    logger.warning(f"Failed to interpolate output message: {e}")
                    result["final_output"] = output_message
        
        if emitter:
            emitter.emit_node_end(node_id, node_name, "end", {"has_output": bool(result)})
        return result


@dataclass
class ToolExecutionPolicy:
    is_pure: bool
    concurrency_group: str
    max_concurrency: int
    timeout_s: Optional[int]


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

    def _trace_safe_value(self, value: Any, *, max_string: int = 1200, max_items: int = 12) -> Any:
        if callable(value):
            name = getattr(value, "__name__", value.__class__.__name__)
            return f"<callable:{name}>"
        if isinstance(value, str):
            if len(value) <= max_string:
                return value
            return value[:max_string] + "...[truncated]"
        if isinstance(value, dict):
            items = list(value.items())[:max_items]
            rendered = {str(key): self._trace_safe_value(val, max_string=max_string, max_items=max_items) for key, val in items}
            if len(value) > max_items:
                rendered["__truncated_keys__"] = len(value) - max_items
            return rendered
        if isinstance(value, list):
            rendered = [self._trace_safe_value(item, max_string=max_string, max_items=max_items) for item in value[:max_items]]
            if len(value) > max_items:
                rendered.append({"__truncated_items__": len(value) - max_items})
            return rendered
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return value

    def _emit_inferred_tool_call_event(
        self,
        *,
        emitter: Any,
        node_id: str,
        source: str,
        raw_payload: Any,
        tool_call: Dict[str, Any],
    ) -> None:
        if not emitter:
            return
        wrapped_keys: list[str] = []
        input_payload = tool_call.get("input")
        if isinstance(input_payload, dict):
            wrapped_keys = [key for key in ("query", "text", "value") if key in input_payload]
        emitter.emit_internal_event(
            "reasoning.tool_call_inferred",
            {
                "source": source,
                "raw_payload": self._trace_safe_value(raw_payload),
                "normalized_tool_call": self._trace_safe_value(tool_call),
                "wrapped_input_keys": wrapped_keys,
                "has_top_level_action": bool(isinstance(input_payload, dict) and input_payload.get("action")),
            },
            node_id=node_id,
            category="tool_reasoning",
        )

    async def _is_current_run_cancelled(self, context: Dict[str, Any] | None) -> bool:
        if not self.db or not isinstance(context, dict):
            return False
        if is_run_cancel_requested(
            run_id=context.get("run_id"),
            root_run_id=context.get("root_run_id"),
            parent_run_id=context.get("parent_run_id"),
        ):
            return True
        raw_run_id = context.get("run_id")
        if not raw_run_id:
            return False
        try:
            run_id = UUID(str(raw_run_id))
        except Exception:
            return False
        status = (
            await self.db.execute(select(AgentRun.status).where(AgentRun.id == run_id))
        ).scalar_one_or_none()
        return str(getattr(status, "value", status) or "").strip().lower() == RunStatus.cancelled.value

    @staticmethod
    def _build_reasoning_state_update(
        *,
        state: Dict[str, Any],
        emitted_messages: List[BaseMessage],
        last_agent_output: Any,
        tool_outputs: List[Any],
        last_context: Any,
    ) -> Dict[str, Any]:
        state_update = {
            "messages": emitted_messages,
            "state": {
                **(state.get("state", {})),
                "last_agent_output": last_agent_output,
            },
        }
        if tool_outputs:
            state_update["tool_outputs"] = tool_outputs
        if last_context is not None:
            state_update["context"] = last_context
        return state_update

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
        tool_name = (
            candidate.get("tool")
            or candidate.get("tool_name")
            or candidate.get("toolName")
            or candidate.get("name")
            or candidate.get("function")
        )

        if "input" in candidate:
            input_data = candidate.get("input")
        elif "args" in candidate:
            input_data = candidate.get("args")
        elif "parameters" in candidate:
            input_data = candidate.get("parameters")
        elif "payload" in candidate:
            input_data = candidate.get("payload")
        elif "data" in candidate:
            input_data = candidate.get("data")
        elif "arguments" in candidate:
            input_data = candidate.get("arguments")
        else:
            input_data = {
                key: value
                for key, value in candidate.items()
                if key
                not in {
                    "tool_call",
                    "toolCall",
                    "tool_id",
                    "toolId",
                    "toolID",
                    "tool",
                    "tool_name",
                    "toolName",
                    "name",
                    "function",
                    "id",
                    "type",
                    "index",
                }
            }

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

    def _parse_config_schema(self, config_schema: Any) -> Dict[str, Any]:
        return parse_schema_dict(config_schema)

    def _parse_tool_input_schema(self, tool: Any) -> Dict[str, Any]:
        return get_tool_input_schema(tool)

    def _coerce_tool_input(self, tool_input: Any, tool: Any) -> Dict[str, Any]:
        def _parse_json_object(raw: Any) -> Optional[Dict[str, Any]]:
            if not isinstance(raw, str):
                return None
            text = raw.strip()
            if not text:
                return None
            candidates: List[str] = [text]

            fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
            if fenced:
                candidates.append(fenced.group(1).strip())

            first = text.find("{")
            last = text.rfind("}")
            if first != -1 and last > first:
                candidates.append(text[first:last + 1].strip())

            trimmed = text.strip().rstrip(",")
            if not trimmed.startswith("{") and ":" in trimmed:
                candidates.append("{" + trimmed.strip("{} \t\r\n,") + "}")

            for candidate in candidates:
                if not candidate:
                    continue
                try:
                    parsed = json.loads(candidate)
                except Exception:
                    parsed = None
                if isinstance(parsed, str):
                    inner = parsed.strip()
                    if inner and inner != candidate:
                        try:
                            parsed = json.loads(inner)
                        except Exception:
                            parsed = None
                if isinstance(parsed, dict):
                    return parsed
            return None

        if not isinstance(tool_input, dict):
            tool_input = {"value": tool_input}
        else:
            tool_input = dict(tool_input)

        value_payload = tool_input.get("value")
        if isinstance(value_payload, str):
            parsed_value_payload = _parse_json_object(value_payload)
            if isinstance(parsed_value_payload, dict):
                value_payload = parsed_value_payload
                tool_input["value"] = parsed_value_payload
        if isinstance(value_payload, dict):
            merged = dict(value_payload)
            for key, val in tool_input.items():
                if key == "value":
                    continue
                if key not in merged:
                    merged[key] = val
            tool_input = merged

        nested_candidates: List[Dict[str, Any]] = []
        for wrapper_key in ("input", "args", "parameters", "payload", "data"):
            wrapper_value = tool_input.get(wrapper_key)
            if isinstance(wrapper_value, str):
                parsed_wrapper = _parse_json_object(wrapper_value)
                if isinstance(parsed_wrapper, dict):
                    wrapper_value = parsed_wrapper
                    tool_input[wrapper_key] = parsed_wrapper
            if isinstance(wrapper_value, dict):
                nested_candidates.append(wrapper_value)

        nested: Dict[str, Any] = {}
        for candidate in nested_candidates:
            for key, value in candidate.items():
                if key not in nested:
                    nested[key] = value
        query_aliases = ("query", "q", "search_query", "keywords", "text", "value")
        if not tool_input.get("query"):
            for alias in query_aliases:
                candidate = tool_input.get(alias)
                if candidate is None:
                    candidate = nested.get(alias)
                if isinstance(candidate, str) and candidate.strip():
                    tool_input["query"] = candidate
                    break

        def _coerce_string_alias(target_key: str, aliases: tuple[str, ...]) -> None:
            existing = tool_input.get(target_key)
            if isinstance(existing, str) and existing.strip():
                return
            for alias in aliases:
                candidate = tool_input.get(alias)
                if candidate is None:
                    candidate = nested.get(alias)
                if isinstance(candidate, str) and candidate.strip():
                    tool_input[target_key] = candidate
                    return
                if isinstance(candidate, (int, float)):
                    tool_input[target_key] = str(candidate)
                    return

        _coerce_string_alias(
            "path",
            (
                "path",
                "file_path",
                "filepath",
                "filePath",
                "file",
                "filename",
                "target_path",
                "targetPath",
                "relative_path",
                "relativePath",
                "pathname",
            ),
        )
        _coerce_string_alias(
            "content",
            (
                "content",
                "contents",
                "text",
                "body",
                "code",
                "source",
                "file_content",
                "fileContent",
                "new_content",
                "newContent",
            ),
        )
        _coerce_string_alias(
            "from_path",
            (
                "from_path",
                "fromPath",
                "source_path",
                "sourcePath",
                "old_path",
                "oldPath",
                "from",
            ),
        )
        _coerce_string_alias(
            "to_path",
            (
                "to_path",
                "toPath",
                "destination_path",
                "destinationPath",
                "dest_path",
                "destPath",
                "new_path",
                "newPath",
                "to",
            ),
        )
        _coerce_string_alias(
            "entry_file",
            (
                "entry_file",
                "entryFile",
                "entry",
                "entry_path",
                "entryPath",
            ),
        )
        input_schema = self._parse_tool_input_schema(tool)
        properties = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
        required = input_schema.get("required", []) if isinstance(input_schema, dict) else []
        target_key: Optional[str] = None

        if isinstance(required, list) and len(required) == 1 and isinstance(required[0], str):
            target_key = required[0]
        elif isinstance(properties, dict) and len(properties) == 1:
            target_key = next(iter(properties.keys()))

        if target_key and not tool_input.get(target_key):
            scalar_value = tool_input.get("value")
            if scalar_value is None and nested:
                scalar_value = nested.get("value")
            if scalar_value is not None and not isinstance(scalar_value, dict):
                tool_input[target_key] = scalar_value

        return tool_input

    def _get_tool_execution_policy(self, tool: Any, default_timeout: Optional[int]) -> ToolExecutionPolicy:
        execution = get_tool_execution_config(tool)
        is_pure = bool(execution.get("is_pure", False))
        concurrency_group = execution.get("concurrency_group") or "default"
        max_concurrency = execution.get("max_concurrency")
        if max_concurrency is None or int(max_concurrency) < 1:
            max_concurrency = 1
        timeout_s = execution.get("timeout_s", None)
        if timeout_s is None:
            timeout_s = default_timeout
        return ToolExecutionPolicy(
            is_pure=is_pure,
            concurrency_group=str(concurrency_group),
            max_concurrency=int(max_concurrency),
            timeout_s=timeout_s,
        )

    def _build_langchain_tool(self, tool: Any) -> BaseTool:
        tool_name = getattr(tool, "slug", None) or getattr(tool, "name", "tool")
        description = getattr(tool, "description", "") or ""
        schema = parse_schema_dict(getattr(tool, "schema", {}) or {})
        input_schema = sanitize_schema_dict(schema.get("input", {}) if isinstance(schema, dict) else {}, tool_name=tool_name)
        args_schema = _build_tool_args_schema(tool_name, input_schema)

        def _run(*args: Any, **kwargs: Any) -> Any:
            raise NotImplementedError("RegistryTool is for tool binding only")

        async def _arun(*args: Any, **kwargs: Any) -> Any:
            raise NotImplementedError("RegistryTool is for tool binding only")

        registry_tool_cls = type(
            f"{tool_name.title().replace('-', '_').replace(' ', '_')}Tool",
            (BaseTool,),
            {
                "__annotations__": {
                    "name": str,
                    "description": str,
                    "args_schema": type[BaseModel],
                },
                "__module__": __name__,
                "name": tool_name,
                "description": description,
                "args_schema": args_schema,
                "_run": _run,
                "_arun": _arun,
            },
        )

        return registry_tool_cls()

    async def _load_tool_records(self, tool_ids: List[Any]) -> List[Any]:
        if not self.db or not tool_ids:
            return []

        from uuid import UUID
        from sqlalchemy import select, or_
        from app.db.postgres.models.registry import ToolRegistry

        valid_ids = []
        for raw in tool_ids:
            try:
                valid_ids.append(UUID(str(raw)))
            except Exception:
                continue

        if not valid_ids:
            return []

        stmt = select(ToolRegistry).where(ToolRegistry.id.in_(valid_ids))
        if self.tenant_id is None:
            stmt = stmt.where(ToolRegistry.tenant_id == None)
        else:
            stmt = stmt.where(
                or_(
                    ToolRegistry.tenant_id == self.tenant_id,
                    ToolRegistry.tenant_id == None,
                )
            )
        result = await self.db.execute(stmt)
        tools = list(result.scalars().all())
        resolver = PromptReferenceResolver(self.db, self.tenant_id)
        resolved_tools: list[Any] = []
        for tool in tools:
            schema = tool.schema if isinstance(tool.schema, dict) else {}
            resolved_description, resolved_input, resolved_output = await resolver.resolve_tool_payload(
                description=getattr(tool, "description", None),
                input_schema=schema.get("input") if isinstance(schema.get("input"), dict) else {},
                output_schema=schema.get("output") if isinstance(schema.get("output"), dict) else {},
            )
            columns = list(getattr(getattr(tool, "__table__", None), "columns", []))
            tool_payload = {
                column.name: getattr(tool, column.name)
                for column in columns
            }
            if not tool_payload:
                for attr in (
                    "id",
                    "tenant_id",
                    "name",
                    "slug",
                    "description",
                    "schema",
                    "config_schema",
                    "implementation_type",
                    "ownership",
                    "managed_by",
                    "source_object_type",
                    "source_object_id",
                    "artifact_id",
                    "artifact_version",
                    "artifact_revision_id",
                    "visual_pipeline_id",
                    "executable_pipeline_id",
                    "builtin_key",
                    "builtin_template_id",
                    "is_builtin_template",
                    "is_active",
                    "is_system",
                ):
                    if hasattr(tool, attr):
                        tool_payload[attr] = getattr(tool, attr)
            elif "config_schema" not in tool_payload and hasattr(tool, "config_schema"):
                tool_payload["config_schema"] = getattr(tool, "config_schema")
            tool_payload["description"] = resolved_description
            tool_payload["schema"] = {"input": resolved_input, "output": resolved_output}
            resolved_tools.append(SimpleNamespace(**tool_payload))
        return resolved_tools

    def _buffer_tool_call_chunks(
        self,
        message: BaseMessage,
        buffers: Dict[str, Dict[str, Any]],
        order: List[str],
    ) -> None:
        def _merge_dict_fragments(target: Dict[str, Any], fragment: Dict[str, Any]) -> None:
            for key, value in fragment.items():
                existing = target.get(key)
                if isinstance(existing, dict) and isinstance(value, dict):
                    _merge_dict_fragments(existing, value)
                elif isinstance(existing, str) and isinstance(value, str):
                    target[key] = existing + value
                else:
                    target[key] = value

        tool_call_chunks = getattr(message, "tool_call_chunks", None)
        if not tool_call_chunks:
            return
        for chunk in tool_call_chunks:
            if isinstance(chunk, dict):
                chunk_id = chunk.get("id")
                chunk_name = chunk.get("name")
                chunk_args = chunk.get("args")
                chunk_index = chunk.get("index")
            else:
                chunk_id = getattr(chunk, "id", None)
                chunk_name = getattr(chunk, "name", None)
                chunk_args = getattr(chunk, "args", None)
                chunk_index = getattr(chunk, "index", None)

            def _find_key_by_index(idx: Any) -> Optional[str]:
                if idx is None:
                    return None
                for existing_key, existing in buffers.items():
                    if existing.get("index") == idx:
                        return existing_key
                return None

            existing_index_key = _find_key_by_index(chunk_index)
            key: Optional[str] = None

            if chunk_id:
                if chunk_id in buffers:
                    key = chunk_id
                elif existing_index_key is not None:
                    key = existing_index_key
                else:
                    key = chunk_id
            elif existing_index_key is not None:
                key = existing_index_key
            elif chunk_index is not None:
                key = f"index:{chunk_index}"
            else:
                key = f"pos:{len(order)}"

            if key not in buffers:
                buffers[key] = {
                    "id": chunk_id,
                    "name": chunk_name,
                    "args_text": "",
                    "args_obj": {},
                    "index": chunk_index,
                }
                order.append(key)

            # Promote index-keyed partial buffer to canonical chunk id when id later arrives.
            if chunk_id and key != chunk_id and chunk_id not in buffers:
                buffers[chunk_id] = buffers.pop(key)
                for i, existing_key in enumerate(order):
                    if existing_key == key:
                        order[i] = chunk_id
                        break
                key = chunk_id

            buf = buffers[key]
            if chunk_name:
                buf["name"] = chunk_name
            if chunk_index is not None and buf.get("index") is None:
                buf["index"] = chunk_index
            if chunk_id and not buf.get("id"):
                buf["id"] = chunk_id
            if chunk_args:
                if isinstance(chunk_args, dict):
                    args_obj = buf.get("args_obj") if isinstance(buf.get("args_obj"), dict) else {}
                    _merge_dict_fragments(args_obj, chunk_args)
                    buf["args_obj"] = args_obj
                    continue

                if not isinstance(chunk_args, str):
                    try:
                        chunk_args = json.dumps(chunk_args)
                    except Exception:
                        chunk_args = str(chunk_args)

                if isinstance(chunk_args, str):
                    parsed_args = None
                    text = chunk_args.strip()
                    if text.startswith("{") and text.endswith("}"):
                        try:
                            parsed_candidate = json.loads(text)
                        except Exception:
                            parsed_candidate = None
                        if isinstance(parsed_candidate, dict):
                            parsed_args = parsed_candidate
                    if isinstance(parsed_args, dict):
                        args_obj = buf.get("args_obj") if isinstance(buf.get("args_obj"), dict) else {}
                        _merge_dict_fragments(args_obj, parsed_args)
                        buf["args_obj"] = args_obj
                    else:
                        buf["args_text"] = str(buf.get("args_text") or "") + chunk_args

    def _finalize_tool_calls(
        self,
        buffers: Dict[str, Dict[str, Any]],
        order: List[str],
        fallback_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        tool_calls: List[Dict[str, Any]] = []
        parse_failed = False
        for key in order:
            buf = buffers.get(key, {})
            if not buf:
                continue
            args_obj = dict(buf.get("args_obj") or {}) if isinstance(buf.get("args_obj"), dict) else {}
            args_text = str(buf.get("args_text") or "")
            parsed_args: Any

            if args_text.strip():
                try:
                    parsed_from_text = json.loads(args_text)
                except Exception:
                    parse_failed = True
                    parsed_from_text = {"value": args_text}
            else:
                parsed_from_text = {}

            if isinstance(parsed_from_text, dict):
                merged_args = dict(args_obj)
                for arg_key, arg_value in parsed_from_text.items():
                    if arg_key not in merged_args:
                        merged_args[arg_key] = arg_value
                parsed_args = merged_args if merged_args else {}
            elif args_obj:
                parsed_args = args_obj
            else:
                parsed_args = parsed_from_text

            tool_calls.append({
                "id": buf.get("id"),
                "name": buf.get("name"),
                "args": parsed_args,
            })

        if tool_calls and not (parse_failed and fallback_calls):
            return tool_calls

        if fallback_calls:
            return fallback_calls

        return []

    def _extract_tool_output_payload(self, tool_result: Any) -> Any:
        if isinstance(tool_result, dict):
            if "context" in tool_result and tool_result.get("context") is not None:
                return tool_result.get("context")
            if "tool_outputs" in tool_result and tool_result.get("tool_outputs"):
                outputs = tool_result.get("tool_outputs")
                if isinstance(outputs, list) and outputs:
                    return outputs[0]
        return tool_result

    def _build_tool_batches(
        self,
        calls: List[Dict[str, Any]],
        max_parallel_tools: int,
    ) -> List[List[Dict[str, Any]]]:
        batches: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []
        group_counts: Dict[str, int] = {}

        for call in calls:
            policy: ToolExecutionPolicy = call["policy"]
            if not policy.is_pure:
                if current:
                    batches.append(current)
                    current = []
                    group_counts = {}
                batches.append([call])
                continue

            group_limit = policy.max_concurrency or 1
            current_group_count = group_counts.get(policy.concurrency_group, 0)
            if current and (len(current) >= max_parallel_tools or current_group_count >= group_limit):
                batches.append(current)
                current = []
                group_counts = {}

            current.append(call)
            group_counts[policy.concurrency_group] = group_counts.get(policy.concurrency_group, 0) + 1

        if current:
            batches.append(current)
        return batches

    async def _resolve_tool_id(
        self,
        tool_call: Dict[str, Any],
        configured_tools: List[Any],
        *,
        tool_records: Optional[List[Any]] = None,
    ) -> Optional[str]:
        if not configured_tools:
            return None

        def _normalize_tool_label(value: Any) -> str:
            text = str(value or "").strip().lower()
            if not text:
                return ""
            text = re.sub(r"[_\-]+", " ", text)
            text = re.sub(r"[^a-z0-9\s]", " ", text)
            return re.sub(r"\s+", " ", text).strip()

        configured = [str(tool) for tool in configured_tools if tool]
        resolved_records = list(tool_records or [])

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
        normalized_tool_name = _normalize_tool_label(tool_name)
        if tool_name in configured:
            return str(tool_name)

        for tool in resolved_records:
            if not tool:
                continue
            record_id = str(getattr(tool, "id", "") or "").strip()
            record_name = str(getattr(tool, "name", "") or "").strip()
            record_slug = str(getattr(tool, "slug", "") or "").strip()
            if tool_name_lower in {record_name.lower(), record_slug.lower()}:
                return record_id or None
            normalized_name = _normalize_tool_label(record_name)
            normalized_slug = _normalize_tool_label(record_slug)
            if normalized_tool_name and normalized_tool_name in {normalized_name, normalized_slug}:
                return record_id or None

        if not self.db:
            return None

        try:
            from uuid import UUID
            from sqlalchemy import select, or_
            from app.db.postgres.models.registry import ToolRegistry

            tool_ids = []
            for raw in configured:
                try:
                    tool_ids.append(UUID(str(raw)))
                except Exception:
                    continue

            if not tool_ids:
                return None

            stmt = select(ToolRegistry).where(ToolRegistry.id.in_(tool_ids))
            if self.tenant_id is None:
                stmt = stmt.where(ToolRegistry.tenant_id == None)
            else:
                stmt = stmt.where(
                    or_(
                        ToolRegistry.tenant_id == self.tenant_id,
                        ToolRegistry.tenant_id == None,
                    )
                )
            result = await self.db.execute(stmt)
            tools = result.scalars().all()
        except Exception:
            return None

        normalized_matches: list[str] = []
        for tool in tools:
            if not tool:
                continue
            name = str(tool.name).lower() if tool.name else ""
            slug = str(tool.slug).lower() if getattr(tool, "slug", None) else ""
            if tool_name_lower in (name, slug):
                return str(tool.id)
            normalized_name = _normalize_tool_label(tool.name)
            normalized_slug = _normalize_tool_label(getattr(tool, "slug", ""))
            if normalized_tool_name and normalized_tool_name in (normalized_name, normalized_slug):
                return str(tool.id)
            if normalized_tool_name and (
                f" {normalized_tool_name} " in f" {normalized_name} "
                or f" {normalized_tool_name} " in f" {normalized_slug} "
            ):
                normalized_matches.append(str(tool.id))

        if len(normalized_matches) == 1:
            return normalized_matches[0]

        return None

    def _build_tool_state(self, state: Dict[str, Any], tool_input: Dict[str, Any]) -> Dict[str, Any]:
        tool_state = dict(state or {})
        nested_state = dict(tool_state.get("state") or {})
        nested_state["last_agent_output"] = tool_input
        # Preserve runtime/auth context in nested state for downstream executors.
        if isinstance(state, dict) and isinstance(state.get("context"), dict):
            merged_nested_ctx = dict(state.get("context") or {})
            merged_nested_ctx.update(nested_state.get("context") or {})
            nested_state["context"] = merged_nested_ctx
        tool_state["state"] = nested_state
        # Keep existing context metadata (run/grant/tenant/token) while overlaying tool input.
        base_context = state.get("context") if isinstance(state, dict) and isinstance(state.get("context"), dict) else {}
        merged_context = dict(base_context or {})
        if isinstance(tool_input, dict):
            merged_context.update(tool_input)
        tool_state["context"] = merged_context
        return tool_state

    @staticmethod
    def _coerce_text_content(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts: List[str] = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        if isinstance(value, dict):
            for key in ("text", "content", "message", "summary"):
                text = value.get(key)
                if isinstance(text, str):
                    return text
        return ""

    async def _ensure_text_response(
        self,
        *,
        adapter: LLMProviderAdapter,
        full_content: str,
        last_message: Optional[BaseMessage],
        conversation_messages: List[BaseMessage],
        instructions: str,
        temperature: float,
        max_tokens: int,
        emitter: Any,
        node_id: str,
        has_tool_signals: bool,
    ) -> tuple[str, Optional[BaseMessage], bool]:
        if str(full_content).strip() or has_tool_signals:
            return full_content, last_message, False

        try:
            fallback_instruction = "Respond to the user directly in plain text. Do not call tools. Keep it concise."
            fallback_response = await adapter.ainvoke(
                [
                    *conversation_messages,
                    HumanMessage(
                        content=fallback_instruction,
                    ),
                ],
                system_prompt=instructions,
                tools=None,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            fallback_text = self._coerce_text_content(getattr(fallback_response, "content", ""))
            if fallback_text.strip():
                if emitter:
                    emitter.emit_token(fallback_text, node_id)
                return fallback_text, fallback_response, True
            return full_content, fallback_response, True
        except Exception as exc:
            logger.warning(f"Fallback text response generation failed: {exc}")
            return full_content, last_message, False

    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        logger.debug(f"Executing Agent (Reasoning) node")
        
        model_id = config.get("model_id")
        instructions = config.get("instructions", "")  # System prompt
        include_chat_history = config.get("include_chat_history", True)
        reasoning_effort = config.get("reasoning_effort", "medium")
        output_format = config.get("output_format", "text")
        output_schema = config.get("output_schema")
        tools = config.get("tools", [])  # Tool IDs to bind
        tool_execution_mode = config.get("tool_execution_mode") or "sequential"
        if tool_execution_mode not in ("sequential", "parallel_safe"):
            tool_execution_mode = "sequential"
        max_parallel_tools = int(config.get("max_parallel_tools", 4) or 4)
        if max_parallel_tools < 1:
            max_parallel_tools = 1
        tool_timeout_s = int(config.get("tool_timeout_s", 60) or 60)
        max_tool_iterations = int(config.get("max_tool_iterations", 10) or 10)
        if max_tool_iterations < 1:
            max_tool_iterations = 1
        
        # Extract emitter
        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        
        node_id = context.get("node_id", "agent_node") if context else "agent_node"
        node_name = config.get("name", "Agent")
        
        # Resolve model
        resolver = ModelResolver(self.db, self.tenant_id)
        policy_snapshot = _policy_snapshot_from_state(state)
        try:
            resolved_execution = await resolver.resolve_for_execution(model_id, policy_snapshot=policy_snapshot)
            provider = resolved_execution.provider_instance
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
        quota_max_tokens = _resolve_quota_max_output_tokens(state)
        if quota_max_tokens is not None:
            try:
                max_tokens = min(int(max_tokens), int(quota_max_tokens))
            except Exception:
                max_tokens = int(quota_max_tokens)
        
        # Interpolate instructions with state
        if instructions:
            try:
                instructions = evaluate_template(instructions, state)
            except Exception as e:
                logger.warning(f"Failed to interpolate instructions: {e}")

        # Execute
        try:
            adapter = LLMProviderAdapter(provider)

            if emitter:
                emitter.emit_node_start(node_id, node_name, "agent", {
                    "model": model_id,
                    "reasoning_effort": reasoning_effort,
                    "tools_count": len(tools),
                    "tool_execution_mode": tool_execution_mode,
                })

            tool_records = await self._load_tool_records(tools)
            mcp_tools: list[Any] = []
            if self.db is not None and self.tenant_id is not None:
                agent_id_raw = (context or {}).get("agent_id")
                if agent_id_raw:
                    try:
                        agent_uuid = UUID(str(agent_id_raw))
                        runtime_user_id = (context or {}).get("initiator_user_id") or (context or {}).get("user_id")
                        runtime_user_uuid = UUID(str(runtime_user_id)) if runtime_user_id else None
                        mcp_tools = await McpRuntimeService(self.db, self.tenant_id).list_agent_tools(
                            agent_id=agent_uuid,
                            user_id=runtime_user_uuid,
                        )
                    except Exception as exc:
                        logger.warning(f"Failed to load MCP mounted tools: {exc}")
            if mcp_tools:
                tool_records.extend(mcp_tools)
            tool_records_by_id = {str(t.id): t for t in tool_records if getattr(t, "id", None)}
            tool_records_by_slug = {
                str(getattr(t, "slug", "")).strip(): t
                for t in tool_records
                if getattr(t, "slug", None)
            }
            effective_tools = list(tools or []) + [str(t.id) for t in mcp_tools if getattr(t, "id", None)]
            langchain_tools = [self._build_langchain_tool(t) for t in tool_records] if tool_records else []
            tool_accounting_payloads = [_serialize_tool_for_accounting(t) for t in tool_records]

            conversation_messages = list(formatted_messages)
            emitted_messages: List[BaseMessage] = []
            tool_outputs: List[Any] = []
            last_context: Any = None
            last_agent_output: Any = None

            for iteration in range(max_tool_iterations):
                if await self._is_current_run_cancelled(context):
                    return self._build_reasoning_state_update(
                        state=state,
                        emitted_messages=emitted_messages,
                        last_agent_output=last_agent_output,
                        tool_outputs=tool_outputs,
                        last_context=last_context,
                    )
                full_content = ""
                tool_call_buffers: Dict[str, Dict[str, Any]] = {}
                tool_call_order: List[str] = []
                last_message: Optional[BaseMessage] = None
                streamed_usage_payload: dict[str, int] | None = None
                prompt_snapshot = PromptSnapshotService.build_from_langchain(
                    messages=[_serialize_message_for_accounting(message) for message in conversation_messages],
                    system_prompt=instructions,
                    tools=tool_accounting_payloads,
                    extra_context=None,
                )
                context_input_tokens, context_source = await TokenCounterService().count_input_tokens(
                    provider=resolved_execution.resolved_provider,
                    provider_model_id=resolved_execution.binding.provider_model_id,
                    snapshot=prompt_snapshot,
                    api_key=getattr(adapter.provider, "api_key", None),
                )
                max_context_tokens, max_context_tokens_source = await ModelLimitsService(self.db).resolve_input_limit(
                    tenant_id=self.tenant_id,
                    model_id=str(getattr(resolved_execution.logical_model, "id", None) or model_id),
                    resolved_provider=resolved_execution.resolved_provider,
                    resolved_provider_model_id=resolved_execution.binding.provider_model_id,
                    api_key=getattr(adapter.provider, "api_key", None),
                )

                # Stream tokens and buffer tool call chunks
                try:
                    async for chunk in adapter._astream(
                        conversation_messages,
                        system_prompt=instructions,
                        tools=langchain_tools if tools else None,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    ):
                        last_message = chunk.message if hasattr(chunk, "message") else None
                        chunk_usage_payload = extract_usage_payload_from_message(last_message)
                        if chunk_usage_payload:
                            streamed_usage_payload = _merge_usage_payloads(streamed_usage_payload, chunk_usage_payload)
                        if last_message is not None:
                            self._buffer_tool_call_chunks(last_message, tool_call_buffers, tool_call_order)
                        token_content = chunk.message.content if hasattr(chunk, "message") else ""
                        if token_content:
                            full_content += token_content
                            if emitter:
                                emitter.emit_token(token_content, node_id)
                except (NotImplementedError, Exception) as e:
                    logger.warning(f"Streaming failed/unsupported: {e}, using non-streaming")
                    response = await adapter.ainvoke(
                        conversation_messages,
                        system_prompt=instructions,
                        tools=langchain_tools if tools else None,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    full_content = response.content
                    streamed_usage_payload = extract_usage_payload_from_message(response)
                    if emitter:
                        emitter.emit_token(full_content, node_id)
                    last_message = response

                has_tool_signals = bool(tool_call_buffers)
                if last_message is not None and getattr(last_message, "tool_calls", None):
                    has_tool_signals = True
                full_content, last_message, fallback_used = await self._ensure_text_response(
                    adapter=adapter,
                    full_content=full_content,
                    last_message=last_message,
                    conversation_messages=conversation_messages,
                    instructions=instructions,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    emitter=emitter,
                    node_id=node_id,
                    has_tool_signals=has_tool_signals,
                )
                final_usage_payload = extract_usage_payload_from_message(last_message)
                iteration_usage_payload = (
                    _merge_usage_payloads(streamed_usage_payload, final_usage_payload)
                    if fallback_used
                    else (final_usage_payload or streamed_usage_payload)
                )
                invocation_payload = RunInvocationService.build_invocation_payload(
                    model_id=str(getattr(resolved_execution.logical_model, "id", None) or model_id),
                    resolved_provider=resolved_execution.resolved_provider,
                    resolved_provider_model_id=resolved_execution.binding.provider_model_id,
                    node_id=node_id,
                    node_name=node_name,
                    node_type="agent",
                    max_context_tokens=max_context_tokens,
                    max_context_tokens_source=max_context_tokens_source,
                    context_input_tokens=context_input_tokens,
                    context_source=context_source,
                    exact_usage_payload=iteration_usage_payload,
                    estimated_output_tokens=RunInvocationService.estimate_output_tokens(last_message),
                )

                if emitter:
                    emitter.emit_node_end(
                        node_id,
                        node_name,
                        "agent",
                        {
                            "content_length": len(full_content),
                            "usage": invocation_payload["usage"],
                            "usage_source": invocation_payload["usage"].get("source"),
                            "invocation": invocation_payload,
                        },
                    )

                # Handle structured output
                result_content: Any = full_content
                if output_format == "json":
                    try:
                        result_content = json.loads(full_content)
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse JSON output, returning raw string")

                last_agent_output = result_content

                fallback_calls = None
                if last_message is not None and getattr(last_message, "tool_calls", None):
                    fallback_calls = list(getattr(last_message, "tool_calls", []))

                tool_calls = self._finalize_tool_calls(tool_call_buffers, tool_call_order, fallback_calls=fallback_calls)
                if not tool_calls:
                    tool_payload = self._extract_json_payload(full_content)
                    tool_call = self._normalize_tool_call(tool_payload)
                    tool_call_source = "assistant_content_json"
                    if not tool_call and isinstance(result_content, dict):
                        tool_call = self._normalize_tool_call(result_content)
                        tool_call_source = "assistant_result_json"
                    if tool_call:
                        self._emit_inferred_tool_call_event(
                            emitter=emitter,
                            node_id=node_id,
                            source=tool_call_source,
                            raw_payload=tool_payload if tool_call_source == "assistant_content_json" else result_content,
                            tool_call=tool_call,
                        )
                        tool_calls = [{
                            "id": tool_call.get("tool_id") or tool_call.get("tool_name"),
                            "tool_id": tool_call.get("tool_id"),
                            "name": tool_call.get("tool_name"),
                            "args": tool_call.get("input") or {},
                        }]

                tool_calls_for_message = None
                if tool_calls:
                    formatted_calls = []
                    for idx, call in enumerate(tool_calls):
                        if isinstance(call, dict):
                            call_id = call.get("id")
                            call_name = call.get("name") or call.get("tool_name")
                            call_args = call.get("args") or call.get("input") or {}
                            call_tool_id = call.get("tool_id")
                        else:
                            call_id = getattr(call, "id", None)
                            call_name = getattr(call, "name", None) or getattr(call, "tool_name", None)
                            call_args = getattr(call, "args", None) or getattr(call, "input", None) or {}
                            call_tool_id = getattr(call, "tool_id", None)

                        tool_record = None
                        if not call_name and call_tool_id:
                            tool_record = tool_records_by_id.get(str(call_tool_id))
                            call_name = getattr(tool_record, "slug", None) or getattr(tool_record, "name", None)
                        elif call_name:
                            tool_record = tool_records_by_slug.get(str(call_name).strip())

                        if not call_name:
                            continue
                        call_args = _normalize_model_tool_args(call_args, tool_record)

                        formatted_calls.append({
                            "id": str(call_id or f"toolcall_{iteration}_{idx}"),
                            "name": call_name,
                            "args": call_args,
                        })

                    if formatted_calls:
                        tool_calls_for_message = formatted_calls

                if tool_calls_for_message:
                    ai_message = AIMessage(content=full_content, tool_calls=tool_calls_for_message)
                else:
                    ai_message = AIMessage(content=full_content)

                emitted_messages.append(ai_message)
                conversation_messages.append(ai_message)

                if await self._is_current_run_cancelled(context):
                    return self._build_reasoning_state_update(
                        state=state,
                        emitted_messages=emitted_messages,
                        last_agent_output=last_agent_output,
                        tool_outputs=tool_outputs,
                        last_context=last_context,
                    )

                if not tool_calls:
                    state_update = self._build_reasoning_state_update(
                        state=state,
                        emitted_messages=emitted_messages,
                        last_agent_output=last_agent_output,
                        tool_outputs=tool_outputs,
                        last_context=last_context,
                    )
                    if last_context is not None:
                        pass
                    elif config.get("write_output_to_context") and isinstance(result_content, dict):
                        state_update["context"] = result_content
                    return state_update

                resolved_calls: List[Dict[str, Any]] = []
                for idx, call in enumerate(tool_calls):
                    call_id = call.get("id") or f"toolcall_{iteration}_{idx}"
                    tool_name = call.get("name")
                    tool_id = call.get("tool_id")

                    resolved_tool_id = None
                    if tool_id:
                        resolved_tool_id = str(tool_id)
                    elif tool_name:
                        resolved_tool_id = await self._resolve_tool_id(
                            {"tool_name": tool_name},
                            effective_tools,
                            tool_records=tool_records,
                        )
                    if not resolved_tool_id:
                        logger.warning(f"Unresolved tool call: {tool_name or tool_id}")
                        continue

                    tool_input = call.get("args") or call.get("input") or {}
                    tool_record = tool_records_by_id.get(resolved_tool_id)
                    if tool_record is None and tool_name:
                        tool_record = tool_records_by_slug.get(str(tool_name).strip())
                    tool_input = _normalize_model_tool_args(tool_input, tool_record)
                    if tool_record is not None:
                        tool_input = self._coerce_tool_input(tool_input, tool_record)
                    policy = self._get_tool_execution_policy(tool_record, tool_timeout_s)

                    resolved_calls.append({
                        "call_id": str(call_id),
                        "tool_id": resolved_tool_id,
                        "tool_name": tool_name,
                        "input": tool_input,
                        "policy": policy,
                    })

                if not resolved_calls:
                    error_msg = "No resolvable tool calls"
                    logger.warning(error_msg)
                    if emitter:
                        emitter.emit_error(error_msg, node_id)
                    return {
                        "messages": emitted_messages,
                        "state": {
                            **(state.get("state", {})),
                            "last_agent_output": last_agent_output,
                        },
                        "error": error_msg,
                    }

                from app.agent.executors.tool import ToolNodeExecutor
                tool_executor = ToolNodeExecutor(self.tenant_id, self.db)

                async def _run_tool_call(call: Dict[str, Any]) -> Tuple[str, Any]:
                    tool_state = self._build_tool_state(state, call["input"])
                    tool_context = {
                        **(context or {}),
                        "node_id": node_id,
                        "source_node_id": node_id,
                        "tool_call_id": call["call_id"],
                        "node_name": f"Tool:{call['tool_id']}",
                    }
                    timeout = call["policy"].timeout_s
                    try:
                        result = await asyncio.wait_for(
                            tool_executor.execute(tool_state, {"tool_id": call["tool_id"]}, tool_context),
                            timeout=timeout,
                        )
                        return call["call_id"], result
                    except asyncio.TimeoutError:
                        return call["call_id"], {"error": f"Tool call timed out after {timeout}s"}
                    except Exception as exc:
                        return call["call_id"], {"error": str(exc)}

                execution_results: Dict[str, Any] = {}
                if await self._is_current_run_cancelled(context):
                    return self._build_reasoning_state_update(
                        state=state,
                        emitted_messages=emitted_messages,
                        last_agent_output=last_agent_output,
                        tool_outputs=tool_outputs,
                        last_context=last_context,
                    )
                if tool_execution_mode == "parallel_safe":
                    batches = self._build_tool_batches(resolved_calls, max_parallel_tools)
                    for batch in batches:
                        if len(batch) == 1:
                            call_id, result = await _run_tool_call(batch[0])
                            execution_results[call_id] = result
                        else:
                            results = await asyncio.gather(*[_run_tool_call(call) for call in batch])
                            for call_id, result in results:
                                execution_results[call_id] = result
                else:
                    for call in resolved_calls:
                        call_id, result = await _run_tool_call(call)
                        execution_results[call_id] = result

                for call in resolved_calls:
                    result = execution_results.get(call["call_id"])
                    output_payload = self._extract_tool_output_payload(result)
                    output_payload = _truncate_tool_result_payload(
                        output_payload,
                        limit=_tool_result_max_chars(),
                    )
                    tool_outputs.append(output_payload)
                    if output_payload is not None:
                        last_context = output_payload
                        last_agent_output = output_payload

                    content = output_payload
                    if isinstance(content, (dict, list)):
                        try:
                            content = json.dumps(content)
                        except Exception:
                            content = str(content)
                    elif content is None:
                        content = ""
                    else:
                        content = str(content)

                    tool_message = ToolMessage(content=content, tool_call_id=call["call_id"])
                    emitted_messages.append(tool_message)
                    conversation_messages.append(tool_message)

                if await self._is_current_run_cancelled(context):
                    return self._build_reasoning_state_update(
                        state=state,
                        emitted_messages=emitted_messages,
                        last_agent_output=last_agent_output,
                        tool_outputs=tool_outputs,
                        last_context=last_context,
                    )

            error_msg = "Max tool iterations reached"
            if emitter:
                emitter.emit_error(error_msg, node_id)
            return {
                "messages": emitted_messages,
                "state": {
                    **(state.get("state", {})),
                    "last_agent_output": last_agent_output,
                },
                "tool_outputs": tool_outputs or None,
                "context": last_context,
                "_run_failure": {
                    "message": error_msg,
                    "code": "MAX_TOOL_ITERATIONS_REACHED",
                },
                "error": error_msg,
            }

        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            if emitter:
                emitter.emit_error(str(e), node_id)
            return _build_recoverable_error_update(
                state=state,
                error=e,
                node_id=node_id,
                node_name=node_name,
                existing_messages=locals().get("emitted_messages", []),
                last_agent_output=locals().get("last_agent_output"),
                tool_outputs=locals().get("tool_outputs"),
                last_context=locals().get("last_context"),
            )
    
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
        config_schema={
            "type": "object",
            "properties": {
                "state_variables": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "type": {"type": "string", "enum": ["string", "number", "boolean", "object", "list"]},
                            "default_value": {},
                        },
                        "required": ["key", "type"],
                    },
                },
            },
            "additionalProperties": True,
        },
        field_contracts={
            "state_variables": {"type": "state_variable_definitions"},
        },
        output_contract={
            "fields": [],
        },
        ui={
            "icon": "Play",
            "color": "#6b7280",
            "inputType": "any",
            "outputType": "message",
            "configFields": [
                {"name": "state_variables", "label": "State Variables", "fieldType": "variable_list", "required": False,
                 "description": "Initialize persistent state variables with defaults"}
            ],
            "workflowInputs": [
                {"key": "text", "type": "string", "label": "Text", "readonly": True},
                {"key": "files", "type": "list", "label": "Files", "readonly": True},
                {"key": "audio", "type": "list", "label": "Audio", "readonly": True},
                {"key": "images", "type": "list", "label": "Images", "readonly": True},
            ],
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
        config_schema={
            "type": "object",
            "properties": {
                "output_schema": {"type": "object", "additionalProperties": True},
                "output_bindings": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            },
            "additionalProperties": True,
        },
        field_contracts={
            "output_schema": {"type": "end_output_schema"},
            "output_bindings": {"type": "schema_binding"},
        },
        ui={
            "icon": "Square",
            "color": "#6b7280",
            "inputType": "any",
            "outputType": "any",
            "configFields": []
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
                "tools": {"type": "array", "items": {"type": "string"}, "title": "Tools"},
                "tool_execution_mode": {"type": "string", "title": "Tool Execution Mode", "enum": ["sequential", "parallel_safe"], "default": "sequential"},
                "max_parallel_tools": {"type": "number", "title": "Max Parallel Tools", "default": 4},
                "tool_timeout_s": {"type": "number", "title": "Tool Timeout (s)", "default": 60},
                "max_tool_iterations": {"type": "number", "title": "Max Tool Iterations", "default": 10}
            },
            "required": ["model_id"]
        },
        output_contract={
            "fields": [
                {"key": "output_text", "type": "string", "label": "Output Text"},
                {"key": "output_json", "type": "unknown", "label": "Output JSON"},
            ]
        },
        ui={
            "icon": "Bot",
            "color": "#8b5cf6",
            "inputType": "message",
            "outputType": "message",
            "configFields": [
                {"name": "name", "label": "Name", "fieldType": "string", "required": False, "description": "Agent display name"},
                {"name": "model_id", "label": "Model", "fieldType": "model", "required": True, "description": "Select a chat model"},
                {"name": "instructions", "label": "Instructions", "fieldType": "text", "required": False, "description": "System prompt with @variable support", "prompt_capable": True, "prompt_surface": "agent.instructions"},
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
                {"name": "tool_execution_mode", "label": "Tool Execution Mode", "fieldType": "select", "required": False, "default": "sequential",
                 "options": [
                    {"value": "sequential", "label": "Sequential"},
                    {"value": "parallel_safe", "label": "Parallel (Safe)"}
                 ]},
                {"name": "max_parallel_tools", "label": "Max Parallel Tools", "fieldType": "number", "required": False, "default": 4},
                {"name": "tool_timeout_s", "label": "Tool Timeout (s)", "fieldType": "number", "required": False, "default": 60},
                {"name": "max_tool_iterations", "label": "Max Tool Iterations", "fieldType": "number", "required": False, "default": 10}
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
        config_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "model_id": {"type": "string"},
                "instructions": {"type": "string"},
                "input_source": {"type": "object", "additionalProperties": True},
                "categories": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            },
            "required": ["model_id", "categories"],
        },
        field_contracts={
            "input_source": {"type": "value_ref", "allowed_types": ["string", "number", "boolean", "object", "list", "unknown"]},
        },
        output_contract={
            "fields": [
                {"key": "category", "type": "string", "label": "Category"},
                {"key": "confidence", "type": "number", "label": "Confidence"},
            ]
        },
        ui={
            "icon": "ListFilter", # Will need to add this icon map in frontend
            "color": "#8b5cf6",
            "inputType": "message",
            "outputType": "decision",
            "dynamicHandles": True,
            "configFields": [
                {"name": "name", "label": "Name", "fieldType": "string", "required": False},
                {"name": "model_id", "label": "Model", "fieldType": "model", "required": True, "description": "Model used for classification"},
                {"name": "input_source", "label": "Input Source", "fieldType": "value_ref", "required": False, "description": "Pick a value to classify"},
                {"name": "instructions", "label": "Instructions", "fieldType": "text", "required": False, "description": "Additional context for classification", "prompt_capable": True, "prompt_surface": "classify.instructions"},
                {"name": "categories", "label": "Categories", "fieldType": "category_list", "required": True, "description": "Define classification categories", "prompt_capable": True, "prompt_surface": "classify.categories.description"}
            ]
        }
    ))
    AgentExecutorRegistry.register("classify", ClassifyNodeExecutor)

    # =========================================================================
    # Data Operators
    # =========================================================================
    
    from app.agent.executors.data import TransformNodeExecutor, SetStateNodeExecutor
    from app.agent.executors.speech import SpeechToTextNodeExecutor
    
    # Transform Node
    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="transform",
        category="data",
        display_name="Transform",
        description="Reshape data using expressions",
        reads=[AgentStateField.STATE_VARIABLES, AgentStateField.CONTEXT],
        writes=[AgentStateField.STATE_VARIABLES, AgentStateField.TRANSFORM_OUTPUT],
        output_contract={
            "fields": [
                {"key": "output", "type": "unknown", "label": "Output"},
            ]
        },
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
        config_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "assignments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "type": {"type": "string", "enum": ["string", "number", "boolean", "object", "list"]},
                            "value": {},
                            "value_ref": {"type": "object", "additionalProperties": True},
                        },
                        "required": ["key"],
                        "additionalProperties": True,
                    },
                },
                "is_expression": {"type": "boolean"},
            },
            "required": ["assignments"],
            "additionalProperties": True,
        },
        field_contracts={
            "assignments": {"type": "state_assignment_list"},
        },
        ui={
            "icon": "Database",
            "color": "#06b6d4",
            "inputType": "any",
            "outputType": "any",
            "configFields": [
                {"name": "name", "label": "Name", "fieldType": "string", "required": False},
                {"name": "assignments", "label": "Assignments", "fieldType": "assignment_list", "required": True,
                 "description": "Typed state assignments with literal/expression or ValueRef sources"},
                {"name": "is_expression", "label": "Values are Expressions", "fieldType": "boolean", "required": False, "default": True}
            ]
        }
    ))
    AgentExecutorRegistry.register("set_state", SetStateNodeExecutor)

    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="speech_to_text",
        category="data",
        display_name="Speech to Text",
        description="Transcribe audio attachments through a speech-to-text model.",
        reads=[AgentStateField.STATE_VARIABLES, AgentStateField.CONTEXT],
        writes=[AgentStateField.CONTEXT],
        config_schema={
            "type": "object",
            "properties": {
                "model_id": {"type": "string"},
                "source": {"type": "object", "additionalProperties": True},
                "language_hints": {
                    "anyOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"type": "string"},
                    ]
                },
                "prompt": {"type": "string"},
            },
            "required": ["source"],
            "additionalProperties": True,
        },
        field_contracts={
            "source": {
                "type": "value_ref",
                "allowed_types": ["list", "object", "unknown"],
                "allowed_semantic_types": ["audio", "audio_attachments", "audio_attachment"],
            },
        },
        output_contract={
            "fields": [
                {"key": "text", "type": "string", "label": "Text"},
                {"key": "segments", "type": "list", "label": "Segments"},
                {"key": "language", "type": "string", "label": "Language"},
                {"key": "attachments", "type": "list", "label": "Attachments"},
                {"key": "provider_metadata", "type": "object", "label": "Provider Metadata"},
            ]
        },
        ui={
            "icon": "Mic",
            "color": "#0f766e",
            "inputType": "any",
            "outputType": "context",
            "configFields": [
                {"name": "model_id", "label": "STT Model", "fieldType": "model", "required": False, "description": "Defaults to the tenant/global speech-to-text model"},
                {"name": "source", "label": "Audio Source", "fieldType": "value_ref", "required": True, "description": "Select workflow_input.audio or another audio attachment value"},
                {"name": "language_hints", "label": "Language Hints", "fieldType": "text", "required": False, "description": "Optional comma-separated language codes"},
                {"name": "prompt", "label": "Prompt", "fieldType": "text", "required": False, "description": "Optional provider hint text"},
            ],
        }
    ))
    AgentExecutorRegistry.register("speech_to_text", SpeechToTextNodeExecutor)

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
    # Orchestration (GraphSpec v2)
    # =========================================================================

    from app.agent.executors.orchestration import (
        CancelSubtreeNodeExecutor,
        JudgeNodeExecutor,
        JoinNodeExecutor,
        ReplanNodeExecutor,
        RouterNodeExecutor,
        SpawnGroupNodeExecutor,
        SpawnRunNodeExecutor,
    )

    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="spawn_run",
        category="orchestration",
        display_name="Spawn Run",
        description="Spawn a single child run through the orchestration kernel",
        reads=[AgentStateField.STATE_VARIABLES, AgentStateField.CONTEXT],
        writes=[AgentStateField.CONTEXT],
        config_schema={
            "type": "object",
            "properties": {
                "target_agent_id": {"type": "string"},
                "target_agent_slug": {"type": "string"},
                "mapped_input_payload": {"type": "object"},
                "scope_subset": {"type": "array", "items": {"type": "string"}},
                "idempotency_key": {"type": "string"},
                "failure_policy": {"type": "string"},
                "timeout_s": {"type": "number"},
                "start_background": {"type": "boolean", "default": True},
            },
        },
        ui={
            "icon": "GitBranch",
            "color": "#93c5fd",
            "inputType": "context",
            "outputType": "context",
            "configFields": [
                {"name": "target_agent_slug", "label": "Target Agent", "fieldType": "agent_select", "required": False, "visibility": "simple", "group": "what_to_run"},
                {"name": "target_agent_id", "label": "Target Agent (ID)", "fieldType": "agent_select", "required": False, "visibility": "advanced", "group": "what_to_run", "helpKind": "runtime-internal"},
                {"name": "scope_subset", "label": "Scope Subset", "fieldType": "scope_subset", "required": True, "visibility": "simple", "group": "permissions", "helpKind": "required-for-compile"},
                {"name": "idempotency_key", "label": "Idempotency Key", "fieldType": "string", "required": False, "visibility": "advanced", "group": "reliability", "helpKind": "runtime-internal"},
                {
                    "name": "failure_policy",
                    "label": "Failure Policy",
                    "fieldType": "select",
                    "required": False,
                    "default": "best_effort",
                    "visibility": "advanced",
                    "group": "reliability",
                    "helpKind": "runtime-internal",
                    "options": [
                        {"value": "best_effort", "label": "Best Effort"},
                        {"value": "fail_fast", "label": "Fail Fast"},
                    ],
                },
                {"name": "timeout_s", "label": "Timeout (seconds)", "fieldType": "number", "required": False, "visibility": "advanced", "group": "reliability"},
                {"name": "start_background", "label": "Start in Background", "fieldType": "boolean", "required": False, "default": True, "visibility": "advanced", "group": "reliability", "helpKind": "runtime-internal"},
            ],
        },
    ))
    AgentExecutorRegistry.register("spawn_run", SpawnRunNodeExecutor)

    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="spawn_group",
        category="orchestration",
        display_name="Spawn Group",
        description="Spawn a fanout group of child runs through the orchestration kernel",
        reads=[AgentStateField.STATE_VARIABLES, AgentStateField.CONTEXT],
        writes=[AgentStateField.CONTEXT],
        config_schema={
            "type": "object",
            "properties": {
                "targets": {"type": "array", "items": {"type": "object"}},
                "scope_subset": {"type": "array", "items": {"type": "string"}},
                "idempotency_key_prefix": {"type": "string"},
                "failure_policy": {"type": "string"},
                "join_mode": {
                    "type": "string",
                    "enum": ["all", "best_effort", "fail_fast", "quorum", "first_success"],
                    "default": "all",
                },
                "quorum_threshold": {"type": "number"},
                "timeout_s": {"type": "number"},
                "start_background": {"type": "boolean", "default": True},
            },
        },
        ui={
            "icon": "GitMerge",
            "color": "#93c5fd",
            "inputType": "context",
            "outputType": "context",
            "configFields": [
                {"name": "targets", "label": "Targets", "fieldType": "spawn_targets", "required": True, "visibility": "simple", "group": "what_to_run", "helpKind": "required-for-compile"},
                {"name": "scope_subset", "label": "Scope Subset", "fieldType": "scope_subset", "required": True, "visibility": "simple", "group": "permissions", "helpKind": "required-for-compile"},
                {
                    "name": "join_mode",
                    "label": "Join Mode",
                    "fieldType": "select",
                    "required": False,
                    "default": "all",
                    "visibility": "simple",
                    "group": "routing",
                    "options": [
                        {"value": "all", "label": "All"},
                        {"value": "best_effort", "label": "Best Effort"},
                        {"value": "fail_fast", "label": "Fail Fast"},
                        {"value": "quorum", "label": "Quorum"},
                        {"value": "first_success", "label": "First Success"},
                    ],
                },
                {"name": "quorum_threshold", "label": "Quorum Threshold", "fieldType": "number", "required": False, "visibility": "simple", "group": "routing", "dependsOn": {"field": "join_mode", "equals": "quorum"}},
                {"name": "timeout_s", "label": "Timeout (seconds)", "fieldType": "number", "required": False, "visibility": "advanced", "group": "reliability"},
                {"name": "idempotency_key_prefix", "label": "Idempotency Key Prefix", "fieldType": "string", "required": False, "visibility": "advanced", "group": "reliability", "helpKind": "runtime-internal"},
                {
                    "name": "failure_policy",
                    "label": "Failure Policy",
                    "fieldType": "select",
                    "required": False,
                    "default": "best_effort",
                    "visibility": "advanced",
                    "group": "reliability",
                    "helpKind": "runtime-internal",
                    "options": [
                        {"value": "best_effort", "label": "Best Effort"},
                        {"value": "fail_fast", "label": "Fail Fast"},
                    ],
                },
                {"name": "start_background", "label": "Start in Background", "fieldType": "boolean", "required": False, "default": True, "visibility": "advanced", "group": "reliability", "helpKind": "runtime-internal"},
            ],
        },
    ))
    AgentExecutorRegistry.register("spawn_group", SpawnGroupNodeExecutor)

    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="join",
        category="orchestration",
        display_name="Join",
        description="Join an orchestration group and route by completion status",
        reads=[AgentStateField.CONTEXT],
        writes=[AgentStateField.ROUTING_KEY, AgentStateField.BRANCH_TAKEN, AgentStateField.CONTEXT],
        config_schema={
            "type": "object",
            "properties": {
                "orchestration_group_id": {"type": "string"},
                "mode": {
                    "type": "string",
                    "enum": ["all", "best_effort", "fail_fast", "quorum", "first_success"],
                    "default": "all",
                },
                "quorum_threshold": {"type": "number"},
                "timeout_s": {"type": "number"},
            },
        },
        ui={
            "icon": "Link",
            "color": "#93c5fd",
            "inputType": "context",
            "outputType": "decision",
            "dynamicHandles": True,
            "configFields": [
                {"name": "orchestration_group_id", "label": "Group ID", "fieldType": "string", "required": False, "visibility": "advanced", "group": "what_to_run", "helpKind": "runtime-internal"},
                {
                    "name": "mode",
                    "label": "Mode",
                    "fieldType": "select",
                    "required": False,
                    "default": "all",
                    "visibility": "simple",
                    "group": "routing",
                    "options": [
                        {"value": "all", "label": "All"},
                        {"value": "best_effort", "label": "Best Effort"},
                        {"value": "fail_fast", "label": "Fail Fast"},
                        {"value": "quorum", "label": "Quorum"},
                        {"value": "first_success", "label": "First Success"},
                    ],
                },
                {"name": "quorum_threshold", "label": "Quorum Threshold", "fieldType": "number", "required": False, "visibility": "simple", "group": "routing", "dependsOn": {"field": "mode", "equals": "quorum"}},
                {"name": "timeout_s", "label": "Timeout (seconds)", "fieldType": "number", "required": False, "visibility": "advanced", "group": "reliability"},
            ],
        },
    ))
    AgentExecutorRegistry.register("join", JoinNodeExecutor)

    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="router",
        category="orchestration",
        display_name="Router",
        description="Route orchestration payload to named branches",
        reads=[AgentStateField.CONTEXT],
        writes=[AgentStateField.ROUTING_KEY, AgentStateField.BRANCH_TAKEN],
        ui={
            "icon": "Route",
            "color": "#93c5fd",
            "inputType": "context",
            "outputType": "decision",
            "dynamicHandles": True,
            "configFields": [
                {"name": "route_key", "label": "Route Key", "fieldType": "string", "required": False, "default": "status", "visibility": "simple", "group": "routing"},
                {"name": "routes", "label": "Routes", "fieldType": "route_table", "required": False, "visibility": "simple", "group": "routing"},
            ],
        },
    ))
    AgentExecutorRegistry.register("router", RouterNodeExecutor)

    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="judge",
        category="orchestration",
        display_name="Judge",
        description="Decide orchestration pass/fail branches",
        reads=[AgentStateField.CONTEXT],
        writes=[AgentStateField.ROUTING_KEY, AgentStateField.BRANCH_TAKEN],
        ui={
            "icon": "Scale",
            "color": "#93c5fd",
            "inputType": "context",
            "outputType": "decision",
            "dynamicHandles": True,
            "configFields": [
                {"name": "outcomes", "label": "Outcomes", "fieldType": "route_table", "required": False, "visibility": "simple", "group": "routing"},
                {"name": "pass_outcome", "label": "Pass Branch Label", "fieldType": "string", "required": False, "default": "pass", "visibility": "advanced", "group": "routing", "helpKind": "runtime-internal"},
                {"name": "fail_outcome", "label": "Fail Branch Label", "fieldType": "string", "required": False, "default": "fail", "visibility": "advanced", "group": "routing", "helpKind": "runtime-internal"},
            ],
        },
    ))
    AgentExecutorRegistry.register("judge", JudgeNodeExecutor)

    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="replan",
        category="orchestration",
        display_name="Replan",
        description="Evaluate subtree and decide replan vs continue",
        reads=[AgentStateField.CONTEXT],
        writes=[AgentStateField.ROUTING_KEY, AgentStateField.BRANCH_TAKEN, AgentStateField.CONTEXT],
        ui={
            "icon": "RefreshCw",
            "color": "#93c5fd",
            "inputType": "context",
            "outputType": "decision",
            "dynamicHandles": True,
            "configFields": [
                {"name": "run_id", "label": "Run ID", "fieldType": "string", "required": False, "visibility": "advanced", "group": "what_to_run", "helpKind": "runtime-internal"},
            ],
        },
    ))
    AgentExecutorRegistry.register("replan", ReplanNodeExecutor)

    AgentOperatorRegistry.register(AgentOperatorSpec(
        type="cancel_subtree",
        category="orchestration",
        display_name="Cancel Subtree",
        description="Cancel a child run subtree through the orchestration kernel",
        reads=[AgentStateField.CONTEXT],
        writes=[AgentStateField.CONTEXT],
        ui={
            "icon": "Ban",
            "color": "#93c5fd",
            "inputType": "context",
            "outputType": "context",
            "configFields": [
                {"name": "run_id", "label": "Run ID", "fieldType": "string", "required": False, "visibility": "advanced", "group": "what_to_run", "helpKind": "runtime-internal"},
                {"name": "include_root", "label": "Include Root Run", "fieldType": "boolean", "required": False, "default": True, "visibility": "advanced", "group": "reliability", "helpKind": "runtime-internal"},
                {"name": "reason", "label": "Reason", "fieldType": "string", "required": False, "visibility": "advanced", "group": "reliability"},
            ],
        },
    ))
    AgentExecutorRegistry.register("cancel_subtree", CancelSubtreeNodeExecutor)

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
        output_contract={
            "fields": [
                {"key": "result", "type": "unknown", "label": "Result"},
            ]
        },
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
        output_contract={
            "fields": [
                {"key": "results", "type": "list", "label": "Results"},
                {"key": "documents", "type": "list", "label": "Documents"},
            ]
        },
        ui={
            "icon": "Search",
            "color": "#3b82f6",
            "inputType": "message",
            "outputType": "context",
            "configFields": [
                {"name": "pipeline_id", "label": "Retrieval Pipeline", "fieldType": "retrieval_pipeline_select", "required": True, "description": "Select a Retrieval Pipeline"},
                {"name": "query", "label": "Query Template", "fieldType": "template_string", "required": False, 
                 "description": "Query with @variable interpolation. Leave empty to use last message.", "prompt_capable": True, "prompt_surface": "rag.query"},
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
        output_contract={
            "fields": [
                {"key": "results", "type": "list", "label": "Results"},
                {"key": "documents", "type": "list", "label": "Documents"},
            ]
        },
        ui={
            "icon": "Database",
            "color": "#3b82f6",
            "inputType": "message",
            "outputType": "context",
            "configFields": [
                {"name": "knowledge_store_id", "label": "Knowledge Store", "fieldType": "knowledge_store_select", "required": True, "description": "Select a Knowledge Store"},
                {"name": "query", "label": "Query Template", "fieldType": "template_string", "required": False, 
                 "description": "Query with @variable interpolation. Leave empty to use last message.", "prompt_capable": True, "prompt_surface": "vector_search.query"},
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
        output_contract={
            "fields": [
                {"key": "approved", "type": "boolean", "label": "Approved"},
                {"key": "comment", "type": "string", "label": "Comment"},
            ]
        },
        ui={
            "icon": "UserCheck",
            "color": "#10b981",
            "inputType": "any",
            "outputType": "decision",
            "staticHandles": ["approve", "reject"],
            "configFields": [
                {"name": "name", "label": "Name", "fieldType": "string", "required": False},
                {"name": "message", "label": "Message", "fieldType": "template_string", "required": False, 
                 "description": "Message shown to user with @variable support", "prompt_capable": True, "prompt_surface": "user_approval.message"},
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
        output_contract={
            "fields": [
                {"key": "input_text", "type": "string", "label": "Input Text"},
            ]
        },
        ui={
            "icon": "UserCheck",
            "color": "#059669",  # Darker green to indicate legacy
            "inputType": "any",
            "outputType": "message",
            "configFields": [
                {"name": "prompt", "label": "Prompt", "fieldType": "text", "required": False, "description": "Message shown to the human reviewer", "prompt_capable": True, "prompt_surface": "human_input.prompt"},
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
    """Repo-backed artifact operator registration has been removed."""
    return None
 
