# Platform Current State

Last Updated: 2026-03-10

This document is the canonical current-state overview for the Talmudpedia platform. It summarizes the live platform at a domain level and points to more focused design docs for detail.

## Platform Definition

Talmudpedia is a multi-tenant AI platform that combines:
- control-plane APIs for models, tools, governance, and configuration
- graph-based RAG authoring and execution
- graph-based agent authoring and execution
- published app runtimes and builder workflows
- artifact-based extension and execution infrastructure

The platform is not just an agent app and not just a RAG backend. It is a backend platform with multiple execution surfaces sharing common governance, tracing, and runtime services.

## Core Domains

### Agents

The agent domain supports:
- graph-based authoring and validation
- compiled execution through runtime adapters
- threaded runs and persisted traces
- heterogeneous node execution, including logic, tools, retrieval, artifacts, and orchestration
- execution modes and surface-specific visibility rules

See:
- `docs/design-docs/backend_architecture_current.md`
- `docs/design-docs/agent_execution_current.md`

### RAG

The RAG domain supports:
- ingestion and retrieval pipeline compilation
- graph execution with operator registries
- file and external-source inputs
- chunking, embedding, crawling, and vector-store providers
- logical knowledge stores as the contract between ingestion and retrieval consumers

The core distinction remains:
- RAG builds or queries knowledge representations
- agents consume retrieval outputs during reasoning or tool execution

### Knowledge Stores

Knowledge stores remain the logical bridge between data ingestion and reasoning/runtime consumers.

They define:
- retrieval policy
- vector backend relationship
- embedding expectations
- the logical endpoint that both pipelines and agents can target

### Tools and Shared Resources

Shared platform resources include:
- model registry and model resolution
- tool registry and built-in tool catalog
- integration credentials
- artifact registry and artifact-backed execution

These resources are consumed across both the agent and RAG sides of the system.

Current artifact runtime usage now spans:
- artifact admin/test-run flows
- tenant artifact nodes in agents
- artifact-backed tools
- artifact-backed RAG operators

### Published Apps

Published apps are a major runtime domain.

The current backend includes support for:
- admin-side app management
- public and hosted app runtime routes
- builder preview and draft runtime flows
- coding-agent runtimes
- revision storage and publishing pipelines
- sandbox backend selection and execution

### Governance and Security

Governance spans:
- auth and internal auth
- RBAC and org/tenant boundaries
- workload identity and delegated execution
- token brokering and security policy enforcement
- audit and scoped runtime behavior

This is a platform-wide concern, not an add-on module.

### Observability and Operations

The platform currently includes:
- execution event streaming
- trace recording
- run and log inspection surfaces
- stats and usage aggregation
- worker-managed background execution

The system relies on observability as a first-class control-plane feature, especially for agent runs, RAG pipeline execution, and published-app coding flows.

## Current Architectural Shape

The backend currently operates as a set of cooperating domains:
- API and websocket surfaces expose platform and runtime operations
- services coordinate business logic and policy
- graph compilers and runtimes handle agent and RAG execution
- workers and runtime-specific execution surfaces handle asynchronous or isolated workloads
- shared governance and observability infrastructure apply across all runtime surfaces

## Important Current Realities

- PostgreSQL is the primary operational store for platform entities and runtime metadata.
- MongoDB is still present for Sefaria/text-oriented paths.
- Celery and background execution remain important for longer-running jobs.
- local development bootstrapping is still concentrated in `backend/main.py`.
- the platform already contains multiple runtime surfaces beyond the basic API request/response cycle.

## Known Gaps and Ongoing Areas

Some areas are clearly still evolving:
- deeper agent memory and durable execution capabilities
- further tool-governance hardening
- richer retrieval and multi-store capabilities
- stronger artifact queue fairness and scheduling controls beyond the current queue-class split
- continued cleanup of architecture documentation drift

These gaps do not change the current architectural picture; they only indicate active evolution.
