import { buildTimelineFromChatHistory } from "@/features/apps-builder/workspace/chat/useAppsBuilderChat.history";

describe("buildTimelineFromChatHistory", () => {
  it("injects tool parts before the assistant message", () => {
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
          role: "user" as const,
          content: "Please update the main file",
          parts: [{ id: "m1-p1", type: "text", text: "Please update the main file" }],
          created_at: "2026-02-25T10:00:00Z",
        },
        {
          id: "m2",
          role: "assistant" as const,
          content: "Updated.",
          parts: [
            {
              id: "tool-1",
              type: "tool",
              tool: "write_file",
              call_id: "call-1",
              state: {
                status: "completed",
                input: { path: "src/main.tsx" },
                output: { path: "src/main.tsx" },
              },
            },
            { id: "m2-p2", type: "text", text: "Updated." },
          ],
          created_at: "2026-02-25T10:00:02Z",
        },
      ],
      paging: { has_more: false, next_before_message_id: null },
    };

    const timeline = buildTimelineFromChatHistory(detail);

    expect(timeline.map((item) => item.kind)).toEqual(["user", "tool", "assistant"]);
    expect(timeline[1].toolStatus).toBe("completed");
    expect(timeline[1].toolName).toBe("write_file");
    expect(timeline[1].toolPath).toBe("src/main.tsx");
    expect(timeline[2].description).toBe("Updated.");
    expect(timeline[2].assistantStreamId).toBe("m2");
  });

  it("does not treat command output banners as tool file paths in history", () => {
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
          role: "assistant" as const,
          content: "Done.",
          parts: [
            {
              id: "tool-1",
              type: "tool",
              tool: "command",
              call_id: "call-1",
              state: {
                status: "completed",
                output: "talmudpedia-published-app-template@0.0.1",
              },
            },
            { id: "m1-p2", type: "text", text: "Done." },
          ],
          created_at: "2026-02-25T10:00:02Z",
        },
      ],
      paging: { has_more: false, next_before_message_id: null },
    };

    const timeline = buildTimelineFromChatHistory(detail);
    const toolRows = timeline.filter((item) => item.kind === "tool");

    expect(toolRows).toHaveLength(1);
    expect(toolRows[0].toolName).toBe("command");
    expect(toolRows[0].toolPath).toBeUndefined();
  });

  it("keeps command title semantics from run to ran in restored history", () => {
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
          role: "assistant" as const,
          content: "Done.",
          parts: [
            {
              id: "tool-1",
              type: "tool",
              tool: "bash",
              call_id: "call-1",
              state: {
                status: "completed",
                input: { description: "Run TypeScript type checking", command: "npm run typecheck" },
                output: "ok",
              },
            },
            { id: "m1-p2", type: "text", text: "Done." },
          ],
          created_at: "2026-02-25T10:00:02Z",
        },
      ],
      paging: { has_more: false, next_before_message_id: null },
    };

    const timeline = buildTimelineFromChatHistory(detail);
    const toolRows = timeline.filter((item) => item.kind === "tool");

    expect(toolRows).toHaveLength(1);
    expect(toolRows[0].title).toBe("Ran TypeScript type checking");
  });
});
