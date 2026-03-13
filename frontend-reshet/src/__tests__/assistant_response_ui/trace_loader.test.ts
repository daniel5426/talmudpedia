import { buildResponseBlocksFromRunTrace } from "@/services/run-trace-blocks";

describe("run trace block loader", () => {
  it("rebuilds response blocks from persisted run events", async () => {
    const blocks = await buildResponseBlocksFromRunTrace(
      "run-123",
      "List RAG operators\nFound 12 operators.",
      async () => ({
        run_id: "run-123",
        event_count: 3,
        events: [
          {
            version: "run-stream.v2",
            seq: 1,
            ts: "2026-03-12T03:00:00Z",
            event: "tool.started",
            run_id: "run-123",
            stage: "tool",
            payload: {
              span_id: "call-1",
              tool: "platform sdk",
              tool_slug: "platform-rag",
              action: "rag.operators.catalog",
              display_name: "List RAG operators",
              summary: "List RAG operators",
            },
            diagnostics: [],
          },
          {
            version: "run-stream.v2",
            seq: 2,
            ts: "2026-03-12T03:00:01Z",
            event: "tool.completed",
            run_id: "run-123",
            stage: "tool",
            payload: {
              span_id: "call-1",
              tool: "platform sdk",
              tool_slug: "platform-rag",
              action: "rag.operators.catalog",
              display_name: "List RAG operators",
              summary: "List RAG operators",
              output: { items: [{ operator_id: "web_search" }] },
            },
            diagnostics: [],
          },
          {
            version: "run-stream.v2",
            seq: 3,
            ts: "2026-03-12T03:00:02Z",
            event: "assistant.delta",
            run_id: "run-123",
            stage: "assistant",
            payload: {
              content: "List RAG operators\nFound 12 operators.",
            },
            diagnostics: [],
          },
        ],
      }),
    );

    expect(blocks).toHaveLength(2);
    expect(blocks?.[0].kind).toBe("tool_call");
    expect(blocks?.[0].tool.title).toBe("List RAG operators");
    expect(blocks?.[1].kind).toBe("assistant_text");
    expect(blocks?.[1].text).toBe("List RAG operators\nFound 12 operators.");
  });
});
