# Agent Playground - Current State

## Overview

The Agent Playground is a testing and debugging interface for agent workflows. It provides a real-time, interactive environment where developers can test agent executions with full visibility into the execution process. The playground combines a modern chat interface (matching the production chat experience) with a detailed execution trace sidebar for technical debugging.

## Architecture

### Frontend Components

#### Main Page (`frontend/src/app/admin/agents/[id]/run/page.tsx`)
- **Purpose**: Main entry point for the agent playground
- **Layout**: Split-screen design with chat workspace on the left and execution sidebar on the right
- **Features**:
  - Agent metadata loading and display
  - Navigation to agent builder
  - Responsive layout (sidebar hidden on smaller screens)
  - Full-screen height with proper overflow handling

#### Agent Run Controller (`frontend/src/app/admin/agents/[id]/run/useAgentRunController.ts`)
- **Purpose**: Manages agent execution state and streaming event processing
- **Implements**: `ChatController` interface for compatibility with chat components
- **Key Features**:
  - Real-time streaming of LangGraph execution events via SSE
  - Parses and processes LangGraph v2 event types:
    - `on_chat_model_stream`: Captures streaming model output
    - `on_tool_start` / `on_tool_end`: Tracks tool executions
    - `on_chain_start` / `on_chain_end`: Tracks node/graph executions
  - Maintains separate state for:
    - Chat messages (user/assistant)
    - Streaming content
    - Reasoning steps (Chain of Thought)
    - Execution steps (for sidebar)
  - Abort controller support for stopping executions
  - Thinking duration tracking

#### Execution Sidebar (`frontend/src/app/admin/agents/[id]/run/ExecutionSidebar.tsx`)
- **Purpose**: Displays detailed execution trace in real-time
- **Features**:
  - Timeline visualization of execution steps
  - Step status indicators (pending, running, completed, error)
  - Expandable step details showing:
    - Input parameters (JSON formatted)
    - Output results (JSON formatted)
  - Type indicators (tool vs node)
  - Timestamp display for each step
  - Empty state when no execution has occurred

#### Service Layer (`frontend/src/services/agent-resources.ts`)
- **Method**: `streamAgent(agentId, input)`
- **Implementation**: Uses `httpClient.requestRaw()` to get a streaming response
- **Endpoint**: `POST /agents/{agent_id}/stream`
- **Request Format**: 
  ```json
  {
    "input": "user text input",
    "messages": [],
    "context": {}
  }
  ```
- **Response**: Server-Sent Events (SSE) stream with JSON events

### Streaming Implementation

The playground uses a "Streaming-Native" architecture to ensure real-time feedback and full observability.

#### 1. Streaming-Native Default
To maintain consistency between UI (tokens) and observability (tracing/logs), the platform treats streaming as the default execution mode. Even when a non-streaming call is made internally, the system uses streaming under the hood to ensure all observers (like the playground) receive real-time updates.

#### 2. LLMProvider Adapter (`backend/app/agent/core/llm_adapter.py`)
Since the platform uses a custom `LLMProvider` abstraction to support multiple vendors/models, a bridge is used to integrate with LangGraph's streaming engine:
- **`LLMProviderAdapter`**: A class inheriting from LangChain's `BaseChatModel`.
- **Token Dispatch**: In its `_astream` (and `_agenerate`) methods, it manually calls `run_manager.on_llm_new_token()` for every chunk received from the provider.
- **Protocol Normalization**: It translates vendor-specific chunks (e.g., OpenAI's `response.output_text.delta` or Gemini's `GenerateContentResponse`) into standardized LangChain `ChatGenerationChunk` objects.

#### 3. Callback Propagation (The "Pro" Way)
For streaming events (like `on_chat_model_stream`) to be emitted by LangGraph, the execution context must flow from the graph down to the model:
- **Node Signature**: Every node in the compiled graph (e.g., `llm_node`) accepts both `state` and the execution `config`.
- **Config Passing**: The `config` object, which contains the streaming callbacks, is passed directly to the `adapter.ainvoke()` or `adapter.astream()` call.
- **Emission**: LangGraph intercepts these calls and emits the events consumed by the playground controller.

### Backend API

