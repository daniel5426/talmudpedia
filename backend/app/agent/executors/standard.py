import asyncio
import logging
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.agent.executors.base import BaseNodeExecutor, ValidationResult
from app.agent.registry import AgentOperatorRegistry, AgentOperatorSpec, AgentStateField, AgentExecutorRegistry
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, create_model
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

        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        node_id = context.get("node_id", "start") if context else "start"
        node_name = context.get("node_name", "Start") if context else "Start"
        if emitter:
            emitter.emit_node_start(
                node_id,
                node_name,
                "start",
                {"state_variables": len(state_vars), "input_variables": len(input_vars)},
            )
        
        initial_state = {}
        
        # Set up state variables with defaults
        for var in state_vars:
            name = var.get("name")
            default = var.get("default")
            if name:
                initial_state[name] = default
        
        # Input variables are expected to come from the user input
        # They're defined here for documentation/validation
        
        result = {"state": initial_state} if initial_state else {}
        if emitter:
            emitter.emit_node_end(node_id, node_name, "start", {"keys": list(result.keys())})
        return result


class EndNodeExecutor(BaseNodeExecutor):
    """
    Exit point executor.
    Extracts specified output from state.
    """
    
    async def execute(self, state: Dict[str, Any], config: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        logger.debug("Executing END node")
        
        output_variable = config.get("output_variable")
        output_message = config.get("output_message")

        from app.agent.execution.emitter import active_emitter
        emitter = active_emitter.get()
        node_id = context.get("node_id", "end") if context else "end"
        node_name = context.get("node_name", "End") if context else "End"
        if emitter:
            emitter.emit_node_start(
                node_id,
                node_name,
                "end",
                {"output_variable": output_variable, "has_output_message": bool(output_message)},
            )
        
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
        
        if emitter:
            emitter.emit_node_end(node_id, node_name, "end", {"has_output": bool(result)})
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
        if isinstance(config_schema, dict):
            return config_schema
        if isinstance(config_schema, str):
            try:
                parsed = json.loads(config_schema)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    def _parse_tool_input_schema(self, tool: Any) -> Dict[str, Any]:
        schema = getattr(tool, "schema", {}) or {}
        if isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except Exception:
                schema = {}
        if not isinstance(schema, dict):
            return {}
        input_schema = schema.get("input") or {}
        return input_schema if isinstance(input_schema, dict) else {}

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
        _coerce_string_alias(
            "checkpoint_revision_id",
            (
                "checkpoint_revision_id",
                "checkpointRevisionId",
                "checkpoint_id",
                "checkpointId",
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
        config_schema = self._parse_config_schema(getattr(tool, "config_schema", {}) or {})
        execution = config_schema.get("execution") if isinstance(config_schema, dict) else {}
        if not isinstance(execution, dict):
            execution = {}
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
        schema = getattr(tool, "schema", {}) or {}
        if isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except Exception:
                schema = {}
        input_schema = schema.get("input", {}) if isinstance(schema, dict) else {}

        args_schema: type[BaseModel]
        if isinstance(input_schema, dict) and input_schema.get("properties"):
            props = input_schema.get("properties", {}) or {}
            required = set(input_schema.get("required", []) or [])
            fields: Dict[str, Any] = {}
            for prop_name, prop_spec in props.items():
                default = ... if prop_name in required else None
                description = None
                if isinstance(prop_spec, dict):
                    desc_raw = prop_spec.get("description")
                    if isinstance(desc_raw, str) and desc_raw.strip():
                        description = desc_raw.strip()
                field_def = Field(default=default, description=description) if description else default
                fields[prop_name] = (Any, field_def)
            model_name = tool_name.title().replace("-", "_").replace(" ", "_")
            args_schema = create_model(f"{model_name}Args", **fields)
        else:
            model_name = tool_name.title().replace("-", "_").replace(" ", "_")
            args_schema = create_model(f"{model_name}Args", input=(Any, ...))

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
        return result.scalars().all()

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
    ) -> tuple[str, Optional[BaseMessage]]:
        if str(full_content).strip() or has_tool_signals:
            return full_content, last_message

        try:
            fallback_response = await adapter.ainvoke(
                [
                    *conversation_messages,
                    HumanMessage(
                        content="Respond to the user directly in plain text. Do not call tools. Keep it concise.",
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
                return fallback_text, fallback_response
            return full_content, fallback_response
        except Exception as exc:
            logger.warning(f"Fallback text response generation failed: {exc}")
            return full_content, last_message

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

            if emitter:
                emitter.emit_node_start(node_id, node_name, "agent", {
                    "model": model_id,
                    "reasoning_effort": reasoning_effort,
                    "tools_count": len(tools),
                    "tool_execution_mode": tool_execution_mode,
                })

            tool_records = await self._load_tool_records(tools)
            tool_records_by_id = {str(t.id): t for t in tool_records if getattr(t, "id", None)}
            langchain_tools = [self._build_langchain_tool(t) for t in tool_records] if tools else []
            platform_sdk_defaulted_once = False

            conversation_messages = list(formatted_messages)
            emitted_messages: List[BaseMessage] = []
            tool_outputs: List[Any] = []
            last_context: Any = None
            last_agent_output: Any = None

            for iteration in range(max_tool_iterations):
                full_content = ""
                tool_call_buffers: Dict[str, Dict[str, Any]] = {}
                tool_call_order: List[str] = []
                last_message: Optional[BaseMessage] = None

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
                    if emitter:
                        emitter.emit_token(full_content, node_id)
                    last_message = response

                has_tool_signals = bool(tool_call_buffers)
                if last_message is not None and getattr(last_message, "tool_calls", None):
                    has_tool_signals = True
                full_content, last_message = await self._ensure_text_response(
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

                if emitter:
                    emitter.emit_node_end(node_id, node_name, "agent", {"content_length": len(full_content)})

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
                    if not tool_call and isinstance(result_content, dict):
                        tool_call = self._normalize_tool_call(result_content)
                    if tool_call:
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

                        if not isinstance(call_args, dict):
                            call_args = {"value": call_args}

                        if not call_name and call_tool_id:
                            tool_record = tool_records_by_id.get(str(call_tool_id))
                            call_name = getattr(tool_record, "slug", None) or getattr(tool_record, "name", None)

                        if not call_name:
                            continue

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

                if not tool_calls:
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
                            tools,
                        )
                    if not resolved_tool_id:
                        logger.warning(f"Unresolved tool call: {tool_name or tool_id}")
                        continue

                    tool_input = call.get("args") or call.get("input") or {}
                    if not isinstance(tool_input, dict):
                        tool_input = {"value": tool_input}

                    tool_record = tool_records_by_id.get(resolved_tool_id)
                    if tool_record is not None:
                        tool_input = self._coerce_tool_input(tool_input, tool_record)
                    if (not tool_input) and tool_record is not None:
                        tool_slug = str(getattr(tool_record, "slug", "") or "").lower()
                        tool_name_lower = str(getattr(tool_record, "name", "") or "").lower()
                        artifact_id = str(getattr(tool_record, "artifact_id", "") or "")
                        is_platform_sdk = (
                            tool_slug == "platform-sdk"
                            or tool_name_lower == "platform sdk"
                            or artifact_id == "builtin/platform_sdk"
                        )
                        if is_platform_sdk:
                            if not platform_sdk_defaulted_once:
                                tool_input = {"action": "fetch_catalog"}
                                platform_sdk_defaulted_once = True
                                logger.info("Defaulted empty Platform SDK tool call to fetch_catalog")
                            else:
                                tool_input = {
                                    "action": "respond",
                                    "message": "Missing explicit Platform SDK action in tool call.",
                                }
                                logger.warning("Repeated empty Platform SDK tool call; forcing respond action")
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
                        # Include per-call id so emitter span_id is unique for each tool invocation.
                        "node_id": f"{node_id}::tool::{call['tool_id']}::{call['call_id']}",
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
                "error": error_msg,
            }

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
                "tools": {"type": "array", "items": {"type": "string"}, "title": "Tools"},
                "tool_execution_mode": {"type": "string", "title": "Tool Execution Mode", "enum": ["sequential", "parallel_safe"], "default": "sequential"},
                "max_parallel_tools": {"type": "number", "title": "Max Parallel Tools", "default": 4},
                "tool_timeout_s": {"type": "number", "title": "Tool Timeout (s)", "default": 60},
                "max_tool_iterations": {"type": "number", "title": "Max Tool Iterations", "default": 10}
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
 
