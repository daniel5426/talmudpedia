Last Updated: 2026-03-08

# Artifact Sandbox Architecture

## Purpose

This document defines how artifact execution should reuse the existing app-builder sandbox substrate instead of introducing a second sandbox platform.

Goals:
- support tenant-safe artifact execution for draft tests and published runtime
- remove dependence on writing tenant artifacts into `backend/artifacts/`
- keep draft test latency low by reusing warm sandboxes and dependency caches
- support RAG, agent-node, and tool execution from one canonical artifact package model

## Current State

Today there are two different execution models:

1. DB-backed draft execution
- draft test endpoints execute raw code from the request body or `CustomOperator.python_code`
- execution uses `PythonOperatorExecutor`
- this runs in-process inside the backend runtime

2. Filesystem artifact execution
- promoted artifacts are written into `backend/artifacts/<namespace>/<name>/`
- RAG artifact execution imports `handler.py` from disk and calls `execute(context)`
- agent/tool artifact execution imports `handler.py` from disk and calls `execute(state, config, context)`

This is not SaaS-safe because promoted tenant code becomes mutable platform filesystem state.

## Existing Sandbox Substrate We Should Reuse

The app-builder draft runtime already has the right abstraction layers:

- `PublishedAppDraftDevRuntimeService`
  - owns session lifecycle, persistence, idle expiry, dependency hash computation
- `PublishedAppDraftDevRuntimeClient`
  - abstracts remote controller vs embedded local runtime
- `LocalDraftDevRuntimeManager`
  - implements long-lived warm local sandboxes, file sync, dependency install reuse, stage/live workspaces, command execution
- `sandbox_controller_dev_shim.py`
  - exposes controller-like APIs for start/sync/stop/stage/run-command/archive

Important reusable properties:

- persistent session rows in Postgres
- dependency hash marker to skip reinstall when manifests have not changed
- long-lived warm sandbox reuse
- stage workspace separate from live workspace
- generic `run_command` API inside the sandbox
- controller/client split that can later point to a real remote sandbox backend

## Architectural Decision

Do not create a separate "artifact sandbox platform".

Instead, create an `artifact runtime` profile on the same sandbox substrate with:

- artifact-specific session metadata and policies
- artifact-specific workspace layout
- artifact-specific base images / dependency policy
- artifact-specific execution APIs

The substrate stays shared:
- session lifecycle
- client/controller abstraction
- local embedded runtime
- future remote controller

The execution contract becomes profile-specific.

## Target Model

### 1. Canonical Artifact Storage

Artifacts should have canonical storage in shared persistent storage, not local repo disk.

Split the model into:

- draft artifact source
  - manifest
  - code
  - dependency manifest
  - tenant ownership
  - mutable

- published artifact version
  - immutable manifest
  - immutable code bundle
  - dependency spec
  - content hash
  - published version number

Recommended storage shape:

- Postgres
  - artifact metadata, tenancy, versions, state, hashes, runtime policy
- object storage or blob store
  - code package bundle for published versions

Filesystem artifacts under `backend/artifacts/` remain only for builtin/platform-owned artifacts and local development fixtures.

### 2. Artifact Runtime Profiles

Use one substrate with two profiles:

1. `artifact_draft`
- optimized for quick author/test loop
- warm reusable sandbox session
- mutable workspace
- curated dependency set by default
- optional explicit dependency install only when dependency hash changes

2. `artifact_published`
- immutable published package
- runtime resolves exact artifact id + version + content hash
- package synced into sandbox workspace
- suitable for RAG pipelines, agent nodes, and artifact-backed tools

### 3. Artifact Workspace Layout

Inside sandbox:

```text
/workspace/
  artifact.yaml
  handler.py
  requirements.lock or package metadata
  .talmudpedia/
    draft/
    stage/
    published/
    runtime/
```

For draft sessions:
- live workspace is the current mutable draft
- stage workspace is used for validation/build/package before publish

For published runtime:
- workspace is materialized from the immutable published package
- no write-back to canonical source during normal execution

## Execution Paths

### A. Draft Test Execution

User clicks `Test` in artifact editor.

Target flow:

