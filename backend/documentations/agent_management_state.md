# Agent Management Current State

## Overview
The Agent subsystem is a sophisticated, graph-based orchestration engine designed to build and deploy autonomous AI agents. Similar to the RAG pipeline, it utilizes a visual, node-based approach powered by LangGraph to manage complex conversational flows, tool usage, and multi-step reasoning.

## Core Domain Features

### 1. Visual Agent Builder
- **Graph-Based Construction**: Built on `@xyflow/react`, allowing users to define agent logic as a Directed Acyclic Graph (DAG) or cyclic workflows (for loops/retries).
- **Node-Based Architecture**:
    - **Unified Node Shell**: Uses a shared `BaseNode` component for consistent visual design and integrated handle positioning across the platform.
    - **Input/Start**: Entry points for user queries and initial state.
    - **LLM Call**: Core reasoning nodes where specific models (OpenAI, Gemini, etc.) are invoked with system prompts.
    - **Tool Call**: Integration points for external capabilities (Search, Retrieval, API calls).
    - **Conditional/Router**: Branching nodes for complex decision logic (T/F paths).
    - **Output/End**: Final response generation and state termination.
- **Dynamic Configuration**: Each node type has a specific configuration schema (e.g., `model_id`, `temperature`, `system_prompt` for LLM nodes).
- **Subdued Aesthetic**: Operator colors utilize a softened, pastel palette harmonized with the RAG Pipeline Builder to reduce visual noise.

### 2. LangGraph Integration
- **State Management**: Uses a centralized `AgentState` to track message history, reasoning steps, and intermediate data across the graph.
- **Compiler & Executable**: An `AgentCompiler` validates the visual graph and transforms it into a `CompiledStateGraph` (LangGraph), which is then wrapped in an `ExecutableAgent`.
- **Cyclic Support**: Unlike standard RAG pipelines, the Agent system is designed to support cycles, enabling iterative reasoning and self-correction patterns.

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
| Visual Agent Builder | ✅ Completed | Drag-and-drop interface for building agent graphs. |
| LangGraph Compiler | ✅ Completed | Translation of visual graphs into executable LangGraph states. |
| Streaming API | ✅ Completed | Robust SSE/NDJSON streaming of tokens and reasoning steps. |
| Model Resolver Integration | ✅ Completed | Dynamic model binding based on tenant configuration. |
| Tracing & Telemetry | ✅ Completed | Detailed recording of agent runs and internal spans. |
| Versioning System | ✅ Completed | Snapshot-based versioning for agent configurations. |
| Tool Call Nodes | ✅ Completed | Infrastructure for external capabilities resolution and execution. |
| Human-in-the-loop | ✅ Completed | Execution pausing/resumption for user approval or manual input. |
| Unified Node UI | ✅ Completed | Consistent shell and handle positioning shared with Pipeline Builder. |
| Conditional Routing | ✅ Completed | Robust UI support for True/False branching and handle labels. |
| Memory Management | 🚧 In Progress | Short-term memory active; long-term/vector memory in development. |

## Next Implementation Priorities
1. **Advanced Tool Integration**: Streamlining the process of adding and configuring custom tools within the builder.
2. **Refined Conditional Routing**: Implementing robust "Router" nodes for complex branching logic based on LLM output.
3. **Multi-Agent Collaboration**: Enabling agents to call other agents as tools.
4. **Long-term Memory (Vector)**: Integration with knowledge bases for persistent agent memory.
5. **Performance Analytics**: Dashboard for visualizing agent cost, latency, and success rates across versions.
