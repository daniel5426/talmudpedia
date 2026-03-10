# Tools Overview

Date: 2026-02-03
Last Updated: 2026-03-10

This file is now a legacy location.

For the current canonical tools-domain docs, read:
- `docs/product-specs/tools_domain_spec.md`
- `docs/references/mcp_tools_reference.md`

Do not add new canonical tools-domain detail here.
  - `execution_config` (stored under `config_schema.execution`)
- Guardrails:
  - Only `scope=tenant` is allowed on this endpoint
  - Direct creation with `status=published` is blocked; publish must use `POST /tools/{id}/publish`
  - `rag_retrieval` requires `implementation.pipeline_id` and validates tenant ownership
  - `rag_retrieval` input/output schemas are normalized so `query` is always present and required

### Update
`PUT /tools/{id}`
- Accepts updates to schema, config, status, implementation type, artifact link
- Guardrail: direct transition to `published` is blocked; use `POST /tools/{id}/publish`

### Publish
`POST /tools/{id}/publish`
- Sets status to `published`
- Sets `published_at` if missing
- Writes a ToolVersion snapshot
- `rag_retrieval` validates tenant ownership of configured `implementation.pipeline_id`

### Version
`POST /tools/{id}/version?new_version=X.Y.Z`
- Validates semver
- Writes a ToolVersion snapshot
- Updates `tool_registry.version`

### Built-in Catalog (Compatibility Endpoint)
- `GET /tools/builtins/templates`
- Rules:
  - Endpoint name is kept for backward compatibility.
  - Returns global built-ins (`tenant_id = null`) by `builtin_key`/`is_system`.
  - No template/instance semantics are required for runtime.
  - Retrieval tools are created in the regular tool flow (`POST /tools`) with `implementation_type=rag_retrieval`.

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
  - `web_search` (provider interface, `serper` / `tavily` / `exa`)
  - `json_transform`
  - `datetime_utils`

### Query Input Normalization (Retrieval + Web Search)
- Runtime accepts query aliases for both `retrieval_pipeline` and `web_search`:
  - `query`, `q`, `search_query`, `keywords`, `text`, `value`
- Runtime also accepts scalar payload forms produced by some tool-call shapes:
  - `input: "<query text>"`
  - `payload: "<query text>"`
- For nested-object payloads, `top_k` and `filters` can be read from `input.top_k` / `input.filters` for retrieval/web-search execution.
- This normalization is enforced in `ToolNodeExecutor` and is intended to avoid false negatives like `retrieval pipeline tool requires a query` when the model emits non-canonical argument shapes.

### Web Search Credential Resolution (Canonical)
`web_search` uses a single credential strategy with clear precedence:
1. `config_schema.implementation.api_key` (explicit per-tool override)
2. `config_schema.implementation.credentials_ref` (tool-linked credential)
3. Integration credential default lookup:
   - `category = tool_provider`
   - `provider_key = <serper|tavily|exa>`
   - credential payload keys: `api_key` (preferred) or `token`; optional `endpoint`
4. Environment fallback for bootstrap reliability:
   - `SERPER_API_KEY` / `TAVILY_API_KEY` / `EXA_API_KEY` (provider-specific)

Recommended production posture:
- Keep platform tool-provider defaults in env vars (`SERPER_API_KEY`, `TAVILY_API_KEY`, `EXA_API_KEY`).
- Let tenants override with tenant-scoped credentials and default selection in Settings.
- Avoid hardcoding provider secrets directly in tool definitions unless explicitly required.

### Agent Call Tools
- `implementation_type: agent_call` executes a synchronous child-agent run.
- Target resolution supports `target_agent_id` or `target_agent_slug`.
- Target must be tenant-scoped and published.
- Runtime accepts caller payload aliases: `input`, `text`, `messages`, `context`.
- Compact runtime output includes:
  - `mode`
  - `target_agent_id` / `target_agent_slug`
  - `run_id`
  - `status`
  - `output` and/or `context` (if present)
  - `error` (for failure/timeout cases)

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
  - RAG Retrieval: retrieval pipeline selector
  - Agent Call: target slug/ID + optional timeout

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
- `backend/tests/tool_execution/test_agent_call_tool_execution.py`
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