1. backend loads draft source from request body or DB
2. backend computes artifact dependency hash
3. backend ensures an `artifact_draft` sandbox session for `(tenant_id, artifact_id or temp draft id, actor_id, dependency_hash-family)`
4. backend syncs `artifact.yaml`, `handler.py`, and dependency files into sandbox
5. backend installs dependencies only if the dependency hash changed
6. backend executes a profile-specific command such as:
   - `python /runtime/run_artifact_test.py --surface rag`
   - or equivalent runner module
7. backend returns structured output, logs, duration, and sandbox diagnostics

This replaces in-process `PythonOperatorExecutor` for artifact tests.

### B. RAG Runtime Execution

Target flow:

1. compiled pipeline references `artifact_id` + `artifact_version`
2. backend resolves the published package metadata from canonical storage
3. backend ensures an `artifact_published` runtime session or pooled worker with matching runtime class
4. backend syncs or mounts the immutable package into the sandbox
5. backend executes the RAG adapter runner
6. backend captures output and trace metadata

Runner contract presented to artifact code:

```python
def execute(context):
    ...
```

### C. Agent Node Execution

Target flow:

1. node config references `artifact_id` + `artifact_version`
2. backend resolves published package metadata
3. backend routes execution to the artifact sandbox runtime
4. field mappings are resolved in backend before sandbox execution
5. sandbox runner invokes artifact adapter for agent surface
6. backend merges the resulting state patch into agent state

Runner contract presented to artifact code:

```python
def execute(state, config, context):
    ...
```

### D. Tool-backed Artifact Execution

Target flow:

1. tool registry entry references `artifact_id` + `artifact_version`
2. `ToolNodeExecutor` resolves tool input as it already does
3. backend forwards execution to the same artifact sandbox runtime used by agent artifacts
4. sandbox runs the tool/agent artifact adapter
5. backend returns tool result

This keeps tool artifacts and agent artifacts on one runtime path.

## Unification Rule

The current code has two handler contracts:

- RAG artifact: `execute(context)`
- agent/tool artifact: `execute(state, config, context)`

Do not force immediate hard unification in V1 of the sandbox migration.

Instead:

- keep both contracts supported
- make the sandbox runner surface-aware
- pass one normalized payload into the runner
- let the runner invoke the correct adapter for `rag`, `agent`, or `tool`

Longer term, we may add a unified internal ABI, but migration should not block on that.

## Reusing App-Builder Concepts

### Reuse As-Is

- runtime service / client / controller layering
- embedded local runtime for dev
- remote controller support
- dependency hashing
- warm sandbox reuse
- command execution API
- workspace archive/snapshot support

### Reuse With Changes

- session identity
  - app-builder keys on app + user
  - artifacts should key on tenant + artifact-runtime-scope + actor or pool policy
- workspace shape
  - app-builder is a Vite app project
  - artifacts are code packages with small runner adapters
- publish semantics
  - app-builder promotes stage to live workspace
  - artifacts publish from mutable draft to immutable version package

### Do Not Reuse

- Vite preview-server assumptions
- app-specific preview URLs as the primary artifact execution mechanism
- app-builder revision tables as the artifact canonical version store

## Proposed New Backend Components

### New Service Layer

- `backend/app/services/artifact_runtime.py`
  - artifact sandbox session lifecycle
  - draft test execution API
  - published runtime package materialization

- `backend/app/services/artifact_runtime_client.py`
  - mirrors the published app draft runtime client
  - talks to shared sandbox controller

- `backend/app/services/artifact_runtime_local.py`
  - embedded local runtime for dev
  - reuses local runtime manager patterns

### New Execution Runner

Inside sandbox runtime image, add a small runner entrypoint:

- `run_artifact.py`

Responsibilities:
- load manifest and handler from workspace
- validate surface and contract
- deserialize input payload
- run with timeout
- capture stdout/stderr/result/error
- emit structured JSON result

### New Data Model

Suggested tables:

- `artifact_sources`
  - canonical mutable draft source
- `artifact_source_versions`
  - optional checkpoints for authoring history
- `artifact_published_versions`
  - immutable published packages
- `artifact_runtime_sessions`
  - active draft test sessions and pooled published runtime sessions

If we want minimal churn, existing `custom_operators` can temporarily back `artifact_sources`, but published versions should move out of filesystem promotion.

## Session Strategy

### Draft Test Sessions

