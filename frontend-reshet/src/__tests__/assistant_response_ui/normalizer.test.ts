import {
  adaptRunStreamEvent,
  applyRunStreamEventToBlocks,
  extractStructuredAssistantText,
  finalizeAssistantRenderBlocks,
  sortChatRenderBlocks,
} from "@/services/chat-presentation";
import type { ChatRenderBlock } from "@/services/chat-presentation";

describe("chat presentation normalizer", () => {
  it("keeps tool calls inline and does not duplicate synthesized tool reasoning rows", () => {
    let blocks: ChatRenderBlock[] = [];

    blocks = sortChatRenderBlocks(
      applyRunStreamEventToBlocks(
        blocks,
        adaptRunStreamEvent(
          {
            version: "run-stream.v2",
            seq: 1,
            ts: "2026-03-06T10:00:00Z",
            event: "tool.started",
            run_id: "run-1",
            stage: "tool",
            payload: {
              span_id: "call-1",
              tool: "platform sdk",
              tool_slug: "platform-agents",
              action: "agents.nodes.validate",
              display_name: "Validate agent graph",
              summary: "Validate agent graph",
              input: { action: "agents.nodes.validate", agent_id: "agent-1" },
            },
            diagnostics: [],
          },
          0,
        ),
      ),
    );

    blocks = sortChatRenderBlocks(
      applyRunStreamEventToBlocks(
        blocks,
        adaptRunStreamEvent(
          {
            version: "run-stream.v2",
            seq: 2,
            ts: "2026-03-06T10:00:01Z",
            event: "reasoning.update",
            run_id: "run-1",
            stage: "reasoning",
            payload: {
              step: "platform sdk",
              step_id: "call-1",
              status: "active",
              message: "Calling tool platform sdk...",
            },
            diagnostics: [],
          },
          1,
        ),
      ),
    );

    blocks = sortChatRenderBlocks(
      applyRunStreamEventToBlocks(
        blocks,
        adaptRunStreamEvent(
          {
            version: "run-stream.v2",
            seq: 3,
            ts: "2026-03-06T10:00:02Z",
            event: "assistant.delta",
            run_id: "run-1",
            stage: "assistant",
            payload: { content: "Validation completed." },
            diagnostics: [],
          },
          2,
        ),
      ),
    );

    blocks = sortChatRenderBlocks(
      applyRunStreamEventToBlocks(
        blocks,
        adaptRunStreamEvent(
          {
            version: "run-stream.v2",
            seq: 4,
            ts: "2026-03-06T10:00:03Z",
            event: "tool.completed",
            run_id: "run-1",
            stage: "tool",
            payload: {
              span_id: "call-1",
              tool: "platform sdk",
              tool_slug: "platform-agents",
              action: "agents.nodes.validate",
              display_name: "Validate agent graph",
              summary: "Validate agent graph",
              output: { valid: true },
            },
            diagnostics: [],
          },
          3,
        ),
      ),
    );

    expect(blocks.map((block) => block.kind)).toEqual(["tool_call", "assistant_text"]);
    expect(blocks[0].kind).toBe("tool_call");
    expect(blocks[0].tool.title).toBe("Validate agent graph");
    expect(blocks[1].kind).toBe("assistant_text");
  });

  it("extracts user-facing text from architect envelopes and falls back safely", () => {
    const structured = JSON.stringify({
      extracted_intent: "greeting",
      next_actions: [
        {
          action_type: "respond_to_user",
          payload: "Hello! How can I help you today?",
        },
      ],
    });

    expect(extractStructuredAssistantText(structured)).toBe("Hello! How can I help you today?");
    expect(extractStructuredAssistantText("plain text")).toBe("plain text");
  });

  it("replaces streamed json text with parsed final assistant text on finalize", () => {
    const initial = sortChatRenderBlocks(
      applyRunStreamEventToBlocks(
        [],
        adaptRunStreamEvent(
          {
            version: "run-stream.v2",
            seq: 1,
            ts: "2026-03-06T10:00:00Z",
            event: "assistant.delta",
            run_id: "run-1",
            stage: "assistant",
            payload: { content: '{"next_actions":[{"action_type":"respond_to_user","payload":"Hi there"}]}' },
            diagnostics: [],
          },
          0,
        ),
      ),
    );

    const finalized = finalizeAssistantRenderBlocks(initial, '{"next_actions":[{"action_type":"respond_to_user","payload":"Hi there"}]}');

    expect(finalized).toHaveLength(1);
    expect(finalized[0].kind).toBe("assistant_text");
    expect(finalized[0].text).toBe("Hi there");
  });
});
