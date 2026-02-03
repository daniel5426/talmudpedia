# Agent Management Current State

## Overview
The Agent subsystem is a sophisticated, graph-based orchestration engine designed to build and deploy autonomous AI agents. Similar to the RAG pipeline, it utilizes a visual, node-based approach powered by LangGraph to manage complex conversational flows, tool usage, and multi-step reasoning.

## Core Domain Features

### 1. Visual Agent Builder
- **Graph-Based Construction**: Built on `@xyflow/react`, allowing users to define agent logic as a Directed Acyclic Graph (DAG) or cyclic workflows (for loops/retries).
- **Unified Node Shell**: Uses a shared `BaseNode` component for consistent visual design and integrated handle positioning across the platform.
- **Specialized Node Layouts**: Row-based layouts for logic and interaction nodes (If/Else, While, User Approval) that align branch labels directly with their output handles.
- **Node-Based Architecture**:
    - **Input/Start**: Entry points for user queries and initial state initialization.
    - **Reasoning (Agent)**: Primary reasoning nodes with multi-tool binding and reasoning effort control.
    - **Logic (If/Else, While)**: Dynamic branching and looping powered by restricted CEL expressions.
    - **Data (Transform, Set State)**: Direct manipulation of agent `state` via expression-based mapping or literal assignments.
    - **Actions (Tool/RAG)**: Integration points for external capabilities.
- **Dynamic Configuration**: Each node type has a specific configuration schema (e.g., `model_id`, `temperature`, `system_prompt` for LLM nodes).
- **Subdued Aesthetic**: Operator colors utilize a softened, pastel palette harmonized with the RAG Pipeline Builder to reduce visual noise.
- **Decoupled Data Flow (Field Mapping)**: Artifact nodes utilize an explicit input/output mapping system, decoupling logic from global state.
    - **Expression-Based Mapping**: Users map artifact inputs to `{{ state.var }}` or `{{ upstream.node.field }}`.
    - **Contract Enforcement**: Artifacts declare their schema in `artifact.yaml`, which the builder uses to generate configuration UIs.

### 2. LangGraph & Logic Engine
- **State vs Context**: Clear architectural distinction between persistent `state` (checkpointed) and ephemeral `context` (erased between major steps).
- **CEL Engine**: Integration of restricted Common Expression Language (CEL) for safe, performant logic evaluation without risk of side effects.
- **State Management**: Uses a centralized `AgentState` to track message history, reasoning steps, and persistent user-defined variables.
- **Compiler & Executable**: An `AgentCompiler` validates the visual graph and transforms it into a `CompiledStateGraph` (LangGraph).
- **Cyclic Support**: Full support for loops and iterative reasoning patterns (e.g., `While` nodes with max iteration safety).

### 3. Unified Model & Tool Registry
- **Model Resolution**: Integrates with the platform's `ModelResolver` to dynamically bind LLM nodes to specific model providers at runtime.
- **Tool Ecosystem**: Agents can be equipped with tools from a managed registry, allowing them to perform actions like semantic search (via RAG retrievers), data fetching, or calculations.

### 4. Advanced Execution & Streaming
- **Event-Driven Streaming**: Supports `astream_events` (v2) for real-time feedback, including:
    - **Token Streaming**: Live text generation.
    - **Reasoning Steps**: Transparent visualization of the agent's internal "thought process".
    - **Retrieval Artifacts**: Real-time display of cited documents during RAG-enabled steps.
- **Thinking Duration Tracking**: Built-in timers to measure and display how long an agent spent "thinking" before responding.
- **Isolated Background Execution**: Agent runs are executed in a background task with a dedicated database session, ensuring stability regardless of the triggering HTTP request's lifecycle.

### 5. Persistence & Versioning
- **Database Models**:
    - `Agent`: Stores the `graph_definition`, metadata, and high-level configuration (memory, constraints).
    - `AgentVersion`: Snapshots of agent configurations for rollback and deployment tracking.
    - `AgentRun`: Records individual executions, including status (`queued`, `running`, `paused`, `completed`, `failed`), output results, usage (tokens/cost), and `checkpoint` data for resumption.
    - `AgentTrace`: Detailed span-level telemetry (inputs, outputs, timing) for debugging complex multi-step runs.

## System Architecture

### Backend Stack
- **API**: FastAPI providing endpoints for chat, management, and execution.
- **Orchestration**: LangGraph for the underlying state machine logic.
- **Database**: PostgreSQL with SQLAlchemy for persistence of agents, runs, and traces.
- **Telemetry**: Custom tracing system for monitoring agent performance and step-level execution.

### Frontend Stack
- **Interface**: Next.js with a dedicated `AgentBuilder` component.
- **Canvas**: React Flow (XYFlow) for the visual logic editor.
- **Shared Architecture**: Unified `BaseNode`, `ConfigPanel`, and `FloatingPanel` components ensure functional and aesthetic parity with the Pipeline Builder.
- **Consolidated Service Layer**: Standardized `agentService`, `modelsService`, and `toolsService` modules for streamlined API interaction and state management.

## Implementation State

| Feature | Status | Details |
| :--- | :--- | :--- |
| Visual Agent Builder | ✅ Completed | Drag-and-drop interface with specialized branch-row UI. |
| LangGraph Compiler | ✅ Completed | Translation of visual graphs into executable LangGraph states. |
| Logic Engine (CEL) | ✅ Completed | Safe, restricted CEL evaluation for conditions and transforms. |
| Looping (While) | ✅ Completed | Iterative workflows with iteration counters and safety limits. |
| Data Manipulation | ✅ Completed | `Transform` and `Set State` nodes for complex state reshaping. |
| Streaming API | ✅ Completed | Robust SSE/NDJSON streaming of tokens and reasoning steps. |
| Model Resolver Integration | ✅ Completed | Dynamic model binding based on tenant configuration. |
| Tracing & Telemetry | ✅ Completed | Detailed recording of agent runs and internal spans. |
| Versioning System | ✅ Completed | Snapshot-based versioning for agent configurations. |
| Tool Call Nodes | ✅ Completed | Infrastructure for external capabilities resolution and execution. |
| Human-in-the-loop | ✅ Completed | Specialized User Approval UI with Approve/Reject branching. |
| Unified Node UI | ✅ Completed | Consistent shell and handle positioning shared with Pipeline Builder. |
| Conditional Routing | ✅ Completed | Multi-branch If/Else support with dynamic rows and labels. |
| Field Mapping | ✅ Completed | Decoupled data flow for artifacts with `{{ expr }}` resolution. |
| Memory Management | 🚧 In Progress | Short-term memory active; long-term/vector memory in development. |

## Next Implementation Priorities
1. **Performance Analytics**: Dashboard for visualizing agent cost, latency, and success rates across versions.
2. **Advanced Tool Integration**: Streamlining the process of adding and configuring custom tools within the builder.
3. **Multi-Agent Collaboration**: Enabling agents to call other agents as tools.
4. **Long-term Memory (Vector)**: Integration with knowledge bases for persistent agent memory.
5. **Classify & Guardrail Nodes**: Specialized reasoning nodes for automated intent classification and safety checks.
