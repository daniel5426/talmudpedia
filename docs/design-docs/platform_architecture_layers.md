# Platform Architecture Layers

Last Updated: 2026-03-10

This document defines the conceptual layered architecture of the Talmudpedia platform. It is a mental model document, not a file-by-file implementation map.

## Purpose

Use this document to answer:
- what the major architectural layers are
- what each layer is responsible for
- what should remain outside each layer

Use `docs/design-docs/backend_architecture_current.md` when you need the current backend implementation picture.

## Layer 0: Platform Foundation

### Core Question

Who is operating within the platform, under which identity, scope, and environment constraints?

### Responsibilities

- tenant and organization boundaries
- identity and user/service principal context
- environment and deployment context
- top-level policy anchoring

### Non-Responsibilities

- reasoning logic
- data transformation workflows
- workflow execution semantics

## Layer 1: Shared Resources

### Core Question

What reusable capabilities exist for other layers to consume?

### Responsibilities

- model registry and model configuration
- tool catalogs and tool contracts
- artifact registry and extension surfaces
- provider and integration bindings

### Examples

- language models
- embedding models
- vector backends
- external system connectors
- built-in and custom tools

## Layer 2: RAG

### Core Question

How does raw data become retrievable knowledge?

### Responsibilities

- ingestion pipelines
- transformation and chunking
- embedding generation
- storage into retrieval systems
- retrieval pipeline behavior and contracts

### Key Rule

The RAG layer should not contain reasoning policy. It prepares or retrieves knowledge.

## Layer 3: Agent

### Core Question

How does the system reason, decide, and act with available knowledge and tools?

### Responsibilities

- reasoning flow definition
- context assembly
- model invocation
- tool usage and orchestration
- retrieval consumption

### Key Rule

Agents consume knowledge and capabilities. They should not redefine the storage semantics of the RAG layer.

## Layer 4: Execution

### Core Question

How do authored workflows run reliably, observably, and with the correct runtime boundaries?

### Responsibilities

- graph compilation handoff into runtime execution
- streaming and state transitions
- background and isolated execution
- retries, checkpoints, and resumability mechanisms
- run state and execution metadata

### Used By

- agent execution
- RAG pipeline execution
- published app runtime flows
- artifact-backed execution surfaces

## Layer 5: Governance

### Core Question

Who is allowed to do what, and how is that enforced?

### Responsibilities

- authorization
- policy enforcement
- workload delegation
- auditability
- tenant- and org-scoped control

## Layer 6: Observability

### Core Question

What happened, why did it happen, and how can it be inspected?

### Responsibilities

- trace recording
- logs and event streams
- metrics and usage accounting
- runtime visibility by surface and audience

## Cross-Layer Rules

- governance applies across every execution surface
- observability must be reusable across runtimes rather than embedded as ad-hoc local logging
- execution is a shared platform capability, not something owned only by agents
- resources are shared inputs, not substitutes for workflow definitions

## Builder Abstraction Rule

The main authored workflow types are:
1. RAG pipelines
2. agent flows

Published app and artifact runtimes are additional execution surfaces built around those shared capabilities, not replacements for the core workflow abstractions.
