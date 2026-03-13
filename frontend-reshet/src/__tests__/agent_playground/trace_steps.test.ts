import { buildExecutionStepsFromRunEvents } from "@/services/run-trace-steps";

describe("playground persisted trace replay", () => {
  it("rebuilds execution steps from persisted recorder-style events", () => {
    const steps = buildExecutionStepsFromRunEvents([
      {
        id: "evt-1",
        sequence: 1,
        timestamp: "2026-03-12T10:00:00Z",
        event: "on_tool_start",
        name: "Search library",
        span_id: "tool-1",
        data: {
          input: { query: "Berakhot 2a" },
          message: "Searching the library",
        },
      },
      {
        id: "evt-2",
        sequence: 2,
        timestamp: "2026-03-12T10:00:01Z",
        event: "on_tool_end",
        name: "Search library",
        span_id: "tool-1",
        data: {
          output: { hits: 3 },
        },
      },
      {
        id: "evt-3",
        sequence: 3,
        timestamp: "2026-03-12T10:00:02Z",
        event: "node_start",
        name: "Planner",
        span_id: "node-1",
        data: {
          input: { question: "Summarize the daf" },
          type: "llm",
        },
      },
      {
        id: "evt-4",
        sequence: 4,
        timestamp: "2026-03-12T10:00:03Z",
        event: "error",
        span_id: "node-1",
        data: {
          error: "Planner failed",
        },
      },
      {
        id: "evt-5",
        sequence: 5,
        timestamp: "2026-03-12T10:00:04Z",
        event: "run_status",
        data: {
          status: "failed",
        },
      },
    ]);

    expect(steps).toHaveLength(2);
    expect(steps[0]).toMatchObject({
      id: "tool-1",
      name: "Search library",
      type: "tool",
      status: "completed",
      input: { query: "Berakhot 2a" },
      output: { hits: 3 },
    });
    expect(steps[1]).toMatchObject({
      id: "node-1",
      name: "Planner",
      type: "node",
      status: "error",
      input: { question: "Summarize the daf" },
      output: { error: "Planner failed" },
    });
    expect(steps[0]?.timestamp.toISOString()).toBe("2026-03-12T10:00:00.000Z");
    expect(steps[1]?.timestamp.toISOString()).toBe("2026-03-12T10:00:02.000Z");
  });

  it("supports persisted v2 tool lifecycle envelopes too", () => {
    const steps = buildExecutionStepsFromRunEvents([
      {
        seq: 1,
        ts: "2026-03-12T10:00:00Z",
        event: "tool.started",
        run_id: "run-1",
        payload: {
          span_id: "call-1",
          tool: "platform sdk",
          display_name: "List sources",
          input: { topic: "Shabbat" },
        },
      },
      {
        seq: 2,
        ts: "2026-03-12T10:00:01Z",
        event: "tool.completed",
        run_id: "run-1",
        payload: {
          span_id: "call-1",
          tool: "platform sdk",
          display_name: "List sources",
          output: { count: 4 },
        },
      },
    ]);

    expect(steps).toHaveLength(1);
    expect(steps[0]).toMatchObject({
      id: "call-1",
      name: "List sources",
      type: "tool",
      status: "completed",
      input: { topic: "Shabbat" },
      output: { count: 4 },
    });
  });
});
