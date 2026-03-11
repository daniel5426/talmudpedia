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

## Current Artifact Classes

### Builtin repo artifacts

Filesystem-backed artifacts under `backend/artifacts/`.

Current role:
- platform-owned logic
- compatibility/discovery path through the registry
- not the main editable admin CRUD path for tenant artifact authoring

### Tenant artifacts

Revision-backed artifacts stored in runtime tables.

Current role:
- first-class tenant-authored executable logic
- admin CRUD target
- testable and executable through the shared runtime

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
- source files and entry module path
- config schema
- inputs and outputs
- declared reads and writes
- revision tracking

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

Artifact configuration currently includes:
- metadata and identity fields
- `source_files`
- `entry_module_path`
- `config_schema`
- `inputs`
- `outputs`
- `reads`
- `writes`
- dependency declarations

The runtime handler contract remains:

```python
async def execute(inputs: dict, config: dict, context: dict) -> dict: ...
```

Compatibility behavior also still exists for older handlers:

```python
def execute(context): ...
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

Tenant artifacts now execute on Cloudflare Workers for Platforms.

Current practical constraints:
- tenant revisions must be compatible with the Workers Python runtime
- unsupported filesystem/process/socket assumptions are out of contract for tenant artifacts
- dependency declarations are validated against the current Workers-compatible policy before deployment

## Canonical Implementation References

- `backend/app/api/routers/artifacts.py`
- `backend/app/api/routers/artifact_runs.py`
- `backend/app/api/schemas/artifacts.py`
- `backend/app/db/postgres/models/artifact_runtime.py`
- `backend/app/services/artifact_runtime/`
- `backend/app/services/artifact_registry.py`
