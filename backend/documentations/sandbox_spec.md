Last Updated: 2026-03-10

# Sandbox Spec

## Purpose

This document is the current implementation and architecture reference for the sandbox platform used by Talmudpedia.

It covers:
- the shared provider-abstracted sandbox base
- the current Sprite integration for App Builder
- the archived E2B integration kept in-repo as legacy code
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
- [backend/app/services/published_app_sandbox_backend_sprite.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_sandbox_backend_sprite.py)
- [backend/app/services/published_app_sprite_proxy_tunnel.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_sprite_proxy_tunnel.py)
- [backend/app/services/published_app_sandbox_backend_e2b.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_sandbox_backend_e2b.py)
- [backend/app/services/published_app_sandbox_backend_e2b_runtime.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_sandbox_backend_e2b_runtime.py)
- [backend/app/services/published_app_sandbox_backend_e2b_workspace.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_sandbox_backend_e2b_workspace.py)
- [backend/app/services/apps_builder_trace.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/apps_builder_trace.py)
- [backend/app/services/published_app_draft_dev_runtime.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_draft_dev_runtime.py)
- [backend/app/services/published_app_draft_dev_runtime_client.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/published_app_draft_dev_runtime_client.py)
- [backend/app/api/routers/published_apps_builder_preview_proxy.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/api/routers/published_apps_builder_preview_proxy.py)
- [backend/app/db/postgres/models/published_apps.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/db/postgres/models/published_apps.py)
- [backend/alembic/versions/2a4c6e8f1b3d_add_draft_dev_runtime_backend_metadata.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/alembic/versions/2a4c6e8f1b3d_add_draft_dev_runtime_backend_metadata.py)
- [backend/alembic/versions/6c8b7a2d9e4f_add_published_app_draft_workspaces.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/alembic/versions/6c8b7a2d9e4f_add_published_app_draft_workspaces.py)

## Current App Builder State

App Builder is now hard-cut to Sprites for draft runtime.

Current runtime semantics:
- one persistent shared Sprite per app
- one canonical shared workspace per app
- draft preview served from the latest successful preview-build snapshot, not `vite dev`
- coding-agent runs write directly into that canonical workspace
- user draft-dev sessions act as attachment/auth records pointing to the shared app workspace
- App Builder preview continues to flow through the backend preview proxy
- E2B code remains in the repo but is archived for App Builder runtime selection

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
- currently implemented for `local`, `controller`, `sprite`, and archived `e2b`
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
- `sprite`
- `e2b` (archived for App Builder)

Selection rules:
- `APPS_SANDBOX_BACKEND` explicitly selects the backend
- App Builder defaults to `sprite`
- `e2b` is intentionally rejected for active App Builder runtime construction

Important implementation detail:
- explicit client config must win over ambient env defaults
- this was enforced so existing controller-style clients continue to behave correctly even when the process env prefers another backend

## Runtime Session Persistence

The app-builder draft-dev session model now stores backend identity and provider metadata.

Current persisted fields on `PublishedAppDraftDevSession`:
- `runtime_generation`
- `runtime_backend`
- `backend_metadata`

Purpose:
- make runtime ownership explicit across restarts
- identify which backend owns a session
- persist provider-specific recovery or routing metadata
- support provider reconciliation and reconnect/recovery logic

Migration:
- [backend/alembic/versions/2a4c6e8f1b3d_add_draft_dev_runtime_backend_metadata.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/alembic/versions/2a4c6e8f1b3d_add_draft_dev_runtime_backend_metadata.py)

Important operational note:
- any ORM query that serializes draft-dev sessions must eagerly load these columns
- a `MissingGreenlet` bug was already hit when response serialization lazily loaded `runtime_backend` in async request flow

## Shared Session Semantics

The app-builder runtime semantics above the backend abstraction are now:
- one active draft-dev session per `(app_id, user_id)`
- generation-based runtime ownership for that session scope
- dependency-hash based install reuse
- mutable canonical workspace
- long-lived preview build watcher plus static preview server
- publish/version materialization from preview build snapshots
- OpenCode runs tied to the same sandbox/workspace as the preview session

The backend abstraction changes the runtime substrate, not the higher-level app-builder lifecycle.

## Supported Backends

### Sprite Backend

`SpriteSandboxBackend` is the active managed provider integration for App Builder.

