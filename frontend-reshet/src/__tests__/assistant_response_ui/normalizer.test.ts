import {
  adaptRunStreamEvent,
  applyRunStreamEventToBlocks,
  createAssistantTextBlock,
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
    const toolBlock = blocks[0];
    const textBlock = blocks[1];
    expect(toolBlock.kind).toBe("tool_call");
    expect(toolBlock.kind === "tool_call" ? toolBlock.tool.title : null).toBe("Validate agent nodes");
    expect(toolBlock.kind === "tool_call" ? toolBlock.tool.displayName : null).toBe("Validate agent graph");
    expect(textBlock.kind).toBe("assistant_text");
  });

  it("starts a new assistant text block after a tool event so live chronology stays inline", () => {
    let blocks: ChatRenderBlock[] = [];

    blocks = sortChatRenderBlocks(
      applyRunStreamEventToBlocks(
        blocks,
        adaptRunStreamEvent(
          {
            version: "run-stream.v2",
            seq: 1,
            ts: "2026-04-05T10:00:00Z",
            event: "assistant.delta",
            run_id: "run-chronology",
            stage: "assistant",
            payload: { content: "First part. " },
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
            ts: "2026-04-05T10:00:01Z",
            event: "tool.started",
            run_id: "run-chronology",
            stage: "tool",
            payload: {
              span_id: "call-inline-1",
              tool: "platform sdk",
              tool_slug: "platform-agents",
              action: "agents.nodes.schema",
              display_name: "Get node schemas",
              summary: "Get node schemas",
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
            ts: "2026-04-05T10:00:02Z",
            event: "assistant.delta",
            run_id: "run-chronology",
            stage: "assistant",
            payload: { content: "Second part." },
            diagnostics: [],
          },
          2,
        ),
      ),
    );

    expect(blocks.map((block) => block.kind)).toEqual([
      "assistant_text",
      "tool_call",
      "assistant_text",
    ]);
    const firstTextBlock = blocks[0];
    const secondTextBlock = blocks[2];
    expect(firstTextBlock.kind).toBe("assistant_text");
    expect(firstTextBlock.kind === "assistant_text" ? firstTextBlock.text : null).toBe("First part. ");
    expect(secondTextBlock.kind).toBe("assistant_text");
    expect(secondTextBlock.kind === "assistant_text" ? secondTextBlock.text : null).toBe("Second part.");
  });

  it("drops provider-native tool delta objects from live assistant text", () => {
    let blocks: ChatRenderBlock[] = [];

    blocks = sortChatRenderBlocks(
      applyRunStreamEventToBlocks(
        blocks,
        adaptRunStreamEvent(
          {
            version: "run-stream.v2",
            seq: 1,
            ts: "2026-04-12T10:00:00Z",
            event: "assistant.delta",
            run_id: "run-tool-delta",
            stage: "assistant",
            payload: { content: "Sure! Let me fetch your Linear projects right away." },
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
            ts: "2026-04-12T10:00:01Z",
            event: "assistant.delta",
            run_id: "run-tool-delta",
            stage: "assistant",
            payload: {
              content:
                "{'id': 'toolu_01VDqRJyMwtk6oBdqdVN9Gjn', 'caller': {'type': 'direct'}, 'input': {}, 'name': 'mcp_line_list_projects', 'type': 'tool_use', 'index': 1}",
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
            ts: "2026-04-12T10:00:02Z",
            event: "assistant.delta",
            run_id: "run-tool-delta",
            stage: "assistant",
            payload: {
              content: "{'partial_json': '', 'type': 'input_json_delta', 'index': 1}",
            },
            diagnostics: [],
          },
          2,
        ),
      ),
    );

    expect(blocks).toHaveLength(1);
    expect(blocks[0]?.kind).toBe("assistant_text");
    expect(blocks[0]?.kind === "assistant_text" ? blocks[0].text : null).toBe(
      "Sure! Let me fetch your Linear projects right away.",
    );
  });

  it("shortens verbose platform sdk summaries into shared action titles", () => {
    const blocks = sortChatRenderBlocks(
      applyRunStreamEventToBlocks(
        [],
        adaptRunStreamEvent(
          {
            version: "run-stream.v2",
            seq: 1,
            ts: "2026-03-10T10:00:00Z",
            event: "tool.started",
            run_id: "run-2",
            stage: "tool",
            payload: {
              span_id: "call-2",
              tool: "platform sdk",
              tool_slug: "platform-rag",
              action: "rag.operators.schema",
              display_name: "Resolve schemas/contracts for multiple RAG operators in one call, including config schema and exact visual-node/create contract shape.",
              summary: "Resolve schemas/contracts for multiple RAG operators in one call, including config schema and exact visual-node/create contract shape.",
            },
            diagnostics: [],
          },
          0,
        ),
      ),
    );

    expect(blocks).toHaveLength(1);
    const toolBlock = blocks[0];
    expect(toolBlock.kind).toBe("tool_call");
    expect(toolBlock.kind === "tool_call" ? toolBlock.tool.title : null).toBe("Get RAG operator schemas");
    expect(toolBlock.kind === "tool_call" ? toolBlock.tool.summary : "").toContain("Resolve schemas/contracts for multiple RAG operators");
  });

  it("adapts persisted trace tool lifecycle events back into tool-call blocks", () => {
    const blocks = sortChatRenderBlocks(
      applyRunStreamEventToBlocks(
        [],
        adaptRunStreamEvent(
          {
            sequence: 7,
            timestamp: "2026-03-10T12:00:00Z",
            event: "on_tool_start",
            source_run_id: "run-trace-1",
            span_id: "trace-call-1",
            name: "platform sdk",
            data: {
              input: { action: "rag.operators.catalog" },
              tool_slug: "platform-rag",
              action: "rag.operators.catalog",
              display_name: "List available RAG operators with categories, summaries, and required fields.",
              summary: "List available RAG operators with categories, summaries, and required fields.",
            },
          },
          0,
        ),
      ),
    );

    expect(blocks).toHaveLength(1);
    const toolBlock = blocks[0];
    expect(toolBlock.kind).toBe("tool_call");
    expect(toolBlock.kind === "tool_call" ? toolBlock.tool.title : null).toBe("List RAG operators");
    expect(toolBlock.kind === "tool_call" ? toolBlock.tool.toolCallId : null).toBe("trace-call-1");
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
    const textBlock = finalized[0];
    expect(textBlock.kind).toBe("assistant_text");
    expect(textBlock.kind === "assistant_text" ? textBlock.text : null).toBe("Hi there");
  });

  it("collapses duplicate finalized assistant text blocks", () => {
    const finalized = finalizeAssistantRenderBlocks(
      [
        createAssistantTextBlock({
          id: "assistant-1",
          text: "What is your favorite programming language?",
          runId: "run-1",
          seq: 1,
        }),
        createAssistantTextBlock({
          id: "assistant-2",
          text: "What is your favorite programming language?",
          runId: "run-1",
          seq: 2,
        }),
      ],
      "What is your favorite programming language?",
      { runId: "run-1", fallbackSeq: 3 },
    );

    expect(finalized).toHaveLength(1);
    const textBlock = finalized[0];
    expect(textBlock.kind).toBe("assistant_text");
    expect(textBlock.kind === "assistant_text" ? textBlock.text : null).toBe("What is your favorite programming language?");
  });
});
