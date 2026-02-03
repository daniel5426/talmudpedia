# Backend State Overview

This document provides a comprehensive overview of the current state of the backend architecture, reflecting the Phase 3 refactoring and the introduction of advanced Agent and RAG capabilities.

## Architecture Highlights
- **Framework**: FastAPI (Async Python)
- **Database**: PostgreSQL (Primary) + MongoDB (Sefaria Content)
- **Agent Engine**: Custom `AgentCompiler` + LangGraph for declarative execution with CEL logic.
- **RAG Subsystem**: Knowledge Store abstraction layer decoupling ingestion from retrieval.
- **Execution**: Service Layer pattern across all domains (`AgentService`, `RetrievalService`, etc.).
- **Extensions**: Triple-tier extension model (Built-in, Custom Python, Artifacts).

---

## File Tree & Descriptions

### `backend/app`
*Core application logic*

#### `backend/app/agent`
*Agent Domain: Definitions, Logic, and Execution*
- `config.py`: Configuration schemas for agents.
- `cel_engine.py`: Common Expression Language (CEL) evaluation engine for branching and transforms.
- **`graph/`**:
    - `compiler.py`: Compiles visual DAGs into executable LangGraph states.
    - `executable.py`: Runtime wrapper for agent execution.
    - `schema.py`: Pydantic models defining the graph protocol.
- **`executors/`**: (NEW) Specific implementations for node-level logic.
    - `rag.py`: Knowledge Store search integration.
    - `logic.py`: If/Else and While loop handling.
    - `tool.py`: External tool invocation.
- **`execution/`**: (NEW)
    - `service.py`: Manages agent run lifecycle and persistence.
    - `emitter.py`: Event-driven streaming of tokens and internal reasoning.

#### `backend/app/rag`
*RAG Subsystem: Ingestion and Pipeline Orchestration*
- `factory.py`: Factory for creating loaders, chunkers, and storages.
- **`pipeline/`**:
    - `compiler.py`: Compiles RAG pipelines into executable DAGs.
    - `operator_executor.py`: (NEW) Comprehensive registry of operator logic (OCR, PII, Semantic Chunking). Includes `ArtifactExecutor`.
    - `input_storage.py`: (NEW) Tenant-isolated file lifecycle management for pipeline uploads.
- **`providers/`**: Implementations for Loading, Chunking, and Embedding.
- **`adapters/`**: Bridging logic for different vector backends.

#### `backend/app/api`
*Interface Layer*
- **`routers/`**:
    - `agents.py`: Endpoints for Agent management and execution.
    - `knowledge_stores.py`: (NEW) CRUD and configuration for logical Knowledge Stores.
    - `rag_pipelines.py`: Management of ingestion and retrieval pipelines.
    - `rag_ws.py`: (NEW) WebSockets for real-time pipeline status updates.
    - `models.py`: Model Registry and Provider configuration.
    - `voice_ws.py`: Real-time voice interaction via LiveKit.

#### `backend/app/services`
*Core Business Logic*
- `agent_service.py`: Orchestrates agent creation, versioning, and execution.
- `retrieval_service.py`: (NEW) Unified interface for searching across Knowledge Stores.
- `artifact_registry.py`: (NEW) Discovers and indexes filesystem-based code extensions.
- `model_resolver.py`: Resolves logical model IDs to provider-specific configurations.
- `registry_seeding.py`: Automated seeding of default models and operators.

#### `backend/app/db`
*Persistence Layer*
- **`postgres/`**:
    - `models/`: SQLAlchemy models for all domains (Tenants, Agents, Pipelines, KnowledgeStores).
    - `seeds/`: Initial data for the platform.
- **`mongo/`**: (Implicitly used) Storage for Sefaria religious texts.

#### `backend/app/workers`
*Background Processing*
- `celery_app.py`: Task worker configuration.
- `tasks.py`: Async processing for ingestion jobs and long-running agent tasks.
- `job_manager.py`: Status tracking for background jobs.

---

## Technical Specifications

### 💡 Agent Execution (LangGraph + CEL)
Agents are compiled into LangGraph workflows. Logic nodes (If/Else, While) use the `cel_engine.py` to evaluate user-defined expressions safely. State is persisted in `AgentRun` and checkpoints are handled by the execution layer.

### 📚 Knowledge Stores
Bridging RAG and Agents. A Knowledge Store defines the **What** (Embedding Model, Retrieval Policy) and the **Where** (Vector DB provider). Pipelines ingest *into* stores; Agents retrieve *from* them.

### 🧩 Operator Manifests (Artifacts)
New operators can be added by creating a directory in `backend/artifacts` with an `artifact.yaml` and a `handler.py`. The `ArtifactRegistry` automatically discovers these at startup.

---
*Last Updated: February 2026*
