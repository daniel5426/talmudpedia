# ADR 001: Agent Execution Modes (Playground vs. Production)

## Context
We have two primary use cases for executing agents:
1.  **Playground / Builder (Debug Mode)**: Developers need to see *how* the agent is thinking. They need raw inputs/outputs, step-by-step reasoning, intermediate tool calls, and error traces. Speed is important, but visibility is paramount.
2.  **End-User Application (Production Mode)**: The final consumer needs a reliable, "clean" experience. They typically only care about the final response (or a streamlined stream of tokens). They should NOT see internal reasoning, raw tool outputs (unless designed as UI elements), or system prompts. Reliability and security are paramount.

## Decision: Unified Engine, Divergent Observability
We will use **one single execution engine** (`AgentExecutorService`) for both use cases. We will *not* fork the execution logic. Instead, we will differentiate based on **Observability Configurations**.

### Core Principle
> "The code that runs in the playground is the exact same code that runs in production. Only the 'Observer' changes."

### The "Observer" Pattern
The execution engine will emit a superset of all possible events (start/end nodes, tool calls, token streams, state updates). The "Mode" determines which of these events are forwarded to the client.

#### 1. Playground Mode (Debug)
-   **Stream Content**: ALL events.
-   **Verbosity**: High. Includes system prompts, raw LLM inputs, tool stdout/stderr.
-   **Persistence**: "Draft" runs. detailed traces logged.
-   **Client**: `AgentBuilder` / `AgentPlayground`.

#### 2. Production Mode (Release)
-   **Stream Content**: FILTERED events.
    -   `on_chat_model_stream` (only final answer tokens).
    -   `on_tool_end` (only if the tool is marked "Client Visible").
    -   `on_chain_end` (Final output).
-   **Verbosity**: Low. "Magic" happens behind the curtain.
-   **Persistence**: "Production" runs. Full audit logging in DB, but minimal payload over the wire.
-   **Client**: Public API / End-User Chat UI.

### Critical Constraint: Side-Effect Free Observation
⚠️ **Do NOT let "observer" influence execution timing or behavior.**

The observer must be side-effect free. This is where many systems fail.

**Bad (Prohibited):**
-   Observer blocks execution.
-   Observer backpressure slows the agent.
-   Observer failures affect agent success.
-   Observer determines retries.
-   Observer controls streaming cadence.

**Correct Rule:**
> "The agent runs as if no observer exists."

**Implementation Details:**
-   Events MUST be emitted into an async buffer / event bus / fire-and-forget queue.
-   Filtering happens *after* emission (downstream).
-   If the observer crashes, the agent MUST still complete its run.
-   If Playground mode is slower than Production mode due to network/rendering, that is acceptable.
-   If Playground mode *logic* changes behavior compared to Production, that is a **bug**.

## Observability Matrix

| Feature | Playground (Debug) | Production (User) |
| :--- | :--- | :--- |
| **Streaming** | Full Firehose (Tokens, Thoughts, Tools) | Curated Stream (Tokens only, or specific UI events) |
| **State Visibility** | Full State Inspection | Final Output Only |
| **Error Handling** | Full Stack Traces | Sanitized User-Friendly Concept |
| **Tool Calls** | Show input/output details | Show "Processing..." or specific UI widgets |
| **Persistence** | Full Trace (for identifying bugs) | Full Audit Log (for compliance/analytics) |
| **Version** | `latest` / Draft | `pinned` (Semantic Versioning) |

## Implementation Implications
1.  **Strict Strictness**: The backend `stream_agent` endpoint should accept a `mode` parameter (or infer it from the caller/auth scope).
2.  **Event Filtering**: A middleware or filter step in the SSE generator must strip sensitive/noisy events based on the mode.
3.  **Security**: Production mode must NEVER leak system prompts or raw context execution states to the client.

## Status
Accepted
