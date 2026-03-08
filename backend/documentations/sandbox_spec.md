Last Updated: 2026-03-08

# Sandbox Spec

## Purpose

This document is the current implementation and architecture reference for the sandbox platform used by Talmudpedia.

It covers:
- the shared provider-abstracted sandbox base
- the current E2B integration
- the app-builder specific runtime implementation
- the planned artifact migration onto the same substrate

## Scope

This spec is backend-focused. It describes the sandbox control plane that the backend owns and the runtime environments it manages for app-builder and, later, artifacts.

It does not attempt to fully specify frontend preview UX, artifact authoring UX, or publish hosting for production apps.

## Current Source Of Truth

The current implementation lives primarily in:
- [backend/app/services/published_app_sandbox_backend.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_sandbox_backend.py)
- [backend/app/services/published_app_sandbox_backend_factory.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_sandbox_backend_factory.py)
- [backend/app/services/published_app_sandbox_backend_local.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_sandbox_backend_local.py)
- [backend/app/services/published_app_sandbox_backend_controller.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_sandbox_backend_controller.py)
- [backend/app/services/published_app_sandbox_backend_e2b.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_sandbox_backend_e2b.py)
- [backend/app/services/published_app_sandbox_backend_e2b_workspace.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_sandbox_backend_e2b_workspace.py)
- [backend/app/services/published_app_draft_dev_runtime.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_draft_dev_runtime.py)
- [backend/app/services/published_app_draft_dev_runtime_client.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_draft_dev_runtime_client.py)
- [backend/app/api/routers/published_apps_builder_preview_proxy.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_builder_preview_proxy.py)
- [backend/app/db/postgres/models/published_apps.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/db/postgres/models/published_apps.py)
- [backend/alembic/versions/2a4c6e8f1b3d_add_draft_dev_runtime_backend_metadata.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/alembic/versions/2a4c6e8f1b3d_add_draft_dev_runtime_backend_metadata.py)

## Documentation Overlap

Two existing docs overlap with this one:
- [backend/documentations/apps_builder_e2b_runtime_migration_status.md](/Users/danielbenassaya/Code/personal/talmudpedia/backend/documentations/apps_builder_e2b_runtime_migration_status.md)
- [backend/documentations/artifact_sandbox_architecture.md](/Users/danielbenassaya/Code/personal/talmudpedia/backend/documentations/artifact_sandbox_architecture.md)

Current relationship:
- this file is the broad implementation spec
- `apps_builder_e2b_runtime_migration_status.md` is a narrower rollout/status note
- `artifact_sandbox_architecture.md` is an artifact-focused design note

Suggestion:
- keep this file as the canonical sandbox spec
- keep the other two only if they remain shorter, topic-specific companions
- if they start repeating implementation detail from this file, merge or trim them

## High-Level Architecture

The sandbox platform is split into two layers:

1. Product control plane
- owned by the Talmudpedia backend
- decides when to create, sync, heartbeat, stop, and proxy runtime sessions
- persists runtime session metadata in Postgres

2. Sandbox backend
- the actual execution provider
- currently implemented for `local`, `controller`, and `e2b`
- selected explicitly by configuration

The design principle is:
- one stable backend interface
- multiple backend adapters
- product services stay mostly unchanged above that line

## Backend Abstraction

The provider-neutral contract is defined by `PublishedAppSandboxBackend`.

It includes:
- session lifecycle
  - `start_session`
  - `sync_session`
  - `heartbeat_session`
  - `stop_session`
  - `resolve_workspace_path`
- workspace/file operations
  - `list_files`
  - `read_file`
  - `read_file_range`
  - `search_code`
  - `workspace_index`
  - `apply_patch`
  - `write_file`
  - `delete_file`
  - `rename_file`
  - `snapshot_files`
- workspace flow operations
  - `prepare_stage_workspace`
  - `snapshot_workspace`
  - `promote_stage_workspace`
  - `prepare_publish_workspace`
  - `prepare_publish_dependencies`
  - `export_workspace_archive`
  - `sync_workspace_files`
- command/process operations
  - `run_command`
- OpenCode operations
  - `start_opencode_run`
  - `stream_opencode_events`
  - `cancel_opencode_run`
  - `answer_opencode_question`

This interface was intentionally designed to be broad enough for artifact runtime adoption later, not only app-builder draft-dev.

## Backend Selection Model

Backend construction is handled by `build_published_app_sandbox_backend()` in the factory module.

Current backends:
- `local`
- `controller`
- `e2b`

Selection rules:
- `APPS_SANDBOX_BACKEND` explicitly selects the backend
- if no explicit backend is set and a controller URL is configured, use `controller`
- otherwise default to `e2b`

Important implementation detail:
- explicit client config must win over ambient env defaults
- this was enforced so existing controller-style clients continue to behave correctly even when the process env prefers another backend

## Runtime Session Persistence

The app-builder draft-dev session model now stores backend identity and provider metadata.

Current persisted fields on `PublishedAppDraftDevSession`:
- `runtime_backend`
- `backend_metadata`

Purpose:
- identify which backend owns a session
- persist provider-specific recovery or routing metadata
- support future reconnect/recovery logic

