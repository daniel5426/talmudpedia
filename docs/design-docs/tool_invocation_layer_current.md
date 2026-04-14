# Tool Invocation Layer Current

Last Updated: 2026-04-13

This document is the canonical design reference for the unified tool invocation layer.

## Core Decision

All tool backends now execute through one shared invocation contract:
- `ToolRegistry.schema.input` is the authoritative model-authored argument schema.
- every call is split into `model_input` and `runtime_context`
- argument compilation happens before backend dispatch
- validation is `strict` by default for every tool type
- the only opt-out is `execution.validation_mode = "none"`

This is a hard cut. The executor no longer performs generic wrapper recovery, alias flattening, or JSON-string payload rescue.

## Canonical Envelope

Every tool execution is represented internally as:
- `tool_descriptor`
  - tool id, slug, name, implementation type, schema, config
- `model_input_raw`
  - model-authored arguments after runtime metadata is stripped out
- `model_input_compiled`
  - compiled arguments used for dispatch
- `runtime_context`
  - run, thread, tenant, user, auth, model-resolution, and orchestration metadata
- `execution_policy`
  - validation mode and timeout

Rule:
- only `model_input_raw` is compiled against `schema.input`
- `runtime_context` never participates in schema validation

## Validation Model

Canonical execution modes:
- `strict`
- `none`

Rules:
- default is `strict`
- `execution.strict_input_schema` is removed
- MCP and HTTP tools use the same validation contract as native/function tools

## Argument Compiler

The compiler:
- sanitizes the authoritative schema
- validates model input once
- rejects missing fields, unexpected fields, wrong types, enum mismatches, and schema-branch mismatches
- strips executor-owned runtime metadata before validation
- never flattens wrappers such as `args`, `input`, `parameters`, `payload`, `data`, `arguments`, or `value`

Compile failures return a shared envelope with:
- `code = TOOL_ARGUMENT_COMPILE_FAILED`
- stable issue codes such as:
  - `missing_required_field`
  - `unexpected_field`
  - `wrong_type`
  - `invalid_enum`
  - `schema_branch_mismatch`
  - `invalid_tool_schema`

## Backend Dispatch

After compilation:
- function tools receive compiled args plus `__tool_runtime_context__`
- native platform tools execute as strict function tools backed by native backend dispatch
- MCP tools send compiled args as `arguments`
- HTTP tools dispatch compiled args only
- artifact, agent-call, and rag-pipeline paths consume compiled args only

## Trace Anatomy

Tool execution traces now record:
- tool id / slug / implementation type
- validation mode
- raw model input
- stripped runtime metadata keys
- runtime-context key presence
- compiled input or compile failure
- backend dispatch target
- final result or failure category

Sensitive runtime values should be redacted or represented as presence-only.

## Hard-Cut Removals

Removed from the generic executor path:
- `execution.strict_input_schema`
- wrapped payload recovery
- scalar-to-wrapper recovery
- JSON-string payload decoding
- strict-platform special-case wrapper rescue

## Implementation References

- `backend/app/agent/execution/tool_invocation.py`
- `backend/app/agent/execution/tool_input_contracts.py`
- `backend/app/agent/executors/tool.py`
- `backend/app/agent/executors/standard.py`
- `backend/app/api/routers/tools.py`
