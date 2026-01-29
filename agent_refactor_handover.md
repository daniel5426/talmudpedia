# Agent System Refactor: Handover & Roadmap

## 🎯 Goal of the Refactor
The primary goal is to upgrade the current Agent system from a basic pipeline-like structure to a robust, enterprise-grade orchestration engine. We are moving away from simple "data pipes" to a **State-Managed Agentic Loop** (using LangGraph). 

**Key Architectural Pillars:**
1.  **Strict State Contracts**: Nodes declare `reads` and `writes` against a shared `AgentState`.
2.  **Compile-Time Resolution**: Tools and RAG pipelines are resolved and verified during compilation, not execution.
3.  **Immutable Snapshots**: Executions run against a `CompiledAgent` snapshot to ensure reliability and replayability.
4.  **Parallel Safety**: Ensuring multi-branch execution doesn't cause state corruption.

---

## ✅ Accomplished So Far

### 1. Foundation & Registry (`Phase 1`)
- **Operator Registry**: Implemented `AgentOperatorRegistry` and `AgentOperatorSpec`. All node types are dynamically registered with metadata (UI icons, categories).
- **State Fields**: Formalized `AgentStateField` (MESSAGE_HISTORY, CONTEXT, OBSERVATIONS, etc.) to replace generic JSON blobs.
- **Executor Registry**: Created a decoupled `AgentExecutorRegistry` to map node types to their Python logic.
- **Base Executor**: Implemented `BaseNodeExecutor` with `can_execute()` gating for human-in-the-loop and conditional logic.

### 2. Node Implementations (`Phase 2`)
- **ToolNodeExecutor**: Indirect resolution via `ToolResolver`. Supports HTTP and internal functions.
- **RAGNodeExecutor**: Direct integration with the RAG subsystem; executes pipelines as part of the agent loop.
- **ConditionalNode**: Implemented branching logic (contains, regex, LLM decision).
- **HumanInputNode**: Designed to **PAUSE** execution rather than block threads.
- **ParallelNode**: Placeholder logic integrated with compiler validation.

- **Models**: Created `CompiledAgent` (immutable snapshot) and updated `ExecutableAgent`.

### 4. Execution Engine & Persistence (`Phase 4`)
- **AgentExecutor Service**: Implemented robust background job runner.
    - **Session Isolation**: Refactored to use independent database sessions per execution run to prevent `IllegalStateChangeError`.
    - **Checkpointer**: Integrated LangGraph `MemorySaver` (pluggable for Postgres) for state persistence.
- **Human-in-the-Loop**: Fully implemented pausing and resumption logic.
- **Unified Tracing**: Comprehensive `AgentTrace` capture including inputs, outputs, and timestamps.
- **API Lifecycle**: 100% coverage of agent management (CRUD), versioning, and execution endpoints.

---

## 🚀 Next Phases

### 📦 Phase 5: Advanced Visual Builder (High Priority)
- **Schema-Driven Config**: Update the `ConfigPanel` to automatically generate UI inputs based on the node's `config_schema`.
- **Connection Validation**: Real-time feedback in ReactFlow when `reads`/`writes` are incompatible.
- **Execution Mode**: A new builder view to step through an active execution and visualize tokens/reasoning.

### 🐍 Phase 6: Custom Agent Operators
- **Python Sandbox**: Allow users to write custom Python logic for agent nodes.
- **Lifecycle Management**: CRUD for custom operators and secure execution.

### 🧠 Phase 7: Memory & Context
- **Windowed Memory**: Configurable short-term message history management.
- **Vector Memory**: Integration for long-term associative memory.
- **Context Variables**: System-level variables for globally accessible data.

### 🔌 Phase 8: Integration & API
- **Invoke API**: `POST /agents/{slug}/invoke` for external consumption.
- **Webhook Support**: Trigger agent runs from external events.
- **Chat Widget**: Embeddable UI component for interacting with agents.

---

## 🛠 Handover Instructions for New Agent
1.  **Core Logic**: Located in `backend/app/agent/`.
2.  **Registry**: `backend/app/agent/registry.py`.
3.  **Compiler**: `backend/app/agent/graph/compiler.py`.
4.  **Executors**: `backend/app/agent/executors/`.
5.  **State**: `backend/app/agent/core/state.py`.
6.  **Models**: `backend/app/agent/models.py` (CompiledAgent).

7.  **API**: `backend/app/api/routers/agents.py`.
8.  **Service**: `backend/app/agent/execution/service.py`.

**Critical Note on Sessions**: Background execution must use `_execute_with_new_session()` to avoid sharing sessions with the API request thread, which causes threading errors in SQLAlchemy.

**Immediate Next Step**: Implementing the **Execution Mode** UI in the `AgentBuilder` to visualize the backend state machine.
