import { buildTimelineFromChatHistory } from "@/features/apps-builder/workspace/chat/useAppsBuilderChat.history";

describe("buildTimelineFromChatHistory", () => {
  it("injects persisted tool events before assistant message for the same run", () => {
    const detail = {
      session: {
        id: "chat-1",
        title: "History",
        created_at: "2026-02-25T10:00:00Z",
        updated_at: "2026-02-25T10:00:00Z",
        last_message_at: "2026-02-25T10:00:00Z",
      },
      messages: [
        {
          id: "m1",
          run_id: "run-1",
          role: "user" as const,
          content: "Please update the main file",
          created_at: "2026-02-25T10:00:00Z",
        },
        {
          id: "m2",
          run_id: "run-1",
          role: "assistant" as const,
          content: "Updated.",
          created_at: "2026-02-25T10:00:02Z",
        },
      ],
      run_events: [
        {
          run_id: "run-1",
          event: "tool.started" as const,
          stage: "tool",
          payload: {
            tool: "write_file",
            span_id: "call-1",
            input: { path: "src/main.tsx" },
          },
          diagnostics: [],
          ts: "2026-02-25T10:00:01Z",
        },
        {
          run_id: "run-1",
          event: "tool.completed" as const,
          stage: "tool",
          payload: {
            tool: "write_file",
            span_id: "call-1",
            output: { path: "src/main.tsx" },
          },
          diagnostics: [],
          ts: "2026-02-25T10:00:01Z",
        },
      ],
    };

    const timeline = buildTimelineFromChatHistory(detail);

    expect(timeline.map((item) => item.kind)).toEqual(["user", "tool", "assistant"]);
    expect(timeline[1].toolStatus).toBe("completed");
    expect(timeline[1].toolName).toBe("write_file");
    expect(timeline[1].toolPath).toBe("src/main.tsx");
    expect(timeline[2].description).toBe("Updated.");
  });

  it("settles historical tools when events are missing span_id", () => {
    const detail = {
      session: {
        id: "chat-1",
        title: "History",
        created_at: "2026-02-25T10:00:00Z",
        updated_at: "2026-02-25T10:00:00Z",
        last_message_at: "2026-02-25T10:00:00Z",
      },
      messages: [
        {
          id: "m1",
          run_id: "run-1",
          role: "assistant" as const,
          content: "Done.",
          created_at: "2026-02-25T10:00:02Z",
        },
      ],
      run_events: [
        {
          run_id: "run-1",
          event: "tool.started" as const,
          stage: "tool",
          payload: { tool: "read_file", input: { path: "src/a.ts" } },
          diagnostics: [],
          ts: "2026-02-25T10:00:01Z",
        },
        {
          run_id: "run-1",
          event: "tool.completed" as const,
          stage: "tool",
          payload: { tool: "read_file", output: { path: "src/a.ts" } },
          diagnostics: [],
          ts: "2026-02-25T10:00:01Z",
        },
      ],
    };

    const timeline = buildTimelineFromChatHistory(detail);
    const toolRows = timeline.filter((item) => item.kind === "tool");

    expect(toolRows).toHaveLength(1);
    expect(toolRows[0].toolStatus).toBe("completed");
    expect(toolRows[0].tone).toBe("success");
  });

  it("keeps multiple terminal tool events when span_id is missing", () => {
    const detail = {
      session: {
        id: "chat-1",
        title: "History",
        created_at: "2026-02-25T10:00:00Z",
        updated_at: "2026-02-25T10:00:00Z",
        last_message_at: "2026-02-25T10:00:00Z",
      },
      messages: [
        {
          id: "m1",
          run_id: "run-1",
          role: "assistant" as const,
          content: "Done.",
          created_at: "2026-02-25T10:00:02Z",
        },
      ],
      run_events: [
        {
          run_id: "run-1",
          event: "tool.completed" as const,
          stage: "tool",
          payload: { tool: "glob", output: { path: "index.html" } },
          diagnostics: [],
          ts: "2026-02-25T10:00:01Z",
        },
        {
          run_id: "run-1",
          event: "tool.completed" as const,
          stage: "tool",
          payload: { tool: "glob", output: { path: "src/main.tsx" } },
          diagnostics: [],
          ts: "2026-02-25T10:00:02Z",
        },
      ],
    };

    const timeline = buildTimelineFromChatHistory(detail);
    const toolRows = timeline.filter((item) => item.kind === "tool");

    expect(toolRows).toHaveLength(2);
    expect(toolRows[0].toolStatus).toBe("completed");
    expect(toolRows[1].toolStatus).toBe("completed");
  });
});
