Last Updated: 2026-03-10

# Artifacts Spec

This file is now a legacy location.

For the current canonical artifact-domain docs, read:
- `docs/product-specs/artifacts_domain_spec.md`
- `docs/design-docs/artifact_execution_current.md`

Do not add new canonical artifact-domain detail here.
2. create an `artifact_runs` row
3. enqueue or eagerly execute the run
4. execute through the internal artifact worker
5. persist result, logs, and events

Current run endpoints:
- `POST /admin/artifacts/test-runs`
- `POST /admin/artifacts/{artifact_id}/test-runs`
- `GET /admin/artifact-runs/{run_id}`
- `GET /admin/artifact-runs/{run_id}/events`
- `POST /admin/artifact-runs/{run_id}/cancel`

Compatibility endpoint:
- `POST /admin/artifacts/test`

That compatibility endpoint still exists, but it now routes through the same new run-based runtime.

### Publish

Publishing now means promoting the latest draft revision to the published revision pointer.

In V1, publishing does not create tenant filesystem artifacts.

## Execution Contract

The new runtime contract is:

```python
async def execute(inputs: dict, config: dict, context: dict) -> dict:
    ...
```

Compatibility note:
- the current worker runner also supports the older single-context artifact signature for existing code during the transition

## Current Platform Usage By Domain

### Artifacts page

Primary current runtime user of the new artifact execution stack.

Used for:
- create/edit draft artifacts
- trigger test runs
- inspect logs, events, outputs, and failures

### Tools

Artifacts are already part of the conceptual tool model, but full live tool execution through the new revision runtime is still a follow-up phase.

### Agents

Agent-side artifact usage exists, but live agent execution is not yet fully migrated to the new shared runtime everywhere.

### RAG pipelines

RAG custom logic is the historical origin of the feature, but live RAG execution still contains legacy paths and compatibility assumptions.

## Current Contradictions And Transitional Reality

This domain currently has some intentional overlap between legacy and new systems.

### 1. Filesystem versus revision-backed storage

Builtin artifacts are still repo-backed and scanned from disk.

Tenant artifacts are now revision-backed in Postgres.

### 2. Legacy operator language versus artifact language

Some older docs and code still use "custom operator" terminology, especially for RAG.

The current canonical domain term should be "artifact" for the shared system.

### 3. Scope model drift

The platform model already recognizes `tool` as an artifact scope in code and manifests.

Older docs and parts of the historical API language were narrower and focused on `rag` and `agent`.

### 4. Runtime migration is incomplete

Artifact-page testing is on the new runtime.

Full live execution for Agents, RAG, and Tools is not yet completely migrated to the same runtime service.

## Current Limitations

- builtin repo artifacts are not yet migrated into runtime revision tables
- live agent/tool/RAG execution is not yet uniformly routed through the new execution service
- artifact-page and worker execution now use a real DifySandbox-backed adapter, but deployment is still V1 rather than a fully scheduled sandbox pool
- bundle building is now dependency-aware and emits runtime metadata plus vendored dependency payloads when available locally
- the platform still carries some legacy custom-operator concepts and routes during migration

## Canonical Direction

The intended direction is:
- one artifact domain across Agents, RAG, and Tools
- tenant artifacts stored as immutable revisions
- test and production execution using one shared runtime contract
- execution isolated behind the artifact worker / DifySandbox boundary
- builtin artifacts eventually reconciled with the same broader model

## Companion Doc

The execution substrate and worker architecture are specified in:
- [backend/documentations/artifacts_execution_infra_spec.md](/Users/danielbenassaya/Code/personal/talmudpedia/backend/documentations/artifacts_execution_infra_spec.md)