Characteristics:
- one persistent shared Sprite per app
- Sprite services own preview-builder, static preview, and OpenCode process lifecycle
- filesystem persists across hibernation, so dependency installs are reused
- backend metadata stores provider routing/auth details instead of exposing raw provider URLs to the browser
- backend reaches private OpenCode service ports through the Sprite proxy websocket API, not direct public `:4141` URLs
- hard-cut default backend for App Builder

Use case:
- primary managed runtime for App Builder draft development
- likely base substrate for later artifact work, if that path remains desirable

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
- compatibility with existing controller-based environments that still need it outside the App Builder hard cut

### Archived E2B Backend

`E2BSandboxBackend` remains in-repo as archived legacy code.

Characteristics:
- no longer selectable for active App Builder runtime construction
- retained only as implementation history and possible reference for later artifact decisions

Use case:
- none for active App Builder runtime

## Sprite Base Implementation

### Purpose

Sprites provide the persistent managed execution environment for App Builder.

Talmudpedia still owns:
- app workspace persistence in Postgres
- auth
- preview proxy URL policy
- shared live/stage workspace semantics
- backend selection
- recovery strategy
- publish/version storage

Sprites own:
- persistent filesystem
- exec/session primitives
- service lifecycle
- network exposure and URL routing

### Sprite OpenCode Transport

OpenCode is now treated as a private in-Sprite service.

Current transport shape:
- preview remains the HTTP-facing Sprite service behind the backend preview proxy
- OpenCode binds inside the Sprite on `127.0.0.1:4141`
- backend creates a local TCP tunnel through the Sprite proxy websocket API
- the inner `OpenCodeServerClient` talks to `http://127.0.0.1:<local-tunnel-port>`
- workspace bootstrap remains owned by the outer Sprite sandbox backend, not by the inner OpenCode HTTP client
- draft-dev heartbeat waits for preview readiness instead of restarting services on every reattach
- preview proxy retries transient warmup `404/5xx/timeout` responses for GET/HEAD asset requests during Sprite wake
- stage promotion mirrors files into the existing live workspace in place so Vite keeps a stable working directory while changes land

Reason for this design:
- direct `https://<sprite>.sprites.app:4141` access is not a reliable production transport for a private service port
- the Sprite proxy/control surface is the provider-native way to reach private ports from the backend
- keeping OpenCode behind a standard localhost HTTP client preserves the existing event and run APIs without another provider-specific protocol layer inside the coding-agent runtime

### Environment Configuration

Current Sprite-related runtime env vars:
- `SPRITES_TOKEN`
- `APPS_SANDBOX_BACKEND`
- `APPS_SPRITE_API_BASE_URL`
- `APPS_SPRITE_API_TOKEN`
- `APPS_SPRITE_NAME_PREFIX`
- `APPS_SPRITE_WORKSPACE_PATH`
- `APPS_SPRITE_STAGE_WORKSPACE_PATH`
- `APPS_SPRITE_PUBLISH_WORKSPACE_PATH`
- `APPS_SPRITE_PREVIEW_PORT`
- `APPS_SPRITE_OPENCODE_PORT`
- `APPS_SPRITE_PREVIEW_SERVICE_NAME`
- `APPS_SPRITE_OPENCODE_SERVICE_NAME`
- `APPS_SPRITE_OPENCODE_COMMAND`
- `APPS_SPRITE_COMMAND_TIMEOUT_SECONDS`
- `APPS_SPRITE_RETENTION_SECONDS`
- `APPS_SPRITE_NETWORK_POLICY`

## Shared Tracing

The app-builder stack now emits a shared lifecycle trace stream instead of relying only on scattered `logger.info` lines.

Primary trace helper:
- [backend/app/services/apps_builder_trace.py](/Users/danielbenassaya/Code/personal/talmudpedia/backend/app/services/apps_builder_trace.py)

Current trace domains include:
- `draft_dev.runtime`
- `sandbox.sprite`
- `preview.proxy`
- `coding_agent.runtime`
- `coding_agent.monitor`
- `coding_agent.finalizer`
- `coding_agent.opencode_client`
- `publish.runtime`

Important implementation detail:
- the existing coding-agent `pipeline_trace(...)` path now mirrors into the shared app-builder trace file, so coding-agent runs and sandbox lifecycle events can be correlated in one stream

Current trace env vars:
- `APPS_BUILDER_TRACE_ENABLED`
- `APPS_BUILDER_TRACE_FILE`
- existing coding-agent trace env vars still work for the legacy per-pipeline file, but they now also feed the shared app-builder trace stream

