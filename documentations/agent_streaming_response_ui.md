# Agent Streaming Response UI & Architecture

This document describes the end-to-end architecture for streaming agentic responses in Talmudpedia, covering the backend event stream, frontend state management, and the high-performance UI implementation designed for zero flicker.

---

## 1. The Streaming Pipeline

### Backend: Event Synthesis
The backend execution engine emits a stream of server-sent events (SSE). To maintain a clean separation of concerns, we use an **Adapter Pattern** via the `StreamAdapter` class.

- **Token Events**: Raw text chunks from the LLM are emitted as `token` events.
- **Reasoning Events**: Internal lifecycle events (tool starts, node entries) are transformed into unified `reasoning` steps.
- **Protocol**: 
  ```text
  data: {"event": "token", "data": {"content": "Hello"}}
  data: {"type": "reasoning", "data": {"step": "Search", "status": "active"}}
  ```

### Frontend: The SSE Consumer
The `useAgentRunController` (and `useChatController`) implements the consumption logic:
1. **Buffer Management**: Incoming chunks are decoded and appended to a `fullAiContent` string.
2. **Dynamic ID Generation**: A unique `activeStreamingId` is generated at the *moment of request*. This ID remains constant throughout the stream.
3. **Throttled Updates**: State updates for `streamingContent` are handled by React, allowing for a smooth 60fps render of arriving text.

---

## 2. Zero-Flicker Architecture

The most critical part of the UX is the transition from "Streaming" (placeholder state) to "Completed" (history state). We use a three-pillar strategy to make this transition invisible:

### I. Identity Stability (The ID Fix)
We ensure that the message ID is **truly stable**.
- **Incorrect**: Generating a new `nanoid()` when the stream finishes. (Causes DOM destruction/re-creation).
- **Correct**: Using the `newStreamingId` from the `handleSubmit` closure. Because the ID never changes, React reuses the same DOM node, preserving scroll positions and component state.

### II. Layout Anchoring (`hasStarted`)
To prevent the "jump from top" bug, the `ChatPane` uses a `hasStarted` flag.
- Once a single message or token is detected, the layout is locked into "Chat Mode."
- This prevents a race condition where the UI briefly flickers back to the "Empty State" (centered prompt) during the state commit, which would cause the container height to collapse.

### III. Dynamic Scroll Lock
We use the `StickToBottom` library with customized behavior:
- **`targetScrollTop` Override**: During `isLoading`, we dynamically set the target scroll position to the *current* scroll position. This effectively disables "auto-follow" if the user has scrolled up to read history, preventing the AI from dragging the view down.
- **`auto` Resize**: We use `animation="auto"` for layout resizes to ensure instant snapping without the interpolation jitter common in "smooth" scrolling.

---

## 3. UI Component Integration

### The Render Loop
The `ChatPane` uses a unified `displayMessages` memo:
```typescript
const displayMessages = useMemo(() => {
  const list = [...messages]; // Messages already in history
  if (activeStreamingId && !isStreamingInHistory) {
    list.push({ id: activeStreamingId, ...streamingContent }); // The live placeholder
  }
  return list;
}, [...]);
```
This ensures a single coherent list where the "Live" message is treated as part of the normal flow, allowing for consistent styling and animations.

### Chain of Thought (Reasoning)
The reasoning UI is integrated directly into the `MessageContent` component.
- **Live Updates**: The `reasoningSteps` are updated via `mergeReasoningSteps`, which reconciles incoming status changes (e.g., `pending` -> `complete`) based on label labels.
- **Persistence**: Upon completion, the final reasoning steps are saved into the `ChatMessage` object in the database, ensuring that history matches the live experience.

---

## 4. Key Implementation Files
- **Backend**: `backend/app/agent/execution/adapter.py` (Event filtering/synthesis)
- **Controllers**: `frontend/src/app/admin/agents/playground/useAgentRunController.ts` (Stream consumption)
- **UI**: `frontend/src/components/layout/ChatPane.tsx` (Stable rendering and layout)
- **Components**: `frontend/src/components/ai-elements/conversation.tsx` (Scroll management)
