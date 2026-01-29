# Agent Execution State Overview

This document outlines the architectural model of agent execution, following the **"Unified Engine, Divergent Observability"** pattern established in [ADR 001](./architecture/001_agent_execution_modes.md).

## Core Architecture
The platform consumes a single, unified execution engine (`AgentExecutorService`) for all use cases, but differentiates behavior via **Execution Modes**.

### 1. Unified Execution Engine
-   **Service**: `AgentExecutorService`
-   **Logic**: Runs the exact same LangGraph-compiled workflow for both Playground (Debug) and Production.
-   **Persistence**: Uses an **asynchronous "fire-and-forget" pattern**. Database writes (Traces, Runs) are dispatched to background tasks to ensure they never block the real-time token stream.

### 2. Execution Modes & Observability
We enforce strict separation of concerns via the `StreamAdapter`.

| Feature | **Debug Mode** (Playground / Builder) | **Production Mode** (End-User) |
| :--- | :--- | :--- |
| **Stream Content** | Full "Firehose" (Inputs, Tool Calls, Internal Thought, Tokens) | "Clean" Stream (Final Tokens & Status only) |
| **Latency** | Optimized for completeness | Optimized for TTFT (Time To First Token) |
| **Event Visibility** | `INTERNAL` + `CLIENT_SAFE` | `CLIENT_SAFE` Only |
| **Auth Scope** | Internal / Admin Tokens | Public / Client Tokens (Forced) |

#### StreamAdapter
The `StreamAdapter` sits between the Engine and the API Response. It filters the raw event stream based on the requested `ExecutionMode`.
-   **Input**: Raw engine stream (yields everything).
-   **Filter**: Checks `event.visibility` (`INTERNAL` vs `CLIENT_SAFE`).
-   **Output**: Filtered stream safe for the client.

## Interfaces

### 1. Agent Playground & Builder (Debug Mode)
**Purpose**: Interactive environment for testing, debugging, and iterating.

-   **UI**: `ExecutionPanel` (Builder) and Playground use a **Unified Hook** (`useAgentExecution`).
-   **Visualization**:
    -   Renders real-time "Reasoning Traces" (collapsible steps).
    -   Shows raw inputs/outputs for tools.
    -   Displays errors with full stack context.
-   **State Management**: Uses a centralized reducer machine (`idle` -> `running` -> `completed`).

### 2. General Agent Usage (Production Mode)
**Purpose**: The production runtime for end-user applications.

-   **API**: `POST /agents/{id}/stream?mode=production` or `POST /agents/{id}/run`.
-   **Behavior**:
    -   **Silent Tracing**: Full high-fidelity traces are written to DB asynchronously for audit/debug later.
    -   **Clean Output**: The user receives only the final answer tokens and necessary status updates. No internal reasoning or tool inputs are leaked.

## Key Constraints
1.  **Side-Effect Free Observation**: logging to the DB never awaits in the hot path.
2.  **Auth-Scoped Enforcement**: Public tokens cannot request `DEBUG` mode.
3.  **Stateless Hooks**: Frontend hooks (`useAgentExecution`) do not retain state between runs, preventing cross-run contamination.