Current coverage includes:
- draft-dev session ensure/start/sync/heartbeat/stop/expiry
- Sprite workspace ensure/sync/heartbeat/stop/destroy
- stage workspace prepare/snapshot/promote
- preview proxy HTTP/websocket lifecycle
- coding-agent pipeline events via bridge
- batch finalization and revision creation
- sandbox publish snapshot/install/build/upload/finalize lifecycle

Startup rule:
- if `APPS_SANDBOX_BACKEND=sprite`, the backend process must have `APPS_SPRITE_API_TOKEN` or `SPRITES_TOKEN`
- startup fails fast with a clear error if Sprite auth is missing
- App Builder defaults to `sprite`
- `e2b` is intentionally rejected for active App Builder boot
- no App Builder provider fallback should silently move the user back to E2B or local

### Workspace Contract

The Sprite backend uses stable per-app workspace roots inside the persistent Sprite filesystem.

Current responsibilities:
- ensure the shared app Sprite exists
- sync incoming project files into the live workspace
- preserve dependency marker semantics
- manage preview/OpenCode as named Sprite services
- expose internal connection data for proxying

Important implementation note:
- workspace listing must preserve leading-dot filenames
- this is required so hidden runtime markers like `.draft-dev-dependency-hash` round-trip correctly for the coding-agent stage workspace flow
- OpenCode startup ensures the workspace-local runtime directories exist before service startup

### Process Model

Inside the Sprite, the runtime is expected to manage:
- a preview service rooted at the shared live workspace
- an OpenCode service rooted at the shared Sprite environment

The important design choice is:
- one shared Sprite per app
- preview and OpenCode share the same persistent app environment
- stage/live workspaces are directory-level concepts inside that Sprite
- user sessions attach to the shared workspace instead of owning separate provider instances

That keeps coding-agent edits, manual edits, and preview behavior consistent across all editors attached to the app.

### Security Boundary

Raw provider preview hosts are not returned to the frontend as product URLs.

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

The runtime layer now returns proxied preview URLs plus provider-neutral upstream metadata instead of provider-native browser URLs.

## App-Builder Specific Implementation

### Main Service Roles

`PublishedAppDraftDevRuntimeService` remains the product-facing orchestration layer for draft-dev app sessions and shared app workspaces.

Responsibilities:
- ensure or reuse the shared draft workspace for the app
- ensure or reuse the active attachment session for the caller
- compute dependency hashes
- decide when dependencies must be reinstalled
- persist workspace/session metadata
- decorate session responses
- coordinate preview token behavior
- sweep dormant shared workspaces when no sessions remain attached

`PublishedAppDraftDevRuntimeClient` is now a thin facade that delegates to the selected backend adapter.

This preserves the previous service contract while swapping the substrate below it.

### Current Draft-Dev Flow

1. User requests or resumes a draft-dev session.
2. Service loads the app revision and computes dependency hash.
3. Service ensures a shared draft workspace row exists for `app_id`.
4. Service ensures a session row exists for `(app_id, user_id)` and attaches it to that workspace.
5. Client selects the configured backend.
6. Service increments `runtime_generation` when a new shared Sprite must be created.
7. Backend ensures the Sprite exists, ensures preview/OpenCode services exist, and syncs the live workspace.
8. Service persists:
   - `draft_workspace_id`
   - `sandbox_id` as the shared Sprite identity where legacy fields still exist
   - `runtime_generation`
   - `runtime_backend`
   - `backend_metadata`
   - preview and workspace details
9. Response returns a platform proxy preview URL.

### Shared Workspace State Model

`PublishedAppDraftWorkspace` is the provider-owned app runtime record.

Current responsibilities:
- own the shared Sprite identity for the app
- store provider metadata and service routing data
- track lifecycle/health separate from user attachment rows
- provide a single concurrency boundary for shared coding-agent batches

Current design choice:
- one workspace per app
- many user attachment sessions per workspace
- destroying a user session does not destroy the Sprite
- deleting the app or sweeping a dormant unattached workspace destroys the Sprite

### Runtime State Model

Draft-dev sessions and workspaces use explicit health states instead of collapsing almost everything into `running`.

Current states:
- `starting`
- `building`
- `serving`
- `degraded`
- `running`
- `stopping`
- `stopped`
- `expired`
- `error`

