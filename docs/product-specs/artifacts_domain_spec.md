# Artifacts Domain Spec

Last Updated: 2026-03-11

This document is the canonical product/specification overview for the artifact domain.

## Purpose

Artifacts are reusable Python execution units used across the platform by:
- agents
- tools
- RAG pipelines
- the admin artifacts UI and test-run flows

They exist as the shared extension mechanism for executable tenant and platform logic.

## Artifact Ownership And Kinds

Artifacts now share one revision-backed runtime substrate with two ownership modes:
- tenant-owned artifacts
- system-owned artifacts

Artifacts also have one explicit kind:
- `agent_node`
- `rag_operator`
- `tool_impl`

There is no longer a repo-backed runtime artifact class in the canonical model.
`platform_sdk` is now treated as a system-owned artifact seeded into the same runtime tables.

## Current Data Model

The main artifact runtime entities are:
- `artifacts`
- `artifact_revisions`
- `artifact_runs`
- `artifact_run_events`

Current important characteristics:
- artifacts are logical identities
- revisions are executable snapshots
- runs represent execution attempts
- events represent ordered run telemetry

## Current Lifecycle

### Authoring

Tenant artifacts are authored through the admin artifacts APIs.

Current authoring shape includes:
- identity and metadata
- explicit `kind`
- source files and entry module path
- runtime target and dependency declarations
- config schema
- capability declarations
- exactly one kind-specific contract payload
- revision tracking

Current admin authoring UI also includes:
- kind-first creation flow
- a source-tree editor with a file explorer/workspace panel
- an active-file editor surface
- kind-specific contract editing
- artifact-page test-run execution against unsaved source trees

### Publish

Published revisions are the immutable execution target for production-like runtime use.

Current rule:
- production/live execution paths should use published immutable revisions

Current pinning behavior by surface:
- agent artifact nodes are pinned to published artifact revisions at agent run compile/start time
- artifact-backed tools are pinned to `artifact_revision_id` when the tool is published
- artifact-backed RAG operators are pinned to artifact revision metadata when the pipeline is published/compiled

### Test runs

Artifact test runs can use:
- saved draft revisions
- published revisions
- ephemeral revisions generated from unsaved source-tree/dependency changes

## Current Platform Usage

The artifact domain is already used by:
- artifact-backed tools
- agent artifact executors
- RAG artifact-backed operators
- artifact admin/test-run surfaces

This is important because the artifact runtime is no longer just a future design; it is already integrated into multiple execution paths.

## Current Contract Shape

Shared runtime/base configuration now includes:
- metadata and identity fields
- `kind`
- `owner_type`
- `source_files`
- `entry_module_path`
- `python_dependencies`
- `runtime_target`
- `capabilities`
- `config_schema`

Kind-specific contract payloads are:
- `agent_contract`
  - `state_reads`
  - `state_writes`
  - `input_schema`
  - `output_schema`
  - `node_ui`
- `rag_contract`
  - `operator_category`
  - `pipeline_role`
  - `input_schema`
  - `output_schema`
  - `execution_mode`
- `tool_contract`
  - `input_schema`
  - `output_schema`
  - `side_effects`
  - `execution_mode`
  - `tool_ui`

The runtime handler contract remains:

```python
async def execute(inputs: dict, config: dict, context: dict) -> dict: ...
```

## Current Queue Policy

Current queue classes are:
- `artifact_test`
- `artifact_prod_interactive`
- `artifact_prod_background`

Current intent:
- `artifact_test` is for admin artifact-page test runs
- `artifact_prod_interactive` is for user-blocking live execution such as agent turns, tool calls, and inline retrieval
- `artifact_prod_background` is for standalone/background artifact workloads such as pipeline jobs

Current limit:
- queue isolation exists, but stronger intra-queue fairness and scheduling controls are still V1

## Current Runtime Constraints

Tenant artifacts now execute on Cloudflare Workers-compatible runtime paths.

Current practical constraints:
- tenant revisions must be compatible with the Workers Python runtime
- unsupported filesystem/process/socket assumptions are out of contract for tenant artifacts
- dependency declarations are validated against the current Workers-compatible policy before deployment

Current transitional reality:
- the intended production substrate is Cloudflare Workers for Platforms
- the repo also supports a temporary `standard_worker_test` mode for Cloudflare free-plan validation
- that temporary mode validates the control plane and execution path, but it does not yet provide full per-artifact dependency installation fidelity

## Canonical Implementation References

- `backend/app/api/routers/artifacts.py`
- `backend/app/api/routers/artifact_runs.py`
- `backend/app/api/schemas/artifacts.py`
- `backend/app/db/postgres/models/artifact_runtime.py`
- `backend/app/services/artifact_runtime/`
- `backend/app/services/registry_seeding.py`
