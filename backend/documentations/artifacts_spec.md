Last Updated: 2026-03-11

# Artifacts Spec

This file is now a legacy location.

For the current canonical artifact-domain docs, read:
- `docs/product-specs/artifacts_domain_spec.md`
- `docs/design-docs/artifact_execution_current.md`

Do not add new canonical artifact-domain detail here.

Current canonical implementation reminders:
- tenant artifacts are revision-backed with `source_files` and `entry_module_path`
- artifact-page test runs, tenant agent artifact nodes, artifact-backed tools, and artifact-backed RAG operators already use the shared artifact runtime
- the intended production target is Cloudflare Workers for Platforms
- the repo also supports a temporary Cloudflare free-plan `standard_worker_test` mode for runtime-path validation

Current run endpoints:
- `POST /admin/artifacts/test-runs`
- `POST /admin/artifacts/{artifact_id}/test-runs`
- `GET /admin/artifact-runs/{run_id}`
- `GET /admin/artifact-runs/{run_id}/events`
- `POST /admin/artifact-runs/{run_id}/cancel`

Legacy wrapper endpoint kept over the run-based path:
- `POST /admin/artifacts/test`

That legacy endpoint still routes through the same run-based runtime.

### Publish

Publishing now means promoting the latest draft revision to the published revision pointer.

In V1, publishing does not create tenant filesystem artifacts.

## Execution Contract

The new runtime contract is:

```python
async def execute(inputs: dict, config: dict, context: dict) -> dict:
    ...
```

## Current Platform Usage By Domain

### Artifacts page

Primary current runtime user of the new artifact execution stack.

Used for:
- create/edit draft artifacts
- trigger test runs
- inspect logs, events, outputs, and failures

### Tools

Artifact-backed tools now publish against a pinned tenant artifact revision and execute through the shared runtime.

### Agents

Tenant artifact nodes now execute through the shared runtime with published-revision pinning at agent run compile/start time.

### RAG pipelines

Artifact-backed RAG operators now execute through the shared runtime with published artifact revision pinning.

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

### 4. Runtime migration status

Artifact-page testing and the main live tenant Agent/Tool/RAG paths now use the shared runtime.

Remaining migration scope is mostly:
- builtin repo artifacts
- older terminology/docs that still say custom operator or DifySandbox
- temporary free-plan runtime mode versus the intended Workers for Platforms production mode

## Current Limitations

- builtin repo artifacts are not yet migrated into runtime revision tables
- tenant artifact execution now depends on Cloudflare Workers-compatible Python/runtime constraints
- queue fairness remains queue-class based rather than governed by a dedicated scheduler
- backend secret-broker and outbound-policy hardening still need deeper end-to-end coverage
- the platform still carries some legacy custom-operator concepts and routes during migration

## Canonical Direction

The intended direction is:
- one artifact domain across Agents, RAG, and Tools
- tenant artifacts stored as immutable revisions
- test and production execution using one shared runtime contract
- execution isolated behind the Cloudflare Workers runtime boundary for tenant artifacts
- builtin artifacts eventually reconciled with the same broader model

## Companion Doc

The execution substrate and worker architecture are specified in:
- [backend/documentations/artifacts_execution_infra_spec.md](/Users/danielbenassaya/Code/personal/talmudpedia/backend/documentations/artifacts_execution_infra_spec.md)
