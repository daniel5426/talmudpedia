# Tools Domain Spec

Last Updated: 2026-03-19

This document is the canonical product/specification overview for the tools domain.

## Purpose

Tools are callable capabilities that agents can execute. The tools domain provides:
- tool registration and versioning
- execution metadata and guardrails
- multiple implementation types
- tenant/global visibility rules

In the current platform, the canonical runtime-facing tool catalog is the DB-backed `ToolRegistry` domain exposed at `/tools`.
The small in-process helper in `backend/app/services/tool_function_registry.py` is only a function-dispatch map for `FUNCTION` tools, not the canonical registry for the tools domain.

Important boundary:
- `/tools` is the authoring surface for manual tools
- artifact-bound tools are authored from the artifact domain and mirrored into `ToolRegistry`
- pipeline-bound tools are authored from the pipeline domain and mirrored into `ToolRegistry`
- system tools are authored by backend seeding/runtime code

## Current Ownership Classes

Current ownership classes are:
- `manual`
- `artifact_bound`
- `pipeline_bound`
- `agent_bound`
- `system`

These are now persisted on `tool_registry` and returned in the `/tools` DTO so the UI can tell which rows are editable in the registry versus managed from another domain.

## Current Tool Classes

Current derived tool classes are:
- `built_in`
- `mcp`
- `artifact`
- `custom`

This classification is still derived at the API layer rather than stored directly as a database column.

## Current Canonical Registry Shape

The logical tool record lives in `tool_registry` and currently carries:
- identity, scope, and visibility
- input/output schema
- config/execution metadata
- implementation type
- persisted ownership/management/source metadata
- publish/version state
- optional artifact binding fields

Important current detail:
- `ToolRegistry` remains the unified runtime-facing catalog used for tool selection and execution
- not every row is authored from `/tools`
- manual tools are authored and managed from `/tools`
- artifact-bound and pipeline-bound rows are mirrored runtime records managed from their owning domains
- system rows are seeded/managed by backend code

## Current Implementation Types

Current implementation types include:
- `internal`
- `http`
- `rag_pipeline`
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
- create/update/publish/version flows for manual tools
- tool-type filtering
- sensitive config redaction on reads
- explicit DTO fields for:
  - `implementation_config`
  - `execution_config`
  - `ownership`
  - `managed_by`
  - `source_object_type`
  - `source_object_id`
  - registry action flags (`can_edit_in_registry`, `can_publish_in_registry`, `can_delete_in_registry`)
- scope-based route protection

## Current Creation Surfaces

Current creation/authorship surfaces are split by ownership:
- manual tools
  - created from the tools page and persisted through `/tools`
- artifact-bound tools
  - created from the artifact domain, typically as `tool_impl` artifacts
  - the tools page should route users to artifact-native authoring instead of generic `/tools` CRUD
- pipeline-bound tools
  - created from the pipeline domain through the pipeline tool-binding flow
  - the binding flow can set model-facing tool name, description, and input schema while the slug remains pipeline-derived
  - the tools page should route users to pipeline authoring instead of generic `/tools` CRUD
- agent/workflow tools
  - created from the agents surface through the export-to-tool flow
  - exported rows are owner-managed `agent_call` tools mirrored into `ToolRegistry`

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
- the tool registry row still owns the runtime-facing callable identity presented to agents
- artifact-bound tool rows are managed from the artifact surface, not from generic `/tools` CRUD
- runtime execution calls `ArtifactExecutionService.execute_live_run(...)` with `domain=tool`

Current system-tool note:
- system tools can also be artifact-backed
- the architect-visible `platform-rag`, `platform-agents`, `platform-assets`, and `platform-governance` tools are global/system `FUNCTION` tools backed by native backend dispatch, not by the control-plane SDK shim runtime

## Artifact Connection

The current artifact-to-tool relationship is composition, not inheritance:

1. An artifact is authored as kind `tool_impl`.
2. A bound tool record is synchronized into `ToolRegistry` with `implementation_type=artifact` and an artifact binding.
3. Tool publish resolves the backing artifact, requires a published immutable artifact revision, and pins that revision into `artifact_revision_id`.
4. Production tool execution uses the pinned `artifact_revision_id`, not a floating draft artifact pointer.

This means “artifact needs to be able to be a tool” is already satisfied in the runtime model, but through two linked domain objects:
- `Artifact`
- `ToolRegistry`

The current design intentionally keeps both because they own different responsibilities:
- artifacts own executable source, revisioning, deployment, runtime execution, and bound-tool authoring
- tools own runtime-facing registration, tenant/global visibility, and unified selection

### Pipeline-backed tools

Current pipeline-backed tools follow the same mirrored-row model:
- the owning surface is the pipeline editor/tool-binding flow
- the bound `ToolRegistry` row is the runtime-facing catalog entry
- generic `/tools` CRUD should not be treated as the authoring surface for those rows

### Agent-backed tools

Current agent-backed tools now follow the same mirrored-row model:
- the owning surface is the agents page/export flow
- the bound `ToolRegistry` row is an `agent_call` runtime catalog entry
- generic `/tools` CRUD should not be treated as the authoring surface for those rows
- publish/delete lifecycle is synchronized from the agent domain once a binding exists

## Current Known Modeling Tension

There is still some duplicated schema/config surface between tools and `tool_impl` artifacts:
- tool rows carry `schema`
- tool artifacts carry `tool_contract.input_schema` / `tool_contract.output_schema`

The runtime path already works, but the docs should treat this as one connected model with partially duplicated metadata rather than as two unrelated systems.

### MCP tools

Current MCP tools execute through HTTP JSON-RPC `tools/call`.

Current MCP runtime policy:
- `server_url` must use `http` or `https`
- embedded URL credentials are rejected
- private/loopback hosts are blocked by default unless `MCP_ALLOW_PRIVATE_HOSTS=true`
- optional `MCP_ALLOWED_HOSTS` constrains outbound MCP hostnames
- transport and protocol failures are normalized into stable runtime errors instead of leaking raw client exceptions

## Canonical Implementation References

- `backend/app/api/routers/tools.py`
- `backend/app/services/builtin_tools.py`
- `backend/app/agent/executors/tool.py`
- `backend/app/db/postgres/models/registry.py`
- `backend/app/services/artifact_runtime/registry_service.py`
- `backend/app/services/artifact_runtime/execution_service.py`
- `backend/app/services/platform_native_tools.py`
