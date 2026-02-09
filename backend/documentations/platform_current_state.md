# TalmudPedia: Platform Current State & Overview

Last Updated: 2026-02-09

TalmudPedia is a foundational **Enterprise AI Agent & RAG Platform** designed as a unified control plane for models, tools, data, and reasoning workflows. It is vendor-agnostic, modular, and enterprise-ready, supporting both API-based and self-hosted models. Data ingestion (RAG) and reasoning (Agents) are decoupled through the **Knowledge Store** bridge.

---

## 1. Core Architectural Pillars

The platform is organized into independent domains communicating through stable contracts:

| Domain | Responsibility |
| :--- | :--- |
| **Models** | Logical registry for Chat, Embedding, and Reranking; tenant overrides; dimension resolution. |
| **Tools** | Registry of callable capabilities: built-in, MCP, artifact-backed, custom (HTTP/function/RAG). |
| **RAG** | Ingestion and retrieval pipelines; DAG orchestration; Custom Python and Artifact operators. |
| **Knowledge Store** | Bridge abstraction: logical stores decouple pipelines and agents from physical vector DBs. |
| **Agent** | Reasoning and orchestration via LangGraph; CEL logic; HITL; streaming and tracing. |
| **Execution** | Shared kernel: jobs, traces, streaming, state; divergent observability (Debug vs Production). |
| **Governance** | Multi-tenancy, RBAC, audit; Postgres-backed identity (User, Tenant, OrgMembership). |

---

## 2. Current Implementation Status

### A. Agent Domain

- **Architecture**: Service Layer (`AgentService`); single execution engine (`AgentExecutorService`) for Playground and Production.
- **Engine**: `AgentCompiler` turns declarative GraphSpec v1 JSON into executable LangGraph workflows.
- **Observability**: **Unified Engine, Divergent Observability** (ADR 001). `StreamAdapter` filters events by `ExecutionMode`: Debug = full firehose (inputs, tool calls, thoughts, tokens); Production = clean stream (final tokens and client-safe events only). Auth-scoped: public tokens cannot request Debug.
- **Features**: Cyclic workflows, CEL (If/Else, While), User Approval (HITL), Transform/Set State, artifact field mapping, versioning, `AgentRun`/`AgentTrace` persistence. Tool execution: HTTP, artifact, MCP, and function tools supported. Tool invocation in agent nodes supports structured tool calls with JSON fallback (native LLM tool calling is still a roadmap item).
- **UI**: Visual Builder (xyflow, BaseNode, ConfigPanel) and Agent Playground (streaming, execution sidebar, same chat components as production). Builder Execute mode now overlays runtime topology (orchestration decisions + child runs) from SSE with periodic `/agents/runs/{run_id}/tree` reconciliation; overlay is ephemeral per run and never persisted into draft `graph_definition`. Memory: short-term active; long-term/vector in development.
- **Platform Architect v2**: Multi-agent orchestrator seeded with sub-agents (Catalog, Planner, Builder, Coder, Tester). The seed now uses a GraphSpec v2 orchestration graph (`spawn_run`, `spawn_group`, `join`, `router`, `judge`, `replan`, `cancel_subtree`) and auto-seeds orchestrator policy/target allowlist rows for those sub-agents. Platform SDK tool supports draft asset creation and multi-case tests; secure internal API flows use delegated workload tokens with scope enforcement (legacy service/API-key fallback removed on migrated secure paths).

### B. RAG Domain

- **Status**: Phase 3 complete. Refactored to Service Layer; Knowledge Store abstraction fully implemented.
- **Pipelines**: `INGESTION` and `RETRIEVAL` modes; visual DAG builder; type-safe connections via DataType/OperatorRegistry.
- **Operators**: Sources (file, S3, web); normalization (OCR, PII, HTML); enrichment (metadata, NER, summarization); chunking (token, recursive, semantic, hierarchical); embedding via Model Registry; storage via `knowledge_store_sink`; retrieval via `query_input`/`retrieval_result` and `RetrievalService`. Custom Python operators (restricted namespace, tenant-scoped) and Artifact operators (filesystem, `ArtifactExecutor`).
- **Execution**: Background DAG execution, step-level tracking (`pipeline_step_executions`), live progress in builder, schema-driven run forms, namespaced runtime payloads, backend validation, file upload lifecycle (tenant-isolated, TTL cleanup). Centralized result capture in `job.output`.
- **Cascading lifecycle**: Ownership FKs with CASCADE; graceful user links (SET NULL).

