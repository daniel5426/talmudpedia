# Tools Domain Spec

Last Updated: 2026-03-17

This document is the canonical product/specification overview for the tools domain.

## Purpose

Tools are callable capabilities that agents can execute. The tools domain provides:
- tool registration and versioning
- execution metadata and guardrails
- multiple implementation types
- tenant/global visibility rules

In the current platform, the canonical tool registry is the DB-backed `ToolRegistry` domain exposed at `/tools`.
The small in-process helper in `backend/app/services/tool_function_registry.py` is only a function-dispatch map for `FUNCTION` tools, not the canonical registry for the tools domain.

## Current Tool Classes

Current derived tool classes are:
- `built_in`
- `mcp`
- `artifact`
- `custom`

This classification is derived at the API layer rather than stored directly as a database column.

## Current Canonical Registry Shape

The logical tool record lives in `tool_registry` and currently carries:
- identity, scope, and visibility
- input/output schema
- config/execution metadata
- implementation type
- publish/version state
- optional artifact binding fields

Important current detail:
- artifact-backed tools are still first-class tool records
- artifacts do not replace the tool registry row
- the tool registry row owns tool identity, visibility, publish lifecycle, and agent-facing tool selection
- the artifact runtime owns executable code packaging and execution for artifact-backed tools

## Current Implementation Types

Current implementation types include:
- `internal`
- `http`
- `rag_retrieval`
- `agent_call`
- `function`
- `custom`
- `artifact`
- `mcp`

## Current API Surface

The main tools API is mounted at:
- `/tools`

Current behavior includes:
- tenant + global tool listing
- create/update/publish/version flows
- tool-type filtering
- sensitive config redaction on reads
- scope-based route protection

## Current Runtime Rules

Current runtime guardrails:
- inactive tools are blocked
- production mode requires published tools
- debug mode can use draft/published tools
- tool resolution enforces tenant visibility

## Current Notable Tool Behaviors

### Retrieval tools

Current retrieval tools normalize the query contract and validate configured pipeline ownership.

### Agent-call tools

Current agent-call tools execute a child-agent run and return compact runtime output.

### Artifact-backed tools

Current artifact-backed tools resolve a tenant artifact revision and execute through the shared artifact runtime.

Current publish/runtime rules:
- draft editing may still point at a tenant `artifact_id`
- tool publish pins the live execution target into `artifact_revision_id`
- tool publish also ensures the pinned revision has a production deployment
- published production execution uses that pinned `artifact_revision_id`
- if the backing tenant artifact has no published revision, tool publish should fail

Current contract boundary:
- the backing artifact must be kind `tool_impl`
- the artifact owns the executable handler and `tool_contract`
- the tool registry row still owns the callable tool identity presented to agents
- runtime execution calls `ArtifactExecutionService.execute_live_run(...)` with `domain=tool`

Current system-tool note:
- system tools can also be artifact-backed
- the architect-visible `platform-rag`, `platform-agents`, `platform-assets`, and `platform-governance` tools are global/system `FUNCTION` tools backed by native backend dispatch, not by the control-plane SDK shim runtime

## Artifact Connection

The current artifact-to-tool relationship is composition, not inheritance:

1. An artifact is authored as kind `tool_impl`.
2. A tool record is created in `/tools` with `implementation_type=artifact` and an artifact binding.
3. Tool publish resolves the backing artifact, requires a published immutable artifact revision, and pins that revision into `artifact_revision_id`.
4. Production tool execution uses the pinned `artifact_revision_id`, not a floating draft artifact pointer.

This means “artifact needs to be able to be a tool” is already satisfied in the runtime model, but through two linked domain objects:
- `Artifact`
- `ToolRegistry`

The current design intentionally keeps both because they own different responsibilities:
- artifacts own executable source, revisioning, deployment, and runtime execution
- tools own agent-facing registration, tenant/global visibility, and tool lifecycle/publish policy

## Current Known Modeling Tension

There is still some duplicated schema/config surface between tools and `tool_impl` artifacts:
- tool rows carry `schema`
- tool artifacts carry `tool_contract.input_schema` / `tool_contract.output_schema`

The runtime path already works, but the docs should treat this as one connected model with partially duplicated metadata rather than as two unrelated systems.

### MCP tools

Current MCP tools execute through HTTP JSON-RPC `tools/call`.

## Canonical Implementation References

- `backend/app/api/routers/tools.py`
- `backend/app/services/builtin_tools.py`
- `backend/app/agent/executors/tool.py`
- `backend/app/db/postgres/models/registry.py`
- `backend/app/services/artifact_runtime/registry_service.py`
- `backend/app/services/artifact_runtime/execution_service.py`
- `backend/app/services/platform_native_tools.py`
