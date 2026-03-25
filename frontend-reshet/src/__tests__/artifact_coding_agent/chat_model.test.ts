import {
  buildArtifactCodingTimeline,
  finalizeRunningToolItems,
  finalizeStreamingAssistantSegment,
  type TimelineItem,
} from "@/features/artifact-coding/chat-model";

describe("finalizeRunningToolItems", () => {
  it("finalizes only running tool rows for the targeted run", () => {
    const timeline: TimelineItem[] = [
      {
        id: "tool-1",
        kind: "tool",
        title: "Read file",
        toolCallId: "call-1",
        toolStatus: "running",
        runId: "run-1",
      },
      {
        id: "tool-2",
        kind: "tool",
        title: "Search code",
        toolCallId: "call-2",
        toolStatus: "running",
        runId: "run-2",
      },
      {
        id: "assistant-1",
        kind: "assistant",
        title: "Assistant",
        description: "Done",
        runId: "run-1",
      },
    ];

    const next = finalizeRunningToolItems(timeline, "completed", "run-1");

    expect(next[0].toolStatus).toBe("completed");
    expect(next[0].tone).toBe("success");
    expect(next[1].toolStatus).toBe("running");
    expect(next[2]).toEqual(timeline[2]);
  });

  it("marks running tools as failed on terminal failure", () => {
    const timeline: TimelineItem[] = [
      {
        id: "tool-1",
        kind: "tool",
        title: "Edit file",
        toolCallId: "call-1",
        toolStatus: "running",
        runId: "run-1",
      },
    ];

    const next = finalizeRunningToolItems(timeline, "failed", "run-1");

    expect(next[0].toolStatus).toBe("failed");
    expect(next[0].tone).toBe("error");
  });
});

describe("finalizeStreamingAssistantSegment", () => {
  it("clears only the targeted streaming assistant marker", () => {
    const timeline: TimelineItem[] = [
      {
        id: "assistant-1",
        kind: "assistant",
        title: "Assistant",
        description: "Inspecting",
        assistantStreamId: "stream-1",
        runId: "run-1",
      },
      {
        id: "assistant-2",
        kind: "assistant",
        title: "Assistant",
        description: "Other",
        assistantStreamId: "stream-2",
        runId: "run-1",
      },
    ];

    const next = finalizeStreamingAssistantSegment(timeline, "stream-1");

    expect(next[0].assistantStreamId).toBeUndefined();
    expect(next[1].assistantStreamId).toBe("stream-2");
  });
});

describe("buildArtifactCodingTimeline", () => {
  it("rebuilds assistant and tool items in event order for a run", () => {
    const timeline = buildArtifactCodingTimeline(
      [
        {
          id: "user-1",
          run_id: "run-1",
          role: "user",
          content: "Do the thing",
        },
        {
          id: "assistant-1",
          run_id: "run-1",
          role: "assistant",
          content: "Final answer",
        },
      ],
      [
        {
          run_id: "run-1",
          event: "assistant.delta",
          stage: "assistant",
          payload: { content: "I will inspect. " },
        },
        {
          run_id: "run-1",
          event: "tool.started",
          stage: "tool",
          payload: { span_id: "tool-1", tool: "artifact-coding-get-context", summary: "Get context" },
        },
        {
          run_id: "run-1",
          event: "tool.completed",
          stage: "tool",
          payload: { span_id: "tool-1", tool: "artifact-coding-get-context", output: { summary: "Got context" } },
        },
        {
          run_id: "run-1",
          event: "assistant.delta",
          stage: "assistant",
          payload: { content: "Now I can proceed." },
        },
      ],
    );

    expect(timeline.map((item) => item.kind)).toEqual(["user", "assistant", "tool", "assistant"]);
    expect(timeline[1].description).toBe("I will inspect.");
    expect(timeline[2].kind).toBe("tool");
    expect(timeline[3].description).toBe("Now I can proceed.");
  });
});
