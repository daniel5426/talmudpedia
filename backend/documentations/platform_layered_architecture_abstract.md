# Enterprise RAG & Agent Platform — Layered Architecture (Mental Model)

## Purpose
This document defines the **abstract mental architecture** of the Enterprise RAG & Agent Platform.

It intentionally avoids UI, frontend, or implementation details. The focus is on **conceptual layers, responsibilities, and boundaries** that guide system design, code generation, and long-term evolution.

This document is a **foundational reference** for humans and AI code agents.

---

## Core Design Principle

The platform is structured as **horizontal architectural layers**, each answering a distinct question:
- What problem does this layer solve?
- What concepts exist in this layer?
- What is explicitly out of scope for this layer?

Cross-cutting concerns (security, execution, observability) apply uniformly across all layers.

---

## Global Platform Layer (Foundation)

### Core Question
> Who is using the platform, in what context, and under which constraints?

### Responsibilities
- Tenant and organization context
- Environment separation (e.g. dev / prod)
- Identity and access boundaries
- Global configuration and policy anchoring

### Key Concepts
- Tenant
- Organization / Organizational Unit
- User / Service Identity
- Environment

### Non-Responsibilities
- No data processing
- No reasoning logic
- No workflow definition

---

## Layer 1 — RAG Layer (Data → Knowledge)

### Core Question
> How does raw data become structured, retrievable knowledge?

### Mental Model
- Pipelines
- Indexes
- Retrievers
- Ingestion Jobs

### Responsibilities
- Data ingestion
- Data transformation and chunking
- Embedding generation
- Storage into retrieval systems
- Definition of retrieval strategies

### Outputs
- Versioned knowledge indexes
- Retrieval contracts usable by downstream consumers

### Key Rule
The RAG layer **does not perform reasoning** and **has no awareness of agents**.

---

## Layer 2 — Agent Layer (Reasoning & Action)

### Core Question
> How does the system reason, decide, and act using available knowledge and tools?

### Mental Model
- Agents
- Reasoning flows
- Prompts
- Tools

### Responsibilities
- Orchestration of reasoning steps
- Context assembly
- Invocation of language models
- Controlled use of tools
- Consumption of RAG retrieval outputs

### Outputs
- Agent decisions
- Generated responses or actions

### Key Rule
Agents **consume knowledge** but never define or mutate it.

---

## Layer 3 — Execution Layer (Runtime)

### Core Question
> How are workflows executed reliably and observably?

### Responsibilities
- Scheduling and dispatch
- Runtime isolation
- Retries and failure handling
- Streaming and state transitions
- Deterministic re-execution

### Used By
- RAG pipelines
- Agent executions
- Evaluation runs

### Key Concepts
- Executable artifacts
- Runs
- Execution state

---

## Layer 4 — Resource Layer (Shared Assets)

### Core Question
> What reusable capabilities are available to workflows?

### Mental Model
- Providers
- Connections
- Tools
- Models

### Responsibilities
- Central definition of shared resources
- Versioning and configuration
- Secure access and isolation

### Examples
- Language models
- Embedding models
- Vector stores
- External system connectors

---

## Layer 5 — Governance Layer (Control & Trust)

### Core Question
> Who is allowed to do what, and how is it enforced and audited?

### Responsibilities
- Authorization (RBAC / ABAC)
- Policy enforcement
- Audit logging
- Compliance guarantees

### Key Concepts
- Roles
- Permissions
- Policies
- Audit events

---

## Layer 6 — Observability Layer (Behavior)

### Core Question
> What happened, why, and with what impact?

### Responsibilities
- Execution tracing
- Logging
- Metrics collection
- Cost attribution

### Scope
- RAG executions
- Agent runs
- System-level behavior

---

## Builder Abstraction Rule

Only **two architectural constructs define workflows**:

1. **RAG Pipelines** — data transformation graphs
2. **Agent Flows** — reasoning and action graphs

Everything else exists to **support, execute, govern, or observe** these workflows.

---

## Shared DAG Principle

- RAG pipelines and Agent flows are both DAG-based
- They share:
  - Validation logic
  - Compilation concepts
- They differ in:
  - Node semantics
  - Execution behavior
  - Output artifacts

---

## Unified Mental Model

- RAG builds knowledge
- Agents use knowledge
- Execution runs both
- Governance constrains all
- Observability explains behavior

---

## Explicit Non-Goals (for this document)

- UI layout or navigation
- Feature prioritization
- Technology or framework choices
- Performance optimizations

These belong in separate specifications.