#### Streaming Endpoint (`backend/app/api/routers/agents.py`)
- **Route**: `POST /agents/{agent_id}/stream`
- **Purpose**: Streams agent execution events in real-time
- **Implementation**:
  - Uses FastAPI `StreamingResponse` with `text/event-stream` media type
  - Compiles agent graph using `AgentCompiler`
  - Streams LangGraph v2 events via `executable.stream()`
  - Events are serialized as JSON and sent as SSE data lines
  - Sends `{"type": "done"}` event when execution completes
  - Handles errors by sending error events in the stream

#### Event Format
LangGraph events are streamed with the following structure:
```json
{
  "event": "on_chat_model_stream|on_tool_start|on_tool_end|on_chain_start|on_chain_end",
  "name": "tool_or_node_name",
  "run_id": "unique_run_identifier",
  "data": {
    "chunk": { "content": "..." },  // for chat_model_stream
    "input": {...},                  // for tool/chain_start
    "output": {...}                  // for tool/chain_end
  }
}
```

## User Experience

### Chat Interface
- Uses the same high-quality components as the production chat (`ChatWorkspace`, `Message`, `BotImputArea`)
- Supports Chain of Thought visualization
- Real-time streaming of assistant responses
- Message actions (copy, like/dislike, retry)
- Empty state with branded messaging

### Execution Trace
- Real-time updates as execution progresses
- Visual timeline with status indicators
- Expandable details for debugging
- Color-coded status (green for completed, primary for running, red for errors)
- Scrollable list for long execution traces

## Technical Details

### Event Processing Flow
1. User submits input via chat interface
2. Frontend calls `agentService.streamAgent()`
3. Backend compiles and executes agent graph
4. LangGraph events are streamed as SSE
5. Frontend parses events and updates:
   - Chat messages (for model output)
   - Reasoning steps (for Chain of Thought)
   - Execution steps (for sidebar trace)
6. UI updates in real-time as events arrive

### State Management
- **Messages**: Full conversation history
- **Streaming Content**: Current streaming text (replaced by final message on completion)
- **Current Reasoning**: Active reasoning steps being displayed
- **Execution Steps**: Technical trace for sidebar
- **UI State**: Loading, error states, etc.

### Error Handling
- Network errors caught and logged
- Malformed JSON events are caught and logged (execution continues)
- Abort controller allows user to stop execution
- Error states displayed in execution trace sidebar

## Current Limitations

1. **Voice Mode**: Not supported in playground (disabled)
2. **Chat History**: No persistence - each page load starts fresh
3. **Source Citations**: Click handler is a no-op (could be enhanced)
4. **Error Recovery**: Limited error recovery mechanisms
5. **Sidebar Visibility**: Hidden on screens smaller than `lg` breakpoint

## Future Enhancements

### Potential Improvements
1. **Execution Persistence**: Save execution traces for later review
2. **Export Functionality**: Export execution traces as JSON/logs
3. **Step Filtering**: Filter execution steps by type (tool/node)
4. **Search in Trace**: Search within execution step inputs/outputs
5. **Performance Metrics**: Display timing information for each step
6. **Error Details**: Enhanced error display with stack traces
7. **Comparison Mode**: Compare executions side-by-side
8. **Breakpoints**: Pause execution at specific steps for inspection

## Integration Points

### Dependencies
- `ChatWorkspace` from `ChatPane.tsx` (reused component)
- `Conversation` component (provides StickToBottom context)
- `useChatController` types and utilities
- Agent service for API communication
- LangGraph event streaming protocol

### Related Systems
- **Agent Builder**: Linked via "Builder" button in header
- **Agent Management**: Linked via back button to agents list
- **Chat System**: Shares UI components and patterns

## File Structure

```
frontend/src/app/admin/agents/[id]/run/
├── page.tsx                    # Main playground page
├── useAgentRunController.ts    # Execution controller hook
└── ExecutionSidebar.tsx        # Execution trace sidebar

backend/app/api/routers/
└── agents.py                   # Contains /stream endpoint
```

## Usage

1. Navigate to `/admin/agents/{agent_id}/run`
2. Agent metadata is loaded and displayed in header
3. User types message in chat input
4. Execution begins and events stream in real-time
5. Chat shows assistant response as it streams
6. Sidebar shows detailed execution trace
7. User can expand steps to see input/output details
8. User can retry, copy, or provide feedback on responses

## Notes

- The playground uses the same chat components as production for consistency
- Execution trace provides deep visibility for debugging complex agent workflows
- Real-time streaming ensures immediate feedback during execution
- The split-screen layout balances user experience with technical debugging needs