Migration:
- [backend/alembic/versions/2a4c6e8f1b3d_add_draft_dev_runtime_backend_metadata.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/alembic/versions/2a4c6e8f1b3d_add_draft_dev_runtime_backend_metadata.py)

Important operational note:
- any ORM query that serializes draft-dev sessions must eagerly load these columns
- a `MissingGreenlet` bug was already hit when response serialization lazily loaded `runtime_backend` in async request flow

## Shared Session Semantics

The app-builder runtime semantics above the backend abstraction were preserved:
- one active draft-dev session per `(app_id, user_id)`
- dependency-hash based install reuse
- mutable live workspace
- separate stage workspace
- stage promotion into live workspace
- publish workspace preparation from live workspace
- OpenCode runs tied to the same sandbox/workspace as the preview session

The backend abstraction changes the runtime substrate, not the higher-level app-builder lifecycle.

## Supported Backends

### Local Backend

`LocalSandboxBackend` wraps the existing `LocalDraftDevRuntimeManager`.

Characteristics:
- embedded local execution
- useful for development and manual fallback
- no provider network call
- preview served from the local process runtime
- supports file/workspace/stage/publish/command operations
- does not support remote OpenCode sandbox APIs

Use case:
- local development fallback
- low-friction debugging

### Controller Backend

`ControllerSandboxBackend` preserves the older remote-controller shape.

Characteristics:
- HTTP transport to the sandbox controller API
- operation-specific timeouts
- remote OpenCode support
- preview metadata extracted from returned preview URLs

Use case:
- compatibility with existing controller-based environments
- transition path while the E2B path is being proven

### E2B Backend

`E2BSandboxBackend` is the new primary managed provider integration.

Characteristics:
- hosted E2B sandbox provisioning
- workspace root normalized to `/workspace`
- preview server and OpenCode run inside the same sandbox
- backend metadata stores provider connection details instead of exposing raw hosts to the browser
- intended default backend when no controller override exists

Use case:
- primary managed sandbox substrate for app-builder
- future shared substrate for artifacts

## E2B Base Implementation

### Purpose

E2B is used as the sandbox provider, not as the full product control plane.

Talmudpedia still owns:
- session persistence
- auth
- preview URL policy
- workspace semantics
- backend selection
- recovery strategy
- rollout logic

E2B owns:
- sandbox execution environment
- filesystem and process isolation
- sandbox lifecycle primitives

### Environment Configuration

Current E2B-related runtime env vars:
- `E2B_API_KEY`
- `APPS_SANDBOX_BACKEND`
- `APPS_E2B_TEMPLATE`
- `APPS_E2B_SANDBOX_TIMEOUT_SECONDS`
- `APPS_E2B_WORKSPACE_PATH`
- `APPS_E2B_PREVIEW_PORT`
- `APPS_E2B_OPENCODE_PORT`
- `APPS_E2B_SECURE`
- `APPS_E2B_ALLOW_INTERNET_ACCESS`
- `APPS_E2B_AUTO_PAUSE`

Startup rule:
- if `APPS_SANDBOX_BACKEND=e2b`, the backend process must have `E2B_API_KEY`
- startup now fails fast with a clear error if that key is missing

### Workspace Contract

The E2B backend uses `/workspace` as the normalized root.

Current responsibilities:
- sync incoming project files into the workspace
- preserve dependency marker semantics
- manage preview/OpenCode background processes in the same sandbox
- expose internal connection data for proxying

### Process Model

Inside the sandbox, the runtime is expected to manage:
- a Vite preview process
- optionally an OpenCode server process

The important design choice is:
- one sandbox per active draft-dev session
- preview and OpenCode share the same workspace and file state

That keeps coding-agent edits and preview behavior consistent.

### Security Boundary

Raw E2B preview hosts are not returned to the frontend as product URLs.

Instead:
- backend stores upstream preview connection details in `backend_metadata`
- frontend receives a Talmudpedia-owned proxy URL
- the backend proxy forwards traffic to the sandbox host/port

This keeps:
- auth checks under platform control
- browser contract stable
- provider details server-side

## Preview Proxy Architecture

Preview traffic is served through:
- [backend/app/api/routers/published_apps_builder_preview_proxy.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_builder_preview_proxy.py)

Purpose:
- stable platform-owned preview URL
- auth/token enforcement before proxying
- support for browser follow-up requests after the initial preview bootstrap

Current preview URL shape:
- `/public/apps-builder/draft-dev/sessions/{session_id}/preview/...`

The runtime layer now returns proxied preview URLs instead of provider-native browser URLs.

## App-Builder Specific Implementation

### Main Service Roles

`PublishedAppDraftDevRuntimeService` remains the product-facing orchestration layer for draft-dev app sessions.

Responsibilities:
- ensure or reuse the active draft-dev session
- compute dependency hashes
- decide when dependencies must be reinstalled
- persist sandbox/session metadata
- decorate session responses
- coordinate preview token behavior

`PublishedAppDraftDevRuntimeClient` is now a thin facade that delegates to the selected backend adapter.

This preserves the previous service contract while swapping the substrate below it.