### C. Knowledge Store

- Logical “stores” define embedding model, retrieval policy, and vector backend. Pipelines ingest into stores; agents and retrieval pipelines query via `RetrievalService` (semantic, hybrid, keyword). Metadata-aware metrics (document_count, chunk_count). Credentials can reference tenant-scoped Integration Credentials (Settings).

### D. Infrastructure & Backend

- **Stack**: FastAPI (async), PostgreSQL (metadata, pgvector), MongoDB (Sefaria), Redis/Celery for workers.
- **Auth**: Hybrid (User + Tenant + OrgMembership); JWT with tenant_id/org_role; admin routes tenant-scoped; Postgres for auth/admin data.
- **Voice**: WebSocket entry (`voice_ws.py`), provider registry, Gemini session; tool calling to RetrievalService; persistence in Chats/Messages.
- **Settings**: Tenant-centric settings hub with tenant profile (name/slug/status), tenant default pointers (chat model, embedding model, retrieval policy in `Tenant.settings`), and tenant-scoped Integration Credentials (LLM providers, vector stores, artifact secrets, custom). Credential values are write-only; model bindings and knowledge stores reference credentials by ref.

### E. Admin & Observability

- **Stats API**: `GET /api/v1/admin/stats/summary` with sections `overview`, `rag`, `agents`, `resources`; date range and presets; metrics for users, messages, tokens, RAG jobs, agent runs, tools/models/artifacts. Frontend: `/admin/stats` with tabs and drilldowns; types and API in `src/services`.
- **Execution transparency**: RAG pipeline live tracking on canvas; step input/output inspection; streaming steps; Pipeline Builder syncs execution state with React Flow.

---

## 3. Key Implemented Features

| Feature | Description |
| :--- | :--- |
| **DAG orchestration** | RAG and Agents use declarative graphs (GraphSpec v1 baseline, plus GraphSpec v2 orchestration node surface for agents). |
| **Vendor agnostic** | Models and vector stores behind Model Registry and Knowledge Store. |
| **Service layer** | Clear separation: AgentService, RetrievalService, pipeline executor, etc. |
| **Custom code** | Custom Python operators (DB) and Artifact operators (filesystem) in restricted environments. |
| **Traceability** | Agent runs/traces; pipeline step executions; event-driven streaming (Debug/Production). |
| **Dynamic run forms** | Operator-aware pipeline input UI; file upload; retrieval query schema. |
| **Triple extension** | Built-in, Custom Python, Artifacts. |
| **StreamAdapter** | Single execution path; observability differs by mode and auth. |

---

## 4. Technology Stack

- **Backend**: Python 3.11+, FastAPI, LangGraph, SQLAlchemy (async), CEL.
- **Frontend**: TypeScript, Next.js, Shadcn/UI, xyflow (React Flow).
- **Data**: PostgreSQL (Alembic, pgvector), MongoDB (Sefaria), Redis.
- **Orchestration**: Celery, BackgroundTasks.
- **SDK**: Dynamic Python SDK; schema-driven discovery; Pipeline/Agent builders; ArtifactBuilder for SaaS custom nodes.

---

## 5. Immediate Roadmap & Known Gaps

- **Agent SOTA alignment**: Native LLM tool calling, MCP execution, RAG as callable tool, durable checkpointing, memory_config/execution_constraints enforcement, tool permissions (see `summary/agent_sota_architecture_gap_overview.md`).
- **RAG**: Multi-store retrieval with score normalization; advanced metadata filtering UI; real-time metrics per node.
- **Tools**: MCP and function execution now implemented; expand coverage and observability as needed.
- **Platform Architect**: v2 multi-agent Architect (draft-only, test-first) is implemented; legacy linear flow remains as a fallback until v2 stabilizes.
- **Artifact CLI**: Scaffolding for new operator artifacts.
- **Stats**: Performance metrics (e.g. token/latency per node) and deeper drilldowns.
