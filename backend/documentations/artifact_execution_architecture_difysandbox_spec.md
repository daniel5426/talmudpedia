Last Updated: 2026-03-11

# Artifact Execution Architecture (DifySandbox)

This file is now a legacy location.

For the current canonical artifact execution docs, read:
- `docs/design-docs/artifact_execution_current.md`
- `docs/product-specs/artifacts_domain_spec.md`

Keep this file only as historical pre-Cloudflare target-architecture context if needed.
- create run records
- assign queue class and runtime policy
- enqueue work
- expose run state and cancellation

### ArtifactRunService

Responsibilities:
- persist run lifecycle transitions
- persist ordered events
- store stdout/stderr excerpts
- store terminal results and failures

### DifySandbox Worker Client

Responsibilities:
- communicate with the internal worker service or execution pool
- submit execution payloads
- propagate cancellation

## Worker Responsibilities

Each DifySandbox worker should:
- accept authenticated internal execution requests
- fetch artifact bundles by hash or storage key
- populate local bundle cache on miss
- execute the artifact via the runtime runner
- emit structured result, logs, and events
- enforce per-run resource limits

## Scheduling Model

The scheduler should decide:
- which queue class the run belongs to
- which tenant budget applies
- whether the request can execute immediately or must wait

Recommended v1 queue classes:
- `artifact_prod_interactive`
- `artifact_prod_background`
- `artifact_test`

Initial usage:
- `artifact_test` for artifact-page test runs
- later phases extend the same service to Agents, RAG, and Tools

## Test Run Flow

The artifact development page must use the same runtime substrate as production execution.

Flow:
1. user edits an artifact
2. backend resolves the latest draft revision or materializes an ephemeral draft revision from unsaved code
3. backend creates an `ArtifactRun`
4. execution request goes through the scheduler
5. worker fetches or reuses the bundle
6. worker executes the artifact in DifySandbox
7. backend stores logs, events, result, and timing
8. UI polls run status and events endpoints

Important rule:
- no separate local test executor should exist outside this runtime path

## Production Domain Integrations

### Agents

Agent graph compilation should pin artifact revision ids.

At runtime:
- agent executor delegates to `ArtifactExecutionService`
- artifact result is mapped back into agent state
- events are recorded through the shared run/event path

### RAG Pipelines

Artifact-backed operators should be compiled with pinned revision ids.

At runtime:
- pipeline executor delegates to `ArtifactExecutionService`
- each operator run is isolated from the main backend process

### Tools

Artifact-backed tools should become thin wrappers over artifact execution.

At runtime:
- tool resolves published revision id
- tool executor delegates entirely to `ArtifactExecutionService`

## Security Model

Tenant-authored artifact code must not run directly inside the shared backend process.

Required controls:
- isolated execution boundary
- timeout limits
- memory and CPU limits
- restricted filesystem access
- restricted environment exposure
- network policy controls where applicable
- no cross-tenant runtime reuse without strict isolation guarantees

## Current Migration Plan

### Phase 1

Deliver:
- revision-backed tenant artifacts
- bundle builder and bundle storage
- run records and events
- artifact-page test runs on the new runtime

### Phase 2

Deliver:
- tool execution on the new runtime

### Phase 3

Deliver:
- agent artifact-node execution on the new runtime

### Phase 4

Deliver:
- RAG artifact-operator execution on the new runtime

### Historical Outcome

This DifySandbox target architecture was superseded.

Tenant artifact execution is now implemented on Cloudflare Workers for Platforms instead.

## Relationship To Current Docs

This file is the future-state architecture and migration design note.

Current implementation/reference docs:
- [backend/documentations/artifacts_spec.md](/Users/danielbenassaya/Code/personal/talmudpedia/backend/documentations/artifacts_spec.md)
- [backend/documentations/artifacts_execution_infra_spec.md](/Users/danielbenassaya/Code/personal/talmudpedia/backend/documentations/artifacts_execution_infra_spec.md)

Use the docs this way:
- `artifacts_spec.md`: canonical current artifact domain spec
- `artifacts_execution_infra_spec.md`: current runtime/infra implementation status
- `artifact_execution_architecture_difysandbox_spec.md`: target-state architecture and migration plan
