from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.agent.execution.tool_input_contracts import (
    get_tool_validation_mode,
    summarize_validation_errors,
    validate_tool_input_against_schema,
)

VALIDATION_MODE_STRICT = "strict"
VALIDATION_MODE_NONE = "none"
TOOL_ARGUMENT_COMPILE_FAILED = "TOOL_ARGUMENT_COMPILE_FAILED"

TOOL_RUNTIME_CONTEXT_KEYS = {
    "node_id",
    "source_node_id",
    "tool_call_id",
    "run_id",
    "thread_id",
    "tenant_id",
    "user_id",
    "initiator_user_id",
    "requested_scopes",
    "root_run_id",
    "parent_run_id",
    "parent_node_id",
    "depth",
    "agent_id",
    "agent_slug",
    "mode",
    "surface",
    "orchestration_surface",
    "quota_max_output_tokens",
    "token",
    "published_app_id",
    "published_app_account_id",
    "external_user_id",
    "external_session_id",
    "tenant_api_key_id",
    "resource_policy_snapshot",
    "resource_policy_principal",
    "architect_mode",
    "architect_effective_scopes",
    "execution_mode",
    "requested_model_id",
    "resolved_model_id",
    "resolved_binding_id",
    "resolved_provider",
    "resolved_provider_model_id",
}


@dataclass(slots=True)
class ToolDescriptor:
    tool_id: str
    tool_slug: str | None
    tool_name: str | None
    implementation_type: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    config_schema: dict[str, Any]
    implementation_config: dict[str, Any]
    execution_config: dict[str, Any]


@dataclass(slots=True)
class ToolExecutionPolicy:
    validation_mode: str
    timeout_s: int | None


@dataclass(slots=True)
class ToolInvocationEnvelope:
    tool_descriptor: ToolDescriptor
    model_input_raw: Any
    runtime_context: dict[str, Any]
    execution_policy: ToolExecutionPolicy
    model_input_compiled: Any = None
    stripped_runtime_metadata_keys: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ToolCompileFailure:
    code: str
    error: str
    compile_error_code: str
    validation_summary: str | None
    validation_errors: list[dict[str, Any]]
    received_keys: list[str]
    tool_id: str
    tool_slug: str | None
    implementation_type: str
    validation_mode: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "error": self.error,
            "compile_error_code": self.compile_error_code,
            "validation_summary": self.validation_summary,
            "validation_errors": self.validation_errors,
            "received_keys": self.received_keys,
            "tool_id": self.tool_id,
            "tool_slug": self.tool_slug,
            "implementation_type": self.implementation_type,
            "validation_mode": self.validation_mode,
        }


def _schema_properties(schema: dict[str, Any]) -> set[str]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return set()
    return {str(key) for key in properties.keys()}


