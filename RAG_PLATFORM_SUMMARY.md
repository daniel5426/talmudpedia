# RAG Platform Architecture Summary

This document summarizes the transition from a specialized RAG script to a modular, enterprise-grade AI Agent Platform.

## 🚀 Current Status: Phases 1-5 Completed

We have successfully implemented the core infrastructure, multi-provider support, background job processing, an enterprise-grade multi-tenancy/RBAC system, and a visual pipeline orchestrator.

### 1. Modular Architecture (Phase 1)
- **Abstract Interfaces:** Established `ABC` (Abstract Base Class) patterns for all RAG components:
  - `EmbeddingProvider`: Unified interface for vector generation.
  - `VectorStoreProvider`: Unified interface for storage and retrieval.
  - `DocumentLoader`: Standardized document ingestion.
  - `ChunkerStrategy`: Customizable text splitting logic.
- **Factory Pattern:** Implemented `RAGFactory` for dependency injection, allowing runtime switching of providers.
- **Orchestration:** Created `RAGOrchestrator` to manage the pipeline flow from raw files to embedded vectors.

### 2. Multi-Provider Support (Phase 2)
- **Embedding Providers:**
  - `Gemini`: Existing Google-based embeddings.
  - `OpenAI`: Support for `text-embedding-3-small/large`.
  - `HuggingFace`: Local inference using `sentence-transformers`.
- **Vector Stores:**
  - `Pinecone`: Serverless cloud vector database.
  - `Pgvector`: PostgreSQL-based vector storage (Enterprise/On-prem).
  - `Qdrant`: Open-source high-performance vector DB.
- **Document Loaders:**
  - `LocalFileLoader`: Support for `.txt`, `.md`, `.json`, `.csv`, `.pdf`.
  - `S3Loader`: Direct ingestion from AWS S3 buckets.
- **Chunking:**
  - `TokenBased`: Precise token-limit chunking (Tiktoken).
  - `Recursive`: Context-aware splitting (LangChain style).

### 3. Background Jobs & Real-time Monitoring (Phase 3)
- **Celery & Redis:** Integrated background workers for large-scale ingestion tasks.
- **Job Management:** A Redis-backed `JobManager` tracks progress across multiple stages (Loading -> Chunking -> Embedding -> Upserting).
- **WebSockets:** Real-time progress updates sent to the frontend via `rag_ws.py`.
- **Admin Dashboard:**
  - **Live Progress:** Visual progress bars and stage tracking for active jobs.
  - **Index Management:** CRUD operations for vector indices across different providers.
  - **Chunk Preview:** A sandbox to test chunking settings before committing to an index.
  - **System Stats:** Overview of total chunks, active jobs, and available providers.

### 4. Multi-Tenancy & RBAC (Phase 4)
- **Tenant Isolation:** First-class `Tenant` entity providing a hard security boundary for all data.
- **Unified Hierarchy:** `OrgUnit` system (Organization > Department > Team) with arbitrary depth support.
- **Atomic RBAC:** Permissions structured as `{ resource_type, action }` for fine-grained control.
- **Cascading Authorization:** Bottom-up traversal logic allows permissions to inherit from resource up to tenant.
- **Compliance Audit Logs:** Complete trail including `actor_type` (user/service/agent), state changes (before/after), and result tracking.
- **Security Dashboard:**
  - **Organization Tree:** Visual management of hierarchical units and members.
  - **Role Editor:** UI to define custom permission matrices.
  - **Audit Center:** High-performance log viewer with filtering and diff views.

### 5. Visual Pipeline Builder (Phase 5)
- **Visual Editor:** Drag-and-drop UI using `React Flow` for RAG component orchestration.
- **Operator Registry:** Contract-based operator definitions (Sources, Transformers, Embedders, Stores).
- **Immutable Compilation:** UI graphs are compiled into versioned, immutable `ExecutablePipeline` DAGs.
- **Semantic Validation:** Automatic checks for connectivity, config completeness, and type compatibility (e.g., dimension matching).
- **First-class Jobs:** Decoupled pipeline definition from execution via a dedicated `PipelineJob` entity.

---

## 🛠 Technical Stack Added

- **Backend:** `celery`, `redis`, `asyncpg` (Postgres), `qdrant-client`, `openai`, `aiofiles`, `pypdf`, `tiktoken`.
- **Frontend:** `@xyflow/react` (React Flow), `lucide-react`, `radix-ui`, `nanoid`, WebSockets, `TenantContext`.
- **Infrastructure:** `run_celery.py` entry point, updated `requirements.txt`.

---

## 📅 Remaining Roadmap

### Phase 6: Advanced RAG Features (Next Step)
- **Hybrid Search Configuration:** UI to tune weights between Keyword (Lexical) and Vector (Semantic) search.
- **Knowledge Graph Integration:** Connecting chunks with entities for better reasoning.
- **Evaluations (Ragas):** Visualizing faithfulness, relevance, and precision metrics.

---

## 🏃 How to Run the New Components

### 1. Start Infrastructure
```bash
redis-server
```

### 2. Run Migration (First time only)
```bash
cd backend
python scripts/migrate_rbac.py
```

### 3. Start Celery Workers
```bash
cd backend
python run_celery.py worker -l info -Q default,ingestion,embedding
```

### 4. Start Backend & Frontend
```bash
# Backend
python main.py

# Frontend
npm run dev
```

The RAG Management dashboard is now available at `/admin/rag`, with new Security and Organization centers available in the sidebar.
