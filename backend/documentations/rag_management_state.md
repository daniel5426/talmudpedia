# RAG Management Current State

## Overview
The RAG (Retrieval-Augmented Generation) subsystem is a flexible, graph-based pipeline orchestration engine designed to manage the full lifecycle of data ingestion, transformation, and storage for semantic search. It has evolved from a simple linear flow to a highly customizable, contract-driven architecture.

## Core Domain Features

### 1. Visual Pipeline Builder
- **Drag-and-Drop Interface**: Built on `@xyflow/react` for intuitive construction of ingestion and retrieval flows.
- **Node-Based Architecture**: Each step in the pipeline is an independent operator with specific inputs/outputs regulated by the `OperatorRegistry`.
- **Granular Operator Ecosystem**:
    - **Source**: Loaders for local files, AWS S3, and Web Crawling.
    - **Normalization**: OCR, HTML cleaning, and PII redaction.
    - **Enrichment**: Metadata extraction (dates, titles, authors), Entity Recognition (NLP), and Summarization (LLM-based).
    - **Chunking**: Token-based, Recursive Character, Semantic (similarity-based), and Hierarchical strategies.
    - **Embedding**: Unified `model_embedder` resolving to any model in the Model Registry.
    - **Storage**: Vector store connectors (Pinecone, PostgreSQL/PGVector, Qdrant).
    - **Custom**: User-defined Python operators for "escape hatch" logic.
- **Type-Safe Connections**: Robust real-time validation based on the `DataType` enum system (e.g., `RAW_DOCUMENTS` -> `CHUNKS` connection is validated against the registry's compatibility matrix).

### 2. Custom Operator System (NEW)
- **Python Integration**: Users can define custom operators by writing Python code directly in the platform.
- **Restricted Execution**: Custom code runs in a protected namespace with safe builtins and curated standard libraries (`re`, `json`, `datetime`).
- **Standardized Contract**: Custom operators define their own input/output types and configuration schemas, making them first-class citizens in the Node Catalog.
- **Tenant Isolation**: Custom operators are scoped to specific tenants and persisted in the `CustomOperator` database model.

### 3. Unified Model Integration
- **Model Registry Alignment**: Embedding and Completion models are managed centrally.
- **Capability-Based Selection**: The builder dynamically filters available models by `embedding` or `completion` capabilities for specific nodes (e.g., Summarizer nodes fetch completion models).
- **Dimension Resolution**: Automatically extracts embedding dimensions from model metadata, resolving them at compile-time to ensure vector store compatibility.

### 4. Direct Execution Engine (NEW)
- **Topological DAG Execution**: A custom `PipelineExecutor` service can run compiled pipelines step-by-step in accurate order.
- **One-Click Testing**: The "Run Pipeline" feature allows administrators to trigger a pipeline execution with custom JSON input directly from the builder UI.
- **Background Orchestration**: Pipeline jobs are triggered via `BackgroundTasks` to ensure high availability and responsiveness of the main API.
- **Immutable Compilation**: Every save/run creates a versioned `ExecutablePipeline` snapshot with locked operator versions and configuration state.

## System Architecture

### Backend Stack
- **API**: FastAPI with PostgreSQL storage using SQLAlchemy.
- **Registry**: `OperatorRegistry` maintains the catalog of built-in and tenant-specific custom operators.
- **Executor**: `PipelineExecutor` and `ExecutorRegistry` manage the instantiation and running of operator logic.
- **Security**: Restricted `eval`/`exec` environment for custom code and RBAC for all management endpoints.

### Frontend Stack
- **Interface**: Next.js with Shadcn/UI and a premium, minimalist design system.
- **Canvas**: React Flow (XYFlow) for the visual graph editor with muted, pastel category colors.
- **Logic**: Custom hooks for canvas state management and service-oriented integration with the RAG Admin API.

## Implementation State (Phase 2 Completed)

| Feature | Status | Details |
| :--- | :--- | :--- |
| Decomposed Operator Categories | ✅ Completed | Normalization, Enrichment, and Chunking are split for cleaner pipelines. |
| Custom Python Operators | ✅ Completed | Fully integrated editor, storage, and execution engine. |
| Background Pipeline Executor | ✅ Completed | Asynchronous execution of compiled DAGs. |
| Run/Test UI | ✅ Completed | Modal for triggering pipeline runs with custom parameters. |
| Live Execution Tracking | ✅ Completed | Step-by-step progress visualization with input/output inspection. |
| Connection Validation | ✅ Completed | Comprehensive logic supporting all new intermediate data types. |
| Multi-tenancy | ✅ Active | Tenant-specific pipeline namespace and custom operator scoping. |
| PGVector Storage | ✅ Active | Integrated with the main system database via pgvector extension. |

## Next Implementation Priorities
1. **Model-Driven Dimensioning**: Fully automate the passing of resolved dimensions from embedding models to vector stores during execution.
2. **Reranker Implementation**: Implement the `reranking` operator logic in the executor.
3. **Metadata Filtering Engine**: Advanced UI for mapping extracted metadata to vector store fields.
4. **JSON Schema Editor**: Integrate a structured JSON editor for custom operator `config_schema` definitions.
5. **Real-time Metrics**: Visualizing execution time and token usage per operator node.

