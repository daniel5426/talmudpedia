# Backend Architecture Current State

Last Updated: 2026-04-09

This document is the current backend architecture overview for Talmudpedia. It is intended to replace the older backend architecture summary in `backend/ARCHITECTURE.md`.

## Purpose

The backend is a FastAPI-based control plane and runtime platform for:
- agent authoring and execution
- RAG pipeline authoring and execution
- knowledge-store-backed retrieval
- published app hosting and builder workflows
- artifact packaging and isolated execution
- governance, audit, and tenant-scoped administration

## Architecture Anchors

- `code_architect/architecture_tree.md`
  - Canonical fast-read backend map for implementation work.
- `backend/main.py`
  - Runtime composition root: startup, infra bootstrap, and router registration.
- `backend/app/api/routers/`
  - HTTP and websocket surface, organized by domain.
- `backend/app/services/`
  - Business logic and orchestration layer.
- `backend/app/agent/`
  - Agent graph compilation, runtime adapters, execution services, and node executors.
- `backend/app/rag/`
  - RAG pipeline compilation, execution, providers, and vector-store abstractions.

## Runtime Layers

### API Layer

The API surface is broad and domain-oriented rather than being a thin single-purpose app.

Key route groups currently registered in `backend/main.py` include:
- auth and internal auth
- agents, agent graph mutations, and run logs
- RAG admin, pipelines, graph mutations, operator contracts, and websocket updates
- artifacts and artifact runs
- published app admin, public, host runtime, builder preview, and sandbox dev shim routes
- models, tools, knowledge stores, settings, stats, RBAC, audit, org units
- library, texts, search, STT, TTS, and voice websocket routes

This means the backend acts as both:
- the platform control plane for internal/admin operations
- the runtime edge for selected hosted experiences such as published apps and voice sessions

### Service Layer

The service layer in `backend/app/services/` is the main coordination boundary. Routers mostly validate requests and dispatch into services.

Important service areas:
- `agent_service.py`
  - CRUD, validation, versioning, and compile-time checks for agents.
- `retrieval_service.py`
  - Retrieval interface shared by agent and RAG flows.
- `rag_admin_service.py`
  - Admin and configuration logic for RAG-side management concerns.
- `graph_mutation_service.py`, `agent_graph_mutation_service.py`, `rag_graph_mutation_service.py`
  - Graph editing and mutation workflows.
- `artifact_runtime/`
  - revision management, build packaging, deployment resolution, runtime policy, and run execution.
- published app services
  - builder, preview, runtime, publish, revision, auth shell, coding agent runtime, and sandbox backend orchestration.
- governance and platform services
  - credentials, model resolution, registry seeding, workload identity, token brokering, audit-adjacent flows, and orchestration policy services.

### Agent Domain

The agent subsystem is graph-driven.

Core responsibilities:
- compile declarative graph definitions into executable runtime plans
- validate node and edge contracts
- execute runs with streaming, persistence, and trace recording
- support multiple runtime adapters and execution modes
- provide node executors for logic, tools, artifacts, retrieval, orchestration, and interaction patterns

Core modules:
- `backend/app/agent/graph/`
  - compiler, runtime, executable wrapper, IR, schema, and node factory
- `backend/app/agent/execution/`
  - execution service, event emitter, durable checkpointer, field resolver, stream contract, and trace recorder
- `backend/app/agent/executors/`
  - node-level behavior for tool, rag, logic, artifact, orchestration, and related execution types
- `backend/app/agent/runtime/`
  - runtime adapter registry and runtime state abstractions

The current architecture is no longer just a simple chat workflow. It is a platform execution domain that supports:
- graph-based agent composition
- debug and production execution modes
- threaded runs
- quota-aware execution
- persisted traces and resumability
- integration with workload delegation and published-app contexts
- worker-owned detached generic execution for top-level background runs

### RAG Domain

The RAG subsystem is also graph-driven, but focused on ingestion and retrieval rather than reasoning.

Core responsibilities:
- compile ingestion and retrieval pipelines
- run operator graphs over uploaded or external data
- connect pipelines to knowledge stores
- manage provider abstractions for chunking, embedding, loading, crawling, and vector storage

