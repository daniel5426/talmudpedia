# Tools Overview

Date: 2026-02-03
Last Updated: 2026-02-04

This document describes the full Tools domain in the app: data model, APIs, execution flow, UI, and tests. It reflects the current architecture after the Tool taxonomy and Agent Tool Picker upgrades.

---

## 1) Concepts and Taxonomy

Tools are callable capabilities that agents can invoke. The system uses a **hybrid taxonomy**:

### Primary Buckets (tool_type)
- `built_in`  - system tools (global, internal)
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
- `is_active`, `is_system`

### Table: `tool_versions`
Snapshot table created on publish and versioning. Stores:
- `version`
- `schema_snapshot` (schema + config + implementation_type)

---

## 3) Derived Fields

### tool_type
Computed by the Tools API:
- `built_in` if `is_system == true` OR (`tenant_id is null` AND `implementation_type == internal`)
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
  - `status` (optional)

### Update
`PUT /tools/{id}`
- Accepts updates to schema, config, status, implementation type, artifact link

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

---

## 5) Execution Flow

### Tool Node Execution
- Node executor: `ToolNodeExecutor`
- Reads `implementation_type` column first
- Falls back to `config_schema.implementation.type`
- MCP execution is stubbed and raises NotImplemented

### Agent Node Tool Binding
- When an Agent node is configured with `tools`, it can emit a JSON tool-call payload.
- The Agent node executes matching tools internally via `ToolNodeExecutor`, writing `tool_outputs`, `context`, and `state.last_agent_output` with the tool result.

### Artifact-backed Tools
- If `artifact_id` is set on the tool, execution delegates to `ArtifactNodeExecutor`
- Supports inline artifact config in `config_schema.implementation`

### Tool Resolver
- Resolves tool metadata and returns the actual implementation type

---

## 6) Frontend UI

### Tools Registry Page
Location: `frontend/src/app/admin/tools/page.tsx`
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
Location: `frontend/src/lib/tool-types.ts`
Exports:
- `TOOL_BUCKETS`
- `TOOL_SUBTYPES`
- `getToolBucket(tool)`
- `getSubtypeLabel(type)`
- `filterTools(tools, filters)`

### Agent Tool Picker
Location: `frontend/src/components/agent-builder/ToolPicker.tsx`
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
- `backend/tests/test_tools_api.py`
  - Create, list, publish, version
- `backend/tests/test_tool_type_derivation.py`
  - tool_type derivation logic
- `backend/tests/test_full_artifact_layers.py`
  - Ensures new fields exist on tools

### Frontend
- `frontend/src/lib/tool-types.test.ts`
- `frontend/src/components/agent-builder/ToolPicker.test.tsx`

---

## 8) Defaults and Backfill

Migration defaults:
- Existing tools -> `status = published` if `is_active = true`, else `disabled`
- `version = "1.0.0"` if missing
- `implementation_type` inferred from artifact/config_schema/is_system

---

## 9) Known Gaps

- MCP execution is not implemented; currently raises NotImplemented.
- Tool execution for `function` subtype is stubbed.

---

## 10) Key Files

Backend:
- `backend/app/db/postgres/models/registry.py`
- `backend/app/api/routers/tools.py`
- `backend/app/agent/executors/tool.py`
- `backend/app/agent/resolution.py`

Frontend:
- `frontend/src/app/admin/tools/page.tsx`
- `frontend/src/lib/tool-types.ts`
- `frontend/src/components/agent-builder/ToolPicker.tsx`
- `frontend/src/components/agent-builder/ConfigPanel.tsx`
