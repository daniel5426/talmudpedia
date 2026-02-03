# Platform Overview – Enterprise AI Operating System

TalmudPedia is a foundational **AI Development and Execution OS** designed for organizations to build, govern, and operate sophisticated AI systems at scale. It provides a unified control plane for models, data, tools, and reasoning workflows while remaining fully agnostic to vendors and infrastructure.

The platform is built on the philosophy of **"Separation of Concerns"**, where data ingestion (RAG) and reasoning (Agents) are decoupled through a central bridge: the **Knowledge Store**.

---

## 🏗️ High-Level Architecture

The platform is organized into independent, root-level domains that communicate through stable service contracts.

```text
       ┌─────────────────────────────────────────────────────────┐
       │                   Governance & Identity                 │
       └───────────────────────────┬─────────────────────────────┘
                                   │
       ┌───────────────────────────▼─────────────────────────────┐
       │               Unified Execution Kernel                  │
       │        (Jobs, Traces, Streaming, State Management)       │
       └─────┬─────────────────────┬───────────────────────┬─────┘
             │                     │                       │
 ┌───────────▼───────────┐ ┌───────▼─────────────┐ ┌───────▼──────────┐
 │      RAG Domain       │ │   Knowledge Store   │ │   Agent Domain   │
 │ (Ingestion Pipelines) │ │    (The Bridge)     │ │ (Reasoning Flows)│
 └───────────┬───────────┘ └───────▲─────────────┘ └───────┬──────────┘
             │                     │                       │
             └─────────────────────┴───────────────────────┘
                                   │
 ┌─────────────────────────────────▼──────────────────────────────────┐
 │                  Resource Layer (Shared Assets)                    │
 │         (Model Registry, Tool Catalog, Artifact Registry)          │
 └────────────────────────────────────────────────────────────────────┘
```

---

## 💎 Core Domains

### 1. Resource Layer (Models, Tools & Artifacts)
Defines **what** capabilities exist.
- **Model Registry**: A central hub for Chat, Embedding, and Reranking models. Supports tenant-specific configurations and automatic dimension resolution.
- **Tool Catalog**: A registry of callable assets (APIs, specialized handlers) that Agents can utilize.
- **Artifact Registry**: A filesystem-based extension system that allows deploying versioned, manifest-driven code blocks (Handlers) as first-class operators.

### 2. RAG Domain (Knowledge Builder)
Responsible for **how raw data becomes knowledge**.
- **Visual Pipeline Builder**: A drag-and-drop interface for constructing complex ingestion and retrieval DAGs.
- **Operator Ecosystem**: Supports diverse processing nodes including OCR, PII redaction, semantic chunking, and LLM-based enrichment.
- **Extensibility**: Developers can inject logic via **Custom Python Operators** (browser-based) or **Code Artifacts** (filesystem-based).

### 3. Knowledge Store (The Bridge) 🚀
The central abstraction that decouples domain logic from physical vector databases.
- **Implementation Independence**: Agents and Pipelines interact with logical "Knowledge Stores" rather than specific database instances.
- **Unified Interface**: Handles embedding generation, vector search, and reranking policies (Semantic, Hybrid, Keyword) transparently.
- **Cascading Lifecycle**: Manages the link between ingestion pipelines and retrieval requests.

### 4. Agent Domain (Reasoning & Orchestration)
Responsible for **decision-making workflows**.
- **LangGraph Integration**: Powered by a sophisticated state-machine engine supporting cyclic workflows, loops, and retries.
- **Logic Engine (CEL)**: Uses Common Expression Language for safe, high-performance branching and data transformation.
- **Human-in-the-Loop**: Built-in support for "User Approval" nodes and interactive state updates.
- **Streaming & Tracing**: Real-time event firehose for tokens, thoughts, and retrieval results.

### 5. Execution & Governance
The foundation that ensures **reliability and trust**.
- **Service Layer Pattern**: All domains are refactored into clean Service Layers (`AgentService`, `RetrievalService`, etc.) for robust API interaction.
- **Divergent Observability**: Unified engine with separate modes for **Playground (Full Trace)** and **Production (Clean Output)**.
- **Multi-Tenancy**: First-class support for tenant isolation, scoped resources, and RBAC.

---

## 🛠️ Operator Hierarchy
The platform supports three levels of functional extension:

| Type | Storage | Best For... | Developer Experience |
| :--- | :--- | :--- | :--- |
| **Built-in** | Source Code | Standardized logic (Loaders, Chunkers) | No-code (Config only) |
| **Custom Python** | Database | Quick hacks, "Escape hatch" logic | In-browser Editor |
| **Artifacts** | Filesystem | Heavy logic, specialized libraries, external SDKs | Local Dev / Git-based |

---

## 🚀 Key Capabilities

- **Vendor Agnostic**: Seamlessly swap between OpenAI, Anthropic, or Self-hosted models.
- **Hybrid Search**: Out-of-the-box support for Vector (Semantic), Keyword, and Reranked search flows.
- **Traceability**: Every reasoning step and data transformation is recorded and inspectable.
- **Safe Execution**: User-code is executed in restricted environments with curated standard libraries.
- **Dynamic Frontend**: Modern, responsive UI built with Next.js, Radix UI, and React Flow.

---

## 💻 Technology Stack

- **Backend**: Python 3.11+, FastAPI (Async), LangGraph, SQLAlchemy (Async).
- **Frontend**: TypeScript, Next.js 14, Shadcn/UI, xyflow (React Flow).
- **Data**: PostgreSQL (Metadata & pgvector), MongoDB (Legacy/Specific Data), Redis (Caching/Workers).
- **Orchestration**: Celery & BackgroundTasks.
- **Infrastructure**: Docker, AWS/GCP ready.

---

## 🔮 Platform Vision

TalmudPedia serves as a **long-lived AI operating system**. It allows organizations to:
1.  **Iterate Fast**: Build and test agents in minutes using the Playground.
2.  **Govern Everything**: Enforce consistent security and cost policies across all AI apps.
3.  **Future Proof**: Switch models or vector stores as the ecosystem evolves without rewriting a single agent.