Core modules:
- `backend/app/rag/pipeline/`
  - compiler, executor, operator executor, registry, and input storage
- `backend/app/rag/providers/`
  - loaders, chunkers, embeddings, crawler, and vector-store implementations
- `backend/app/rag/interfaces/`
  - contracts for providers and web crawler behavior
- `backend/app/rag/adapters/`
  - vector backend adapter boundary

The system model keeps a clean separation:
- RAG builds or queries knowledge representations
- agents consume retrieval outputs and orchestration tools

### Artifact Runtime

Artifacts are a first-class extension and execution surface.

Current runtime responsibilities include:
- artifact discovery and registry integration
- revision storage and source-tree packaging
- deployment resolution and dispatch to Cloudflare Workers-compatible runtimes
- backend-side tenant runtime policy enforcement
- shared execution for artifact test runs and live agent/tool/RAG artifact surfaces

Current runtime modes:
- `workers_for_platforms` for the intended per-revision production deployment shape
- `standard_worker_test` for temporary free-plan validation with one shared runtime Worker

Current queue policy is implemented through queue classes rather than a separate scheduler:
- `artifact_test`
- `artifact_prod_interactive`
- `artifact_prod_background`

This provides workload separation, but stronger fairness inside a queue is still an evolving concern.

Architecture-critical locations:
- `backend/app/services/artifact_runtime/`
- `backend/app/api/routers/artifacts.py`
- `backend/app/api/routers/artifact_runs.py`
- `runtime/cloudflare-artifacts/`

### Published Apps and Coding Runtime

Published apps form a major backend concern, not a thin addon.

Current responsibilities include:
- published app admin APIs
- public app routes and host runtime
- preview and draft runtime support
- sandbox backend selection and execution
- revision storage and publish flows
- coding-agent runtime, monitoring, streaming, and tool integration

This area is implemented primarily in:
- `backend/app/api/routers/published_apps_*`
- `backend/app/services/published_app_*`

### Persistence and Workers

The backend uses multiple persistence and runtime mechanisms:
- PostgreSQL
  - primary relational store for platform entities, runs, governance data, registry data, and operational metadata
- MongoDB
  - still present for Sefaria/text-oriented data paths
- Celery workers
  - background processing for longer-running jobs

Important worker modules:
- `backend/app/workers/celery_app.py`
- `backend/app/workers/tasks.py`
- `backend/app/workers/artifact_tasks.py`
- `backend/app/workers/job_manager.py`
- `backend/app/workers/livekit_worker.py`

Current generic-agent worker split:
- top-level generic background runs dispatch to the Celery `agent_runs` queue
- `agent_runs` remains the source of truth for execution ownership and lease metadata
- generic stream routes now attach to persisted run events instead of owning execution in the API process

## Cross-Cutting Concerns

### Security and Governance

Security is not isolated to one module. It is spread across:
- auth and internal auth routers
- RBAC and workload security routes
- `backend/app/core/` security, RBAC, scope, audit, and token modules
- workload identity, delegation, and token broker services
- published-app auth services and auth shell rendering

### Observability and Tracing

Execution observability is a core architectural feature.

Relevant mechanisms include:
- execution event streaming
- trace recording
- run logs routes
- published app coding traces and monitors
- pipeline execution transparency on the RAG side

### Local Development Bootstrap

`backend/main.py` currently contains significant startup/bootstrap behavior for local development, including environment loading and optional local infra/runtime bootstrapping. That file is both an app composition root and a local dev orchestration point.

## Architectural Summary

The backend should be understood as a multi-domain platform backend with five major execution surfaces:
- control-plane APIs
- agent runtime
- RAG pipeline runtime
- artifact runtime
- published-app runtime

The important architectural boundary is not “API vs database.” The real boundaries are:
- authoring and control plane
- compiled graph execution
- shared platform services
- isolated runtime execution surfaces
- governance and observability applied across all of them

## Contradictions Removed By This Doc

This document supersedes older simplified descriptions that frame the backend mainly as:
- a basic FastAPI app with a few classic routers
- a single advanced-RAG chat flow
- a narrower MongoDB-first data model

Those descriptions no longer match the current codebase.
