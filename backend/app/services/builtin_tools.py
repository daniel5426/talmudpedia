from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from app.db.postgres.models.registry import ToolImplementationType


BUILTIN_TOOLS_V1_ENV = "BUILTIN_TOOLS_V1"


def is_builtin_tools_v1_enabled() -> bool:
    raw = os.getenv(BUILTIN_TOOLS_V1_ENV, "1")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class BuiltinToolTemplateSpec:
    key: str
    name: str
    slug: str
    description: str
    implementation_type: ToolImplementationType
    implementation: dict[str, Any]
    execution: dict[str, Any]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


def _base_io_schema() -> tuple[dict[str, Any], dict[str, Any]]:
    input_schema = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }
    output_schema = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }
    return input_schema, output_schema


def _specs() -> list[BuiltinToolTemplateSpec]:
    specs: list[BuiltinToolTemplateSpec] = []

    retrieval_input = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 100},
            "filters": {"type": "object"},
        },
        "required": ["query"],
        "additionalProperties": False,
    }
    retrieval_output = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "pipeline_id": {"type": "string"},
            "results": {"type": "array", "items": {"type": "object"}},
            "count": {"type": "integer"},
        },
        "required": ["results"],
        "additionalProperties": True,
    }
    specs.append(
        BuiltinToolTemplateSpec(
            key="retrieval_pipeline",
            name="Retrieval Pipeline",
            slug="builtin-retrieval-pipeline",
            description="Query a tenant retrieval pipeline and return normalized results.",
            implementation_type=ToolImplementationType.RAG_RETRIEVAL,
            implementation={"type": "rag_retrieval", "pipeline_id": ""},
            execution={"timeout_s": 60, "is_pure": True, "concurrency_group": "retrieval", "max_concurrency": 2},
            input_schema=retrieval_input,
            output_schema=retrieval_output,
        )
    )

    http_input = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "method": {"type": "string"},
            "headers": {"type": "object"},
            "body": {},
            "params": {"type": "object"},
        },
        "required": ["url"],
        "additionalProperties": True,
    }
    http_output = {
        "type": "object",
        "properties": {
            "status_code": {"type": "integer"},
            "headers": {"type": "object"},
            "body": {},
        },
        "additionalProperties": True,
    }
    specs.append(
        BuiltinToolTemplateSpec(
            key="http_request",
            name="HTTP Request",
            slug="builtin-http-request",
            description="Perform an outbound HTTP request.",
            implementation_type=ToolImplementationType.HTTP,
            implementation={"type": "http", "method": "GET", "url": "", "headers": {}},
            execution={"timeout_s": 20, "is_pure": False, "concurrency_group": "network", "max_concurrency": 4},
            input_schema=http_input,
            output_schema=http_output,
        )
    )

    function_input, function_output = _base_io_schema()
    function_input["properties"] = {
        "args": {"type": "object"},
    }
    function_output["properties"] = {"result": {}}
    specs.append(
        BuiltinToolTemplateSpec(
            key="function_call",
            name="Function Call",
            slug="builtin-function-call",
            description="Invoke an allowlisted internal function tool.",
            implementation_type=ToolImplementationType.FUNCTION,
            implementation={"type": "function", "function_name": "echo"},
            execution={"timeout_s": 15, "is_pure": True, "concurrency_group": "function", "max_concurrency": 4},
            input_schema=function_input,
            output_schema=function_output,
        )
    )

    mcp_input, mcp_output = _base_io_schema()
    mcp_input["properties"] = {"arguments": {"type": "object"}}
    mcp_output["properties"] = {"result": {}}
    specs.append(
        BuiltinToolTemplateSpec(
            key="mcp_call",
            name="MCP Call",
            slug="builtin-mcp-call",
            description="Invoke a remote MCP tool over JSON-RPC.",
            implementation_type=ToolImplementationType.MCP,
            implementation={"type": "mcp", "server_url": "", "tool_name": ""},
            execution={"timeout_s": 15, "is_pure": False, "concurrency_group": "mcp", "max_concurrency": 4},
            input_schema=mcp_input,
            output_schema=mcp_output,
        )
    )

    web_fetch_input = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "method": {"type": "string"},
            "headers": {"type": "object"},
            "body": {},
        },
        "required": ["url"],
        "additionalProperties": False,
    }
    web_fetch_output = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "status_code": {"type": "integer"},
            "content_type": {"type": "string"},
            "text": {"type": "string"},
            "truncated": {"type": "boolean"},
        },
        "required": ["url", "status_code", "text"],
        "additionalProperties": True,
    }
    specs.append(
        BuiltinToolTemplateSpec(
            key="web_fetch",
            name="Web Fetch",
            slug="builtin-web-fetch",
            description="Fetch URL content with timeout and payload-size guardrails.",
            implementation_type=ToolImplementationType.CUSTOM,
            implementation={"type": "builtin", "builtin": "web_fetch", "timeout_s": 15, "max_bytes": 250000},
            execution={"timeout_s": 20, "is_pure": True, "concurrency_group": "network", "max_concurrency": 4},
            input_schema=web_fetch_input,
            output_schema=web_fetch_output,
        )
    )

    web_search_input = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
        },
        "required": ["query"],
        "additionalProperties": False,
    }
    web_search_output = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "results": {"type": "array", "items": {"type": "object"}},
            "provider": {"type": "string"},
        },
        "required": ["results"],
        "additionalProperties": True,
    }
    specs.append(
        BuiltinToolTemplateSpec(
            key="web_search",
            name="Web Search",
            slug="builtin-web-search",
            description="Search the web via pluggable provider (Serper first).",
            implementation_type=ToolImplementationType.CUSTOM,
            implementation={"type": "builtin", "builtin": "web_search", "provider": "serper", "credentials_ref": None},
            execution={"timeout_s": 20, "is_pure": True, "concurrency_group": "network", "max_concurrency": 4},
            input_schema=web_search_input,
            output_schema=web_search_output,
        )
    )

    json_transform_input = {
        "type": "object",
        "properties": {
            "data": {},
            "pick": {"type": "array", "items": {"type": "string"}},
            "mapping": {"type": "object"},
            "defaults": {"type": "object"},
        },
        "additionalProperties": True,
    }
    json_transform_output = {
        "type": "object",
        "properties": {"result": {}},
        "required": ["result"],
        "additionalProperties": True,
    }
    specs.append(
        BuiltinToolTemplateSpec(
            key="json_transform",
            name="JSON Transform",
            slug="builtin-json-transform",
            description="Apply deterministic pick/map transformations to JSON input.",
            implementation_type=ToolImplementationType.CUSTOM,
            implementation={"type": "builtin", "builtin": "json_transform"},
            execution={"timeout_s": 10, "is_pure": True, "concurrency_group": "transform", "max_concurrency": 8},
            input_schema=json_transform_input,
            output_schema=json_transform_output,
        )
    )

    datetime_input = {
        "type": "object",
        "properties": {
            "operation": {"type": "string"},
            "value": {"type": "string"},
            "timezone": {"type": "string"},
            "format": {"type": "string"},
            "amount": {"type": "integer"},
            "unit": {"type": "string"},
            "other": {"type": "string"},
        },
        "additionalProperties": False,
    }
    datetime_output = {
        "type": "object",
        "properties": {
            "operation": {"type": "string"},
            "result": {},
        },
        "required": ["operation", "result"],
        "additionalProperties": True,
    }
    specs.append(
        BuiltinToolTemplateSpec(
            key="datetime_utils",
            name="Datetime Utils",
            slug="builtin-datetime-utils",
            description="UTC/local time formatting and arithmetic helpers.",
            implementation_type=ToolImplementationType.CUSTOM,
            implementation={"type": "builtin", "builtin": "datetime_utils"},
            execution={"timeout_s": 5, "is_pure": True, "concurrency_group": "utility", "max_concurrency": 16},
            input_schema=datetime_input,
            output_schema=datetime_output,
        )
    )

    return specs


BUILTIN_TEMPLATE_SPECS = _specs()
BUILTIN_TEMPLATE_MAP = {spec.key: spec for spec in BUILTIN_TEMPLATE_SPECS}