Current interpretation:
- `serving` is the canonical healthy state for a ready preview
- `running` is kept as a compatibility state for older rows/clients
- `building` means the workspace is provisioning or reinstalling dependencies
- `degraded` means the workspace exists but the preview/runtime health check failed and needs restart or recovery
- `stopping` is transient teardown before the row becomes `stopped` or `expired`

### Dependency Install Reuse

The dependency optimization from the previous runtime was preserved:
- dependency hash is computed from project dependency manifests
- installs are skipped when the hash has not changed
- installs run only when the dependency hash changes or the workspace is fresh

This matters for Sprites because the persistent filesystem should eliminate unnecessary reinstall churn.

### Stage And Publish Workspace Flows

The backend interface preserves the existing app-builder workspace lifecycle:
- prepare stage workspace
- snapshot stage or live workspace
- promote stage workspace into live
- prepare publish dependencies
- archive workspace

This means the sandbox layer is not just “run preview”; it also supports the app-builder’s internal workspace transitions.

### Snapshot Filtering

Snapshot filtering now happens at the sandbox producer boundary instead of only after the backend receives the payload.

Current hard-cut behavior:
- Sprite snapshot walks skip generated and high-noise paths before serializing the response
- the backend still keeps late filtering as a defensive second layer
- this prevents coding-agent finalization and publish flows from exploding on `node_modules`, cache trees, dist output, or other non-source artifacts

### OpenCode Integration

OpenCode runs are tied to the same shared Sprite as the preview environment.

Current reasons:
- agent edits and preview state stay aligned
- the agent sees the same filesystem the preview server sees
- stage/live flows can operate inside the same persistent app environment
- service restart/recovery is provider-native instead of PID-driven

`OpenCodeServerClient` now recognizes `sprite` as an active sandbox runtime.

Current Sprite/OpenCode runtime assumptions:
- OpenCode is exposed through a dedicated Sprite service
- the service shares the app Sprite filesystem
- provider auth and routing stay server-side
- the backend keeps the frontend/browser contract stable while the provider remains an implementation detail

### Shared Coding-Agent Batch Model

The coding-agent batch scope is now app-wide.

Current semantics:
- one shared stage workspace per app
- prompts from any attached editor join the same active app batch
- manual writes to the shared live workspace are blocked while that batch is active
- finalization promotes stage to live once for the app batch
- a completed batch produces one revision outcome that is associated back to all finalized runs in that batch

### Local Preview Base Path Support

The local draft-dev runtime continues to accept preview base path configuration.

Purpose:
- make proxied preview URLs work even for embedded local runtime
- keep local and Sprite preview behavior aligned at the browser contract layer

## Current Limitations

The new substrate is in place, but some parts are still intentionally incomplete:
- the remote sweeper is currently request-driven best effort, not a dedicated scheduled background job
- tenant or environment-specific rollout controls are still to be added
- artifact runtime migration is not implemented yet
- Sprite checkpoints are intentionally not used for App Builder version history or coding-agent checkpointing
- the current local backend remains a manual fallback and should not silently replace a failed Sprite workspace

## Suggested Operational Defaults

For now, the safest intended operating mode is:
- default backend: `sprite`
- explicit manual fallback: `local` or `controller`
- no silent fallback across backends once a workspace exists
- proxied preview URLs only
- Sprite auth required at startup when Sprite is selected

## Artifact Migration Fit

The current sandbox base was deliberately designed so artifacts can migrate onto it later.

What already fits artifacts well:
- provider-neutral workspace identity
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

- Sprite-specific runtime assumptions must stay behind the backend interface.
- Session and workspace metadata must be eagerly loaded in async request flows to avoid lazy-load errors.
- Preview proxy behavior, especially websocket/HMR traffic, needs live validation.
- If artifact migration later requires stronger isolation policy, the abstraction should add runtime profiles, not split into a second sandbox platform.
- Documentation overlap already exists; this file should be treated as the canonical spec to reduce drift.

## Recommended Next Steps

1. Add a scheduled dormant-workspace sweeper instead of keeping the current request-driven best effort.
2. Add rollout controls by environment and tenant if App Builder runtime selection becomes dynamic again.
3. Start the artifact migration with sandboxed draft test execution.
4. Decide whether artifact runtime remains on E2B or receives a separate Sprite-native design.
5. Keep the archived E2B notes short and non-canonical so this spec remains the primary source of truth.