def _extract_runtime_context(node_context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(node_context, dict):
        return {}
    return {
        key: value
        for key, value in node_context.items()
        if key in TOOL_RUNTIME_CONTEXT_KEYS and value is not None
    }


def _split_model_input_and_runtime_metadata(
    raw_input: Any,
    *,
    declared_keys: set[str],
) -> tuple[Any, dict[str, Any], list[str]]:
    if not isinstance(raw_input, dict):
        return raw_input, {}, []

    model_input: dict[str, Any] = {}
    leaked_runtime: dict[str, Any] = {}
    stripped_keys: list[str] = []
    for key, value in raw_input.items():
        if key in TOOL_RUNTIME_CONTEXT_KEYS and key not in declared_keys:
            leaked_runtime[key] = value
            stripped_keys.append(str(key))
            continue
        model_input[key] = value
    return model_input, leaked_runtime, stripped_keys


def build_tool_invocation_envelope(
    *,
    tool: Any,
    raw_input: Any,
    node_context: dict[str, Any] | None,
    implementation_type: str,
    config_schema: dict[str, Any],
    implementation_config: dict[str, Any],
    execution_config: dict[str, Any],
) -> ToolInvocationEnvelope:
    schema = getattr(tool, "schema", {}) or {}
    input_schema = schema.get("input") if isinstance(schema, dict) else {}
    output_schema = schema.get("output") if isinstance(schema, dict) else {}
    descriptor = ToolDescriptor(
        tool_id=str(getattr(tool, "id", "") or ""),
        tool_slug=str(getattr(tool, "slug", "") or "").strip() or None,
        tool_name=str(getattr(tool, "name", "") or "").strip() or None,
        implementation_type=implementation_type,
        input_schema=input_schema if isinstance(input_schema, dict) else {},
        output_schema=output_schema if isinstance(output_schema, dict) else {},
        config_schema=config_schema if isinstance(config_schema, dict) else {},
        implementation_config=implementation_config if isinstance(implementation_config, dict) else {},
        execution_config=execution_config if isinstance(execution_config, dict) else {},
    )
    declared_keys = _schema_properties(descriptor.input_schema)
    model_input_raw, leaked_runtime, stripped_keys = _split_model_input_and_runtime_metadata(
        raw_input,
        declared_keys=declared_keys,
    )
    runtime_context = {
        **_extract_runtime_context(node_context),
        **{key: value for key, value in leaked_runtime.items() if value is not None},
    }
    timeout_raw = descriptor.execution_config.get("timeout_s")
    timeout_s = int(timeout_raw) if isinstance(timeout_raw, (int, float, str)) and str(timeout_raw).strip() else None
    return ToolInvocationEnvelope(
        tool_descriptor=descriptor,
        model_input_raw=model_input_raw,
        runtime_context=runtime_context,
        execution_policy=ToolExecutionPolicy(
            validation_mode=get_tool_validation_mode(tool),
            timeout_s=timeout_s,
        ),
        stripped_runtime_metadata_keys=stripped_keys,
    )


def compile_tool_arguments(envelope: ToolInvocationEnvelope) -> ToolCompileFailure | None:
    if envelope.execution_policy.validation_mode == VALIDATION_MODE_NONE:
        envelope.model_input_compiled = envelope.model_input_raw
        return None

    validation_errors = validate_tool_input_against_schema(
        envelope.tool_descriptor.input_schema,
        envelope.model_input_raw,
        tool_name=envelope.tool_descriptor.tool_slug or envelope.tool_descriptor.tool_name,
    )
    if validation_errors:
        primary_code = str(validation_errors[0].get("code") or "invalid_tool_input")
        return ToolCompileFailure(
            code=TOOL_ARGUMENT_COMPILE_FAILED,
            error="Tool argument compilation failed",
            compile_error_code=primary_code,
            validation_summary=summarize_validation_errors(validation_errors),
            validation_errors=validation_errors,
            received_keys=sorted(str(key) for key in envelope.model_input_raw.keys()) if isinstance(envelope.model_input_raw, dict) else [],
            tool_id=envelope.tool_descriptor.tool_id,
            tool_slug=envelope.tool_descriptor.tool_slug,
            implementation_type=envelope.tool_descriptor.implementation_type,
            validation_mode=envelope.execution_policy.validation_mode,
        )

    envelope.model_input_compiled = envelope.model_input_raw
    return None


def tool_dispatch_target(envelope: ToolInvocationEnvelope) -> str:
    impl_type = envelope.tool_descriptor.implementation_type
    implementation = envelope.tool_descriptor.implementation_config
    if impl_type == "function":
        return f"function:{implementation.get('function_name') or 'unknown'}"
    if impl_type == "mcp":
        return f"mcp:{implementation.get('tool_name') or implementation.get('server_id') or 'unknown'}"
    if impl_type == "http":
        method = str(implementation.get("method") or "POST").upper()
        return f"http:{method} {implementation.get('url') or ''}".strip()
    if impl_type == "artifact":
        return f"artifact:{implementation.get('artifact_id') or envelope.tool_descriptor.tool_id}"
    if impl_type == "rag_pipeline":
        return f"rag_pipeline:{implementation.get('pipeline_id') or envelope.tool_descriptor.tool_id}"
    if impl_type == "agent_call":
        return f"agent_call:{implementation.get('target_agent_slug') or implementation.get('target_agent_id') or 'unknown'}"
    return impl_type
