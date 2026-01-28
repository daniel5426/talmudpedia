# TalmudPedia: Platform Current State & Overview

TalmudPedia is a foundational **Enterprise AI Agent & RAG Platform** designed as a unified control plane for models, tools, data, and reasoning workflows. It is architected to be vendor-agnostic, modular, and enterprise-ready, supporting both API-based and self-hosted models.

## 1. Core Architectural Pillars
The platform is organized into independent, root-level domains that communicate through stable contracts:
*   **Models Domain**: A logical registry for AI capabilities (Chat, Embedding, Rerankers).
*   **Tools Domain**: A registry for callable platform capabilities (APIs, internal services).
*   **RAG Domain**: Workflows for knowledge ingestion and retrieval.
*   **Agent Domain**: Reasoning and orchestration workflows using directed graphs.
*   **Execution Domain**: The shared kernel for running jobs, traces, and runtime resolution.
*   **Governance Domain**: Multi-tenancy, RBAC, and audit logging.

---

## 2. Current Implementation Status

### **A. Agent Domain (Reasoning)**
*   **Architecture**: Fully refactored to a **Service Layer pattern** (`AgentService`).
*   **Engine**: Uses a custom `AgentCompiler` that transforms declarative JSON graphs into executable **LangGraph** workflows.
*   **Status**: 
    *   Backend logic for CRUD, validation, and publishing is complete.
    *   Visual Builder and Agent Playground are the primary interfaces for creation and testing.
    *   Agents reference models and tools via logical IDs, delegating runtime resolution to the execution layer.

### **B. RAG Domain (Knowledge)**
*   **Architecture**: A flexible, graph-based orchestration engine for data ingestion and transformation.
*   **Visual Builder**: A drag-and-drop interface (built on `xyflow/react`) for constructing ingestion pipelines.
*   **Operator Ecosystem**: 
    *   **Sources**: File loaders, S3, Web Crawling.
    *   **Processing**: OCR, PII redaction, Summarization, and various Chunking strategies.
    *   **Storage**: Connectors for PGVector (PostgreSQL), Pinecone, and Qdrant.
*   **Custom Operators**: Users can write and execute **Custom Python Operators** in a restricted, tenant-isolated environment.
*   **Status**: Phase 2 is complete, including background execution of DAGs and live progress tracking.

### **C. Pipeline Input & Dynamic UI**
*   **Dynamic Forms**: Replaced generic JSON inputs with an **Operator-Aware Form System**. It automatically discovers required parameters from a pipeline's "source" nodes and generates a type-safe UI.
*   **File Handling**: Integrated file upload support that maps local files to server-side paths for pipeline ingestion.

### **D. Infrastructure & Backend**
*   **Framework**: FastAPI (Async Python).
*   **Databases**: 
    *   **PostgreSQL**: Primary store for metadata, configurations, and vector embeddings (via `pgvector`).
    *   **MongoDB**: Dedicated to storing Sefaria religious texts.
*   **Worker Layer**: Celery/BackgroundTasks for handling long-running ingestion and execution jobs.
*   **Voice Integration**: Support for real-time voice interaction via WebSockets and LiveKit.

---

## 3. Key Implemented Features
| Feature | Description |
| :--- | :--- |
| **DAG Orchestration** | Both RAG and Agents use declarative Directed Acyclic Graphs. |
| **Vendor Agnostic** | Models and Vector Stores are abstracted behind interfaces. |
| **Service Layer** | Strong separation between API routers and business logic. |
| **Custom Code** | Safe execution of user-defined Python logic within pipelines. |
| **Traceability** | All execution paths are inspectable with input/output logging. |

## 4. Immediate Roadmap
*   Refactoring the RAG Domain to the Service Layer pattern (Phase 3).
*   Automating model-driven dimensioning for vector stores.
*   Implementing advanced metadata filtering and reranking operators.
*   Expanding the Agent Playground's interactive execution and tracing capabilities.