### Current Draft-Dev Flow

1. User requests or resumes a draft-dev session.
2. Service loads the app revision and computes dependency hash.
3. Service ensures a session row exists for `(app_id, user_id)`.
4. Client selects the configured backend.
5. Backend starts or syncs the runtime session.
6. Service persists:
   - `sandbox_id`
   - `runtime_backend`
   - `backend_metadata`
   - preview and workspace details
7. Response returns a platform proxy preview URL.

### Dependency Install Reuse

The dependency optimization from the previous runtime was preserved:
- dependency hash is computed from project dependency manifests
- installs are skipped when the hash has not changed
- installs run only when the dependency hash changes or the session is fresh

This matters for E2B because startup cost would otherwise climb sharply.

### Stage And Publish Workspace Flows

The backend interface preserves the existing app-builder workspace lifecycle:
- prepare stage workspace
- snapshot stage or live workspace
- promote stage workspace into live
- prepare publish workspace
- prepare publish dependencies
- archive workspace

This means the sandbox layer is not just “run preview”; it also supports the app-builder’s internal workspace transitions.

### OpenCode Integration

OpenCode runs are tied to the same sandbox and workspace as the preview session.

Current reasons:
- agent edits and preview state stay aligned
- the agent sees the same files the preview server sees
- stage/live flows can operate on the same edited workspace

`OpenCodeServerClient` was updated to support extra headers, which helps transport/auth integration when routing through the new backend/proxy flow.

### Local Preview Base Path Support

The local draft-dev runtime now accepts preview base path configuration.

Purpose:
- make proxied preview URLs work even for embedded local runtime
- keep local and E2B preview behavior aligned at the browser contract layer

## Current Limitations

The new substrate is in place, but some parts are still intentionally incomplete:
- no confirmed live E2B end-to-end validation against a real template in this spec
- reconnect/recovery paths for orphaned or stale E2B sandboxes still need hardening
- tenant or environment-specific rollout controls are still to be added
- artifact runtime migration is not implemented yet
- the current local backend remains the manual fallback and should not silently replace a failed E2B session

## Suggested Operational Defaults

For now, the safest intended operating mode is:
- default backend: `e2b`
- explicit manual fallback: `local` or `controller`
- no silent fallback across backends once a session exists
- proxied preview URLs only
- E2B API key required at startup when E2B is selected

## Artifact Migration Fit

The current sandbox base was deliberately designed so artifacts can migrate onto it later.

What already fits artifacts well:
- provider-neutral session identity
- command execution in sandbox
- workspace/file sync
- stage/publish workspace primitives
- backend-specific metadata persistence
- support for both local and managed remote execution

What artifacts still need beyond app-builder:
- canonical artifact storage outside platform filesystem
- immutable published artifact packaging/versioning
- artifact-specific session profiles
- artifact-specific runner entrypoints
- surface-aware execution for RAG, agent nodes, and tools

## Suggested Artifact Migration Architecture

### Storage Model

Do not rely on writing tenant artifacts into `backend/artifacts/`.

Recommended split:
- drafts stored in Postgres
- published artifact packages stored in object/blob storage
- builtin artifacts may remain on repo filesystem

### Runtime Profiles

Add artifact runtime profiles on the same sandbox substrate:
- `artifact_draft`
- `artifact_published`

Suggested meaning:
- `artifact_draft`
  - mutable workspace for author/test loop
  - warm reusable session
  - dependency installation controlled by artifact dependency hash
- `artifact_published`
  - immutable versioned package execution
  - suitable for agent, tool, and RAG runtime use

### Execution Surfaces

Artifact execution still has two runtime contracts today:
- RAG: `execute(context)`
- agent/tool: `execute(state, config, context)`

Recommended migration strategy:
- keep both contracts for now
- use a sandbox runner that is aware of the execution surface
- pass normalized execution payload into the runner
- let the runner invoke the correct adapter without forcing immediate ABI unification

### Suggested Rollout Order

1. Replace artifact test execution with sandboxed draft execution.
2. Add canonical published artifact packaging.
3. Move agent artifact nodes to published sandbox execution.
4. Move artifact-backed tools to the same published runtime.
5. Move RAG artifact execution from filesystem import to package-based sandbox execution.
6. Keep filesystem artifacts only for builtins and local fixtures.

## Risks And Watchpoints

- E2B-specific runtime assumptions must stay behind the backend interface.
- Session metadata must be eagerly loaded in async request flows to avoid lazy-load errors.
- Preview proxy behavior, especially websocket/HMR traffic, needs live validation.
- If artifact migration later requires stronger isolation policy, the abstraction should add runtime profiles, not split into a second sandbox platform.
- Documentation overlap already exists; this file should be treated as the canonical spec to reduce drift.

## Recommended Next Steps

1. Run a real E2B end-to-end app-builder session against a concrete template and capture the exact startup/env requirements.
2. Add reconnect/recovery semantics for stale E2B sandbox ids.
3. Add rollout controls by environment and tenant.
4. Start the artifact migration with sandboxed draft test execution.
5. Decide whether to collapse the two older sandbox docs into shorter companion notes that reference this spec.
