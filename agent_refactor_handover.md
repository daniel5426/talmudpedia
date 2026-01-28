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

### 3. Graph Validation & Compilation (`Phase 3`)
- **AgentCompiler**:
    - **Structural Checks**: Connectivity, single start/end, reachability.
    - **Schema Validation**: Nodes validated against JSON schemas at compile-time.
    - **Data Flow Contracts**: Compiler verifies that all `reads` are satisfied by upstream `writes`.
    - **Parallel Safety**: Detects if parallel branches write to the same `AgentStateField`.
- **Component Resolvers**: `ToolResolver` and `RAGPipelineResolver` implemented for strict ID verification.
- **Models**: Created `CompiledAgent` (immutable snapshot) and updated `ExecutableAgent`.

---

## 🚀 Next Phases

### 📦 Phase 4: Execution Engine Upgrade (High Priority)
- **AgentExecutor Service**: Implement the background job runner for Agents (similar to RAG PipelineExecutor).
- **Persistence & Checkpointing**: Save execution state to the database to allow resuming "Paused" (Human Input) runs.
- **Advanced Tracing**: Enhance `AgentTrace` to capture per-node I/O, performance metrics, and logic branches.
- **Streaming**: Unify `astream_events` to provide real-time feedback to the UI.

### 🎨 Phase 5: Visual Builder Enhancement
- **Schema-Driven Config**: Update the `ConfigPanel` to automatically generate UI inputs based on the node's `config_schema`.
- **Connection Validation**: Real-time feedback in ReactFlow when `reads`/`writes` are incompatible.
- **Execution Mode**: A new builder view to step through an active execution.

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

**Immediate Next Step**: Implementation of the `AgentExecutor` service in Phase 4 to bridge the gap between "Compiled" and "Running".
