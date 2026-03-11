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

## Current Execution Surfaces

### Test runs

Artifact admin test runs use `ArtifactExecutionService.start_test_run()`.

Current behavior:
- resolve saved draft/published revision or materialize an ephemeral revision from request source files
- resolve or create a `staging` deployment by build hash
- create run and initial events
- dispatch through the Cloudflare Dispatch Worker eagerly or through Celery depending on queue mode

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
- tenant artifacts now execute on Cloudflare Workers for Platforms
- repo builtin artifacts and some compatibility paths still remain in the system

## Current Runtime Flow

1. resolve an artifact revision
2. create an artifact run record
3. persist initial run events
4. dispatch execution eagerly or through Celery
5. resolve or create a Cloudflare deployment in `staging` or `production`
6. send a dispatch request to the platform Dispatch Worker
7. persist final run state and ordered run events

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
- reduction of remaining compatibility read/execution paths

Important current reality:
- queue fairness still relies on the existing queue classes and worker consumption behavior
- there is not yet a separate platform scheduler enforcing stronger tenant-level fairness, weighted priorities, or admission control inside a queue class
- interactive traffic is better isolated than before because it uses a separate queue class, but fairness within a queue is still limited by the current Celery/worker model
- tenant artifacts are now constrained to a Workers-compatible Python model rather than the previous backend bundle/worker sandbox assumptions

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
