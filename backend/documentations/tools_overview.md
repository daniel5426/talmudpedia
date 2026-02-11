# Tools Overview

Date: 2026-02-03
Last Updated: 2026-02-11

This document describes the full Tools domain in the app: data model, APIs, execution flow, UI, and tests. It reflects the current architecture after Built-in Tools v1 (global templates + tenant instances) and Tool taxonomy upgrades.

---

## 1) Concepts and Taxonomy

Tools are callable capabilities that agents can invoke. The system uses a **hybrid taxonomy**:

### Primary Buckets (tool_type)
- `built_in`  - system tools and built-in templates/instances
- `mcp`       - tools served from MCP servers
- `artifact`  - tools backed by code artifacts
- `custom`    - tenant-defined tools (http/function/rag/custom)

### Subtypes (implementation_type)
- `internal`
- `http`
- `rag_retrieval`
- `function`
- `custom`
- `artifact`
- `mcp`

The API returns `tool_type` as a **derived** field. It is not stored in the DB.

---

## 2) Data Model

### Table: `tool_registry`
Key fields (non-exhaustive):
- `id`, `tenant_id`, `name`, `slug`, `description`, `scope`
- `schema`             - JSON Schema for inputs/outputs
- `config_schema`      - execution config (implementation/execution)
- `status`             - `draft | published | deprecated | disabled`
- `version`            - current version string (semver)
- `implementation_type`- subtype
- `published_at`       - publish timestamp
- `artifact_id`, `artifact_version`
- `builtin_key`                - built-in identifier (e.g. `retrieval_pipeline`)
- `builtin_template_id`        - FK to global template row for tenant instances
- `is_builtin_template`        - marks global built-in template rows
- `is_active`, `is_system`

### Table: `tool_versions`
Snapshot table created on publish and versioning. Stores:
- `version`
- `schema_snapshot` (schema + config + implementation_type)

---

## 3) Derived Fields

### tool_type
Computed by the Tools API:
- `built_in` if `is_system == true` OR `is_builtin_template == true` OR `builtin_key` is set
- `mcp` if `implementation_type == mcp` OR `config_schema.implementation.type == "mcp"`
- `artifact` if `artifact_id` exists OR `implementation_type == artifact`
- `custom` otherwise

---

## 4) API Endpoints

### List
`GET /tools`
- Filters:
  - `status`
  - `implementation_type`
  - `tool_type`
  - `skip`, `limit`

### Create
`POST /tools`
- Accepts:
  - `implementation_type`
  - `implementation_config` (stored under `config_schema.implementation`)
  - `execution_config` (stored under `config_schema.execution`)
- Guardrails:
  - Only `scope=tenant` is allowed on this endpoint
  - Direct creation with `status=published` is blocked; publish must use `POST /tools/{id}/publish`

### Update
`PUT /tools/{id}`
- Accepts updates to schema, config, status, implementation type, artifact link
- Guardrail: direct transition to `published` is blocked; use `POST /tools/{id}/publish`

### Publish
`POST /tools/{id}/publish`
- Sets status to `published`
- Sets `published_at` if missing
- Writes a ToolVersion snapshot

### Version
`POST /tools/{id}/version?new_version=X.Y.Z`
- Validates semver
- Writes a ToolVersion snapshot
- Updates `tool_registry.version`

### Built-in Templates / Instances
- `GET /tools/builtins/templates`
- `POST /tools/builtins/templates/{builtin_key}/instances`
- `GET /tools/builtins/instances`
- `PATCH /tools/builtins/instances/{tool_id}`
- `POST /tools/builtins/instances/{tool_id}/publish`
- Rules:
  - Templates are global (`tenant_id = null`, `is_builtin_template = true`).
  - Instances are tenant-scoped clones with tenant config.
  - Built-in instance schema/type are immutable via generic `PUT /tools/{id}`.
  - `retrieval_pipeline` validates that configured pipeline belongs to the tenant.

---

## 5) Execution Flow

### Tool Node Execution
- Node executor: `ToolNodeExecutor`
- Reads `implementation_type` column first
- Falls back to `config_schema.implementation.type`
- Enforces runtime guardrails:
  - production mode requires tool status `published`
  - debug mode allows draft/published
  - inactive tools are blocked in all modes
- Unknown implementation types now return explicit execution errors (no stub success fallback)

### Agent Node Tool Binding
- When an Agent node is configured with `tools`, it binds tool schemas to the model and accepts structured tool calls (with JSON fallback).
- The Agent node executes matching tools internally via `ToolNodeExecutor`, writing `tool_outputs`, `context`, and `state.last_agent_output` with the tool result.
- Execution supports `sequential` or `parallel_safe` modes, with deterministic ToolMessage ordering.
- Runtime applies schema-aware input coercion for malformed/scalar tool-call payloads (e.g. alias normalization for `query`), reducing prompt-shape brittleness across model SDKs.

