# Platform Current State

Last Updated: 2026-04-13

This document is the canonical high-level overview of the Talmudpedia platform. It is the best single entry point when someone needs to understand what the platform is, which domains it contains, and which technical concepts shape the system.

## Platform Definition

Talmudpedia is a multi-tenant AI platform for building, governing, and running AI systems across several related product surfaces.

At a platform level, it combines:
- agent authoring and execution
- RAG pipeline authoring and execution
- shared tool, model, credential, and artifact registries
- published app hosting and builder workflows
- embedded/public runtime surfaces
- platform-wide governance, tracing, and operations

The platform is not a single chatbot product. It is a control plane plus multiple execution planes that share the same core infrastructure.

## What The Platform Contains

The platform currently spans these major domains:

### 1. Agent Domain

The agent domain provides:
- graph-based agent builders
- draft-safe persistence of agent workflows
- graph analysis, validation, and compilation
- runtime execution across nodes such as LLMs, tools, retrieval, logic, human input, and artifacts
- threaded runs, streamed outputs, and persisted execution traces

Use this domain when the system needs reasoning, orchestration, tool usage, and multi-step execution.

See:
- `docs/design-docs/agent_execution_current.md`
- `docs/product-specs/agent_graph_spec.md`

### 2. RAG Domain

The RAG domain provides:
- ingestion pipelines
- retrieval pipelines
- operator-based graph authoring
- chunking, embedding, crawling, normalization, and search
- compile-time and run-time contracts for pipeline behavior

Use this domain when the system needs to turn raw data into retrievable knowledge or query that knowledge in a structured way.

See:
- `docs/product-specs/rag_pipeline_spec.md`

### 3. Knowledge Store Domain

Knowledge stores are the logical bridge between ingestion and runtime retrieval.

They define:
- where retrieval-ready knowledge lives
- which embedding/vector relationship is expected
- which retrieval policies and contracts consumers depend on

This domain matters because Agent and RAG stay separate as products, but they still meet through shared knowledge resources.

### 4. Tools Domain

The tools domain provides the runtime-facing catalog of callable capabilities.

It includes:
- manually managed tools
- built-in system tools
- MCP-backed tools
- artifact-backed tools
- pipeline-backed tools
- agent-backed tools

This gives the platform a single execution-facing tool model even when authoring happens from different product surfaces.

See:
- `docs/product-specs/tools_domain_spec.md`

### 5. Artifact Domain

Artifacts are the platform’s packaged extension/runtime unit.

They are used for:
- executable custom logic
- artifact-backed tools
- artifact-backed agent nodes
- artifact-backed RAG operators
- artifact admin and test-run flows

The backend acts as the artifact control plane, while isolated execution runs on a Workers-compatible substrate.

See:
- `docs/product-specs/artifacts_domain_spec.md`
- `docs/design-docs/artifact_execution_current.md`

### 6. Published Apps Domain

Published apps are the user-facing application/runtime layer built on top of shared platform capabilities.

This domain includes:
- app draft workspaces and previews
- revision storage and publishing
- hosted/public runtime routes
- admin management flows
- coding-agent-assisted app development flows

Published apps are not separate from the platform. They are one of its main runtime surfaces.

See:
- `docs/product-specs/published_apps_spec.md`
- `docs/design-docs/apps_builder_current.md`

### 7. Embedded Runtime Domain

The platform also supports embedded agent/app experiences through the public embed contract and SDK-based runtime access patterns.

This matters because the platform is designed to power both first-party hosted experiences and external customer-facing embeddings.

See:
- `docs/product-specs/embedded_agent_runtime_spec.md`

## Core Technical Concepts

The main technical concepts that define the platform are:

### Multi-Tenant Control Plane

The platform centrally manages:
- tenants and org boundaries
- models and provider bindings
- tools and visibility rules
- credentials and integrations
- runtime policies and permissions

This is the shared control layer behind every domain.

### Builder To Compiler To Runtime Flow

Several surfaces follow the same general lifecycle:
1. users author drafts visually
2. drafts are persisted even when incomplete
3. analysis/validation explains what is missing
4. compilation or materialization creates runnable state
5. runtime execution uses the compiled form with tracing and policy enforcement

This pattern appears in both Agent and RAG, and also influences published-app and artifact flows.

### Shared Resource Model

Models, tools, artifacts, credentials, and knowledge resources are shared platform objects, not page-local implementation details.

That lets multiple domains reuse the same resources while preserving tenant scope and governance rules.

### Multiple Execution Surfaces

The platform runs workloads through several surfaces, including:
- synchronous API calls
- streamed runs
- background workers
- isolated artifact runtimes
- published-app runtime hosts
- embedded/public runtimes

This is why the architecture is closer to an AI operating platform than a single API service.

### Governance As A First-Class System

Governance is built into the platform through:
- auth and internal auth
- RBAC and tenant scoping
- workload identity
- delegated execution policies
- audit and security enforcement

It is not an afterthought around the execution engine.

### Observability As Shared Infrastructure

The platform treats tracing and execution visibility as reusable infrastructure.

Key concepts include:
- run events
- trace recording
- execution logs
- usage and stats aggregation
- surface-aware visibility rules

This is especially important for debugging agent runs, pipeline execution, published-app preview behavior, and coding-agent flows.

## Runtime And Infrastructure Shape

At a high level, the current system is shaped as:
- API and websocket surfaces for control-plane and runtime operations
- service-layer orchestration for business logic and policy
- graph compilers and execution runtimes for Agent and RAG
- background workers for longer-running tasks
- isolated runtime substrates for artifact-style execution
- shared persistence and trace infrastructure across domains

Important current realities:
- PostgreSQL is the primary operational store
- MongoDB is still used for Sefaria/text-oriented paths
- Celery remains important for async/background work
- local bootstrapping is still concentrated in `backend/main.py`

## Short Positioning Summary

For CV or experience framing, the platform can be described as:

Talmudpedia is a multi-tenant AI platform that combines agent orchestration, RAG pipelines, shared tool and artifact infrastructure, published app hosting, embedded runtimes, and platform-wide governance/observability into one backend system.

## Related Canonical Docs

- `docs/design-docs/platform_architecture_layers.md`
- `docs/design-docs/backend_architecture_current.md`
- `docs/design-docs/agent_execution_current.md`
- `docs/design-docs/apps_builder_current.md`
- `docs/design-docs/artifact_execution_current.md`
- `docs/product-specs/agent_graph_spec.md`
- `docs/product-specs/rag_pipeline_spec.md`
- `docs/product-specs/tools_domain_spec.md`
- `docs/product-specs/artifacts_domain_spec.md`
- `docs/product-specs/published_apps_spec.md`
