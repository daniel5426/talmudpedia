# Artifact Execution Current State

Last Updated: 2026-03-10

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
- `DifySandboxWorkerClient`
- artifact worker executor/adapter boundaries

The current backend supports:
- revision-backed execution
- bundle generation and storage
- artifact run/event persistence
- worker client direct mode and HTTP mode
- DifySandbox-backed execution through the worker layer

## Current Execution Surfaces

### Test runs

Artifact admin test runs use `ArtifactExecutionService.start_test_run()`.

Current behavior:
- resolve saved or ephemeral revision
- create run and initial events
- dispatch eagerly or through Celery depending on runtime mode

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
- the broader worker scheduling/hardening story is still evolving
- repo builtin artifacts and some compatibility paths still remain in the system

## Current Runtime Flow

1. resolve an artifact revision
2. create an artifact run record
3. persist initial run events
4. dispatch execution eagerly or through Celery
5. send worker execution request through direct or HTTP worker mode
6. execute bundle through the DifySandbox-backed worker path
7. persist final run state and ordered run events

## Current Worker/Queue Model

Current queue classes in the system include:
- `artifact_prod_interactive`
- `artifact_prod_background`
- `artifact_test`

Current runtime choices include:
- direct mode for local/embedded execution path
- HTTP mode for internal worker-service execution path

Local development bootstrap can also auto-start:
- the artifact queue worker
- the artifact worker service
- a local DifySandbox container

## Current Limits And Transitional Reality

The artifact runtime is implemented, but it is still a V1 runtime foundation.

Areas still evolving:
- stronger worker scheduling/fairness controls
- fully hardened multi-worker deployment model
- reduction of remaining compatibility read/execution paths

## Canonical Implementation References

- `backend/app/services/artifact_runtime/execution_service.py`
- `backend/app/services/artifact_runtime/revision_service.py`
- `backend/app/services/artifact_runtime/run_service.py`
- `backend/app/services/artifact_runtime/difysandbox_client.py`
- `backend/app/artifact_worker/executor.py`
- `backend/app/artifact_worker/difysandbox_adapter.py`
- `backend/app/workers/artifact_tasks.py`
- `backend/main.py`