### Tool Execution Metadata (config_schema.execution)
Backend-only execution metadata used by the Agent tool loop:
- `is_pure` (bool, default false)
- `concurrency_group` (str, default "default")
- `max_concurrency` (int, default 1)
- `timeout_s` (int, optional)

### Artifact-backed Tools
- If `artifact_id` is set on the tool, execution delegates to `ArtifactNodeExecutor`
- Supports inline artifact config in `config_schema.implementation`
- Tool-call args are mapped into artifact inputs by name (schema-driven); inputs are treated as literal values (no `{{ }}` interpolation)
- Required artifact inputs are validated strictly; missing required fields fail execution

### Function Tools
- `implementation_type: function` executes allowlisted server-side functions
- Function lookup uses the internal Tool Function Registry
- `implementation_config.function_name` is required and must be registered
- Sync functions run in a thread; async functions are awaited

### MCP Tools
- `implementation_type: mcp` executes MCP tools via HTTP JSON-RPC
- Request method: `tools/call` with params `{ name, arguments }`
- `implementation_config.server_url` and `implementation_config.tool_name` are required
- Optional `implementation_config.headers` are passed through for auth

### Built-in Tools v1 Runtime Dispatch
- Native dispatch by `builtin_key` for:
  - `retrieval_pipeline`
  - `http_request`
  - `function_call`
  - `mcp_call`
  - `web_fetch` (allow-any-URL policy in v1)
  - `web_search` (provider interface, Serper first)
  - `json_transform`
  - `datetime_utils`

### Tool Resolver
- Resolves tool metadata and returns the actual implementation type
- Enforces tenant isolation (`tenant_id == current tenant` OR global `tenant_id is null`)
- The same tenant isolation is enforced in runtime tool fetch paths (`ToolNodeExecutor`, agent tool-record loading/resolution)
- Optional `require_published=true` resolution is used for production-mode compile-time checks

---

## 6) Frontend UI

### Tools Registry Page
Location: `frontend-reshet/src/app/admin/tools/page.tsx`
Key features:
- Summary cards for each primary bucket
- Search + filters (status, bucket, subtype)
- Tool list shows bucket badge, subtype badge, status, version
- Detail drawer with input/output schemas and implementation/execution configs
- Create Tool dialog with type-specific inputs:
  - Artifact: artifact picker
  - MCP: server URL + tool name
  - HTTP: method, URL, headers
  - Function: function name

### Shared Tool Taxonomy
Location: `frontend-reshet/src/lib/tool-types.ts`
Exports:
- `TOOL_BUCKETS`
- `TOOL_SUBTYPES`
- `getToolBucket(tool)`
- `getSubtypeLabel(type)`
- `filterTools(tools, filters)`

### Agent Tool Picker
Location: `frontend-reshet/src/components/agent-builder/ToolPicker.tsx`
Features:
- Search input
- Bucket and subtype filters
- Grouped list by bucket
- Multi-select checkboxes
- Detail drawer
- Selected tools summary + Clear all

Integrated in `ConfigPanel` for `tool_list` field type.

---

## 7) Tests

### Backend
- `backend/tests/agent_tool_usecases/test_agent_builtin_tool_flow.py`
- `backend/tests/tool_execution/test_function_tool_execution.py`
- `backend/tests/tool_execution/test_mcp_tool_execution.py`
- `backend/tests/agent_tool_loop/test_tool_loop.py`
- `backend/tests/tools_guardrails/test_tools_api_guardrails.py`
- `backend/tests/tools_guardrails/test_tool_tenant_scoping.py`
- `backend/tests/builtin_tools_registry/test_builtin_registry_api.py`
- `backend/tests/builtin_tool_execution/test_builtin_tool_executor.py`
- `backend/tests/tools_guardrails/test_tools_runtime_guardrails.py`

### Frontend
- `frontend-reshet/src/__tests__/tools_builtin/tools_builtin_page.test.tsx`
- `frontend-reshet/src/__tests__/tools_builtin/tool_bucket_filtering.test.ts`

---

## 8) Defaults and Backfill

Migration defaults:
- Existing tools -> `status = published` if `is_active = true`, else `disabled`
- `version = "1.0.0"` if missing
- `implementation_type` inferred from artifact/config_schema/is_system

## 10) Key Files

Backend:
- `backend/app/db/postgres/models/registry.py`
- `backend/app/api/routers/tools.py`
- `backend/app/agent/executors/tool.py`
- `backend/app/agent/resolution.py`

Frontend:
- `frontend-reshet/src/app/admin/tools/page.tsx`
- `frontend-reshet/src/lib/tool-types.ts`
- `frontend-reshet/src/components/agent-builder/ToolPicker.tsx`
- `frontend-reshet/src/components/agent-builder/ConfigPanel.tsx`