Session key:
- tenant
- artifact draft id or temp editor session id
- actor id
- runtime class

Properties:
- warm and reusable
- idle timeout
- mutable workspace
- dependency hash tracked

Why:
- keeps test latency low
- avoids reinstalling dependencies on every run
- supports iterative editing

### Published Runtime Sessions

Do not create one session per end user.

Instead use:
- pooled warm workers keyed by runtime class / image / dependency class
- package sync or mount on demand
- optional short-lived per-run isolation inside a long-lived sandbox

This is the key cost-control mechanism.

## Dependency Policy

### Draft Phase

V1 recommendation:
- support a curated preinstalled dependency set
- optionally allow explicit dependency files
- only run install when dependency hash changes

### Publish Phase

Publishing should do the expensive work once:
- validate manifest
- resolve/install dependencies
- build package
- store immutable version metadata
- record content hash and dependency hash

### Runtime Phase

Production execution should not perform arbitrary ad hoc installs.

It should:
- use prebuilt runtime images where possible
- or reuse a resolved package environment
- or fail fast if runtime requirements are unavailable

## Sandbox Controller Contract Extensions

The existing controller can be extended instead of replaced.

Add artifact-oriented endpoints or a profile parameter:

- `POST /sessions/start` with `profile=artifact_draft|artifact_published`
- `PATCH /sessions/{id}/sync`
- `POST /sessions/{id}/run-command`
- `POST /sessions/{id}/artifact/execute`
- `POST /sessions/{id}/stage/prepare`
- `POST /sessions/{id}/stage/snapshot`
- `POST /sessions/{id}/stage/promote`

`artifact/execute` should be preferred over raw `run-command` for normal app code paths because it gives:
- stable payload schema
- structured result envelope
- policy enforcement
- central logging hooks

## Security Model

Required constraints:

- sandbox workspace path scoping only
- strict timeout and memory ceilings
- network policy by artifact policy class
- explicit secret injection allowlist
- no direct backend DB/session object access from artifact code
- only serialized input payload enters sandbox
- only serialized result payload exits sandbox

Builtin/platform artifacts may use a more privileged policy class than tenant artifacts, but this must be explicit.

## Observability

Every artifact run should emit:

- artifact id
- version
- tenant id
- surface (`draft_test|rag|agent|tool`)
- session id / sandbox id
- dependency hash
- content hash
- execution duration
- timeout / exit code / error type
- stdout/stderr truncation markers

These events should feed the same execution-event and trace pipeline already used by agent runs where possible.

## Migration Plan

### Phase 1: Draft Tests on Sandbox

- add artifact runtime service/client/local manager
- move `/admin/artifacts/test` off in-process execution
- keep current storage model temporarily

Outcome:
- immediate safety improvement for user-authored draft tests
- no filesystem promotion dependency for testing

### Phase 2: Published Artifact Package Model

- introduce canonical published artifact storage in DB + object/blob storage
- stop writing tenant artifacts into `backend/artifacts/`
- keep filesystem artifacts only for builtins/dev fixtures

Outcome:
- SaaS-safe artifact storage and versioning

### Phase 3: Runtime Integration

- RAG execution resolves published packages through artifact runtime service
- agent/tool artifact execution resolves through same service
- filesystem registry remains only for builtins

Outcome:
- one production execution model across surfaces

### Phase 4: Cleanup

- retire draft DB custom-operator runtime path for RAG
- retire tenant filesystem promotion path
- align API/schema around `draft source` vs `published version`

## Explicit Non-Goals

Not part of the first migration:

- forcing a single handler ABI for all artifact surfaces
- allowing arbitrary package managers and unrestricted dependency installs in production
- replacing the existing app-builder sandbox substrate

## Recommended Decision

Proceed with a shared sandbox platform and a new artifact runtime layer on top of it.

Concretely:

- keep the app-builder sandbox controller/client/local-runtime substrate
- add an artifact runtime profile instead of a second sandbox system
- move draft testing to sandbox execution first
- move published artifact storage off local filesystem next
- then switch RAG, agent, and tool artifact runtime to resolve immutable published packages through the sandbox runtime

This gives the right tradeoff:
- low churn in sandbox infrastructure
- low draft-test latency through warm reuse and dependency hashing
- production-safe storage and execution model for multi-tenant SaaS
