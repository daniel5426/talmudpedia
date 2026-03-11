# Artifact Execution Current State

Last Updated: 2026-03-11

This document is the canonical current-state architecture overview for artifact execution.

## Purpose

Artifact execution now has a shared runtime path used by:
- artifact test runs
- artifact-backed tools
- agent artifact nodes
- RAG artifact-backed operators

This document describes the implemented architecture, not just the long-term target state.

## Current Runtime Shape

The current execution path centers on:
- `ArtifactExecutionService`
- `ArtifactRevisionService`
- `ArtifactRunService`
- `ArtifactDeploymentService`
- `CloudflareArtifactClient`
- `CloudflareDispatchClient`
- backend-side tenant runtime policy enforcement

The current backend supports:
- revision-backed execution
- source-tree revision packaging and build-hash computation
- deployment resolution and reuse by namespace + build hash
- artifact run/event persistence
- Cloudflare Workers dispatch for tenant artifacts
- one canonical runtime contract: `execute(inputs, config, context)`

Current runtime modes in the repo are:
- `workers_for_platforms`
  - intended production target with per-revision deployments and dispatch namespaces
- `standard_worker_test`
  - temporary Cloudflare free-plan validation mode using one shared runtime Worker and inline source-tree dispatch

This distinction matters because the codebase currently supports both:
- the intended Workers for Platforms production shape
- the temporary free-plan test shape that is usable before dispatch namespaces are enabled

## Current Execution Surfaces

### Test runs

Artifact admin test runs use `ArtifactExecutionService.start_test_run()`.

Current behavior:
- resolve saved draft/published revision or materialize an ephemeral revision from request source files
- resolve or create a `staging` deployment by build hash
- create run and initial events
- dispatch through the Cloudflare Dispatch Worker eagerly or through Celery depending on queue mode

In `standard_worker_test` mode, test runs:
- still use the shared run/event control plane
- still use `staging` semantics in metadata
- dispatch source files and entry module path inline to the shared free-plan Worker instead of resolving a per-revision deployed User Worker

### Live agent execution

Agent artifact execution already calls `ArtifactExecutionService.execute_live_run()` for tenant artifact revisions.

### Live tool execution

Artifact-backed tools already call `ArtifactExecutionService.execute_live_run()` and require published immutable revisions in production execution mode.

### Live RAG execution

Artifact-backed RAG operators already call `ArtifactExecutionService.execute_live_run()`.

## Important Correction To Older Docs

Older artifact docs described live agent/tool/RAG execution as “not yet migrated” or broadly pending.

That is no longer fully accurate.

Current code already routes these live surfaces into the shared artifact runtime:
- `backend/app/agent/executors/tool.py`
- `backend/app/agent/executors/artifact.py`
- `backend/app/rag/pipeline/operator_executor.py`

The more accurate current statement is:
- the shared artifact runtime is already used by test runs and several live execution paths
- tenant artifacts execute on Cloudflare Workers-compatible runtime paths
- `platform_sdk` is seeded as a system-owned artifact inside the same revision/runtime model
- repo-backed runtime artifact execution paths have been removed from the canonical control plane

## Current Runtime Flow

1. resolve an artifact revision
2. create an artifact run record
3. persist initial run events
4. dispatch execution eagerly or through Celery
5. resolve or create a Cloudflare deployment in `staging` or `production`
6. send a dispatch request to the platform Dispatch Worker
7. persist final run state and ordered run events

When the repo is running in `standard_worker_test` mode:
- deployment resolution is still recorded in backend metadata
- dispatch goes to the shared free-plan Worker URL
- the request carries `source_files`, `entry_module_path`, and inputs/config/context directly

## Current Worker/Queue Model

Current queue classes in the system include:
- `artifact_prod_interactive`
- `artifact_prod_background`
- `artifact_test`

Current intent for those queue classes is:
- `artifact_test`
  - artifact admin test runs only
- `artifact_prod_interactive`
  - live user-facing work such as agent turns, artifact-backed tool calls, and inline retrieval/runtime execution
- `artifact_prod_background`
  - standalone pipeline jobs and other non-user-blocking artifact workloads

In platform terms, this means the system now has separate lanes for test traffic, interactive production traffic, and background production traffic.

Current namespace/runtime choices include:
- `staging` namespace for artifact-page author testing
- `production` namespace for live published execution
- synchronous dispatch for `artifact_prod_interactive`
- Celery-dispatched background execution for queued workloads

## Current Limits And Transitional Reality

The artifact runtime is implemented, but it is still a V1 runtime foundation.

Areas still evolving:
- stronger worker scheduling/fairness controls
- fully hardened multi-worker deployment model
- migration of repo builtin artifacts onto the same broader runtime model

Important current reality:
- queue fairness still relies on the existing queue classes and worker consumption behavior
- there is not yet a separate platform scheduler enforcing stronger tenant-level fairness, weighted priorities, or admission control inside a queue class
- interactive traffic is better isolated than before because it uses a separate queue class, but fairness within a queue is still limited by the current Celery/worker model
- tenant artifacts are now constrained to a Workers-compatible Python model rather than the previous backend bundle/worker sandbox assumptions
- per-artifact Python dependency installation is not active in the temporary `standard_worker_test` mode; that mode is for runtime-path validation, not final dependency fidelity

## Canonical Implementation References

- `backend/app/services/artifact_runtime/execution_service.py`
- `backend/app/services/artifact_runtime/revision_service.py`
- `backend/app/services/artifact_runtime/run_service.py`
- `backend/app/services/artifact_runtime/deployment_service.py`
- `backend/app/services/artifact_runtime/cloudflare_client.py`
- `backend/app/services/artifact_runtime/cloudflare_dispatch_client.py`
- `backend/app/workers/artifact_tasks.py`
- `runtime/cloudflare-artifacts/dispatch-worker/`
- `runtime/cloudflare-artifacts/outbound-worker/`
