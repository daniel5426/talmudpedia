# Artifacts Domain Spec

Last Updated: 2026-03-10

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
- source code
- config schema
- inputs and outputs
- declared reads and writes
- revision tracking

### Publish

Published revisions are the immutable execution target for production-like runtime use.

Current rule:
- production/live execution paths should use published immutable revisions

### Test runs

Artifact test runs can use:
- saved draft revisions
- published revisions
- ephemeral revisions generated from unsaved code/dependency changes

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
- `config_schema`
- `inputs`
- `outputs`
- `reads`
- `writes`
- source code and dependency declarations

The runtime handler contract remains:

```python
async def execute(inputs: dict, config: dict, context: dict) -> dict:
    ...
```

## Canonical Implementation References

- `backend/app/api/routers/artifacts.py`
- `backend/app/api/routers/artifact_runs.py`
- `backend/app/api/schemas/artifacts.py`
- `backend/app/db/postgres/models/artifact_runtime.py`
- `backend/app/services/artifact_runtime/`
- `backend/app/services/artifact_registry.py`
