import { act, renderHook, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

import type { ChatMessage } from "@/components/layout/useChatController";
import { useAgentRunController } from "@/hooks/useAgentRunController";
import { agentService } from "@/services/agent";

jest.mock("nanoid", () => ({
  nanoid: () => "mock-id",
}));

const mockLoadThreadMessages = jest.fn();
const mockRefreshHistory = jest.fn();
const mockUpsertHistoryItem = jest.fn();

jest.mock("@/services/agent", () => ({
  agentService: {
    cancelRun: jest.fn(),
    getRunEvents: jest.fn(),
    getRunTree: jest.fn(),
    streamAgent: jest.fn(),
    uploadAgentAttachments: jest.fn(),
  },
}));

jest.mock("@/lib/store/useAuthStore", () => ({
  useAuthStore: (selector: (state: any) => any) =>
    selector({ user: { id: "user-1", tenant_id: "tenant-1" } }),
}));

jest.mock("@/hooks/useAgentThreadHistory", () => ({
  useAgentThreadHistory: () => ({
    history: [],
    historyLoading: false,
    refreshHistory: mockRefreshHistory,
    loadThreadMessages: mockLoadThreadMessages,
    upsertHistoryItem: mockUpsertHistoryItem,
  }),
}));

const mockedAgentService = agentService as jest.Mocked<typeof agentService>;

beforeAll(() => {
  Object.assign(globalThis, {
    TextDecoder,
  });
});

const assistantMessage: ChatMessage = {
  id: "assistant-1",
  role: "assistant",
  content: "Saved answer",
  createdAt: new Date("2026-03-12T10:00:00Z"),
  runId: "run-1",
};

describe("useAgentRunController trace inspection", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockedAgentService.getRunEvents.mockResolvedValue({
      run_id: "run-1",
      event_count: 2,
      events: [
        {
          sequence: 1,
          timestamp: "2026-03-12T10:00:00Z",
          event: "on_tool_start",
          name: "Search library",
          span_id: "tool-1",
          data: {
            input: { query: "Berakhot 2a" },
          },
        },
        {
          sequence: 2,
          timestamp: "2026-03-12T10:00:01Z",
          event: "on_tool_end",
          name: "Search library",
          span_id: "tool-1",
          data: {
            output: { hits: 2 },
          },
        },
      ],
    });
    mockLoadThreadMessages.mockResolvedValue({
      id: "thread-2",
      threadId: "thread-2",
      title: "Thread 2",
      timestamp: Date.now(),
      messages: [],
    });
  });

  it("loads and swaps inspected execution steps from persisted runs", async () => {
    const { result } = renderHook(({ agentId }) => useAgentRunController(agentId), {
      initialProps: { agentId: "agent-1" as string | undefined },
    });

    await act(async () => {
      await result.current.handleLoadTrace(assistantMessage);
    });

    await waitFor(() => {
      expect(result.current.executionSteps).toHaveLength(1);
    });

    expect(result.current.executionSteps[0]).toMatchObject({
      id: "tool-1",
      name: "Search library",
      status: "completed",
    });

    mockedAgentService.getRunEvents.mockResolvedValueOnce({
      run_id: "run-2",
      event_count: 2,
      events: [
        {
          sequence: 1,
          timestamp: "2026-03-12T11:00:00Z",
          event: "node_start",
          name: "Planner",
          span_id: "node-1",
          data: { input: { prompt: "Summarize" } },
        },
        {
          sequence: 2,
          timestamp: "2026-03-12T11:00:01Z",
          event: "node_end",
          name: "Planner",
          span_id: "node-1",
          data: { output: { content_length: 120 } },
        },
      ],
    });

    await act(async () => {
      await result.current.handleLoadTrace({
        ...assistantMessage,
        id: "assistant-2",
        runId: "run-2",
      });
    });

    await waitFor(() => {
      expect(result.current.executionSteps[0]?.id).toBe("node-1");
    });
  });

  it("clears inspected execution steps on new thread, thread load, and agent switch", async () => {
    const { result, rerender } = renderHook(({ agentId }) => useAgentRunController(agentId), {
      initialProps: { agentId: "agent-1" as string | undefined },
    });

    await act(async () => {
      await result.current.handleLoadTrace(assistantMessage);
    });

    await waitFor(() => {
      expect(result.current.executionSteps).toHaveLength(1);
    });

    act(() => {
      result.current.startNewChat();
    });
    expect(result.current.executionSteps).toHaveLength(0);

    await act(async () => {
      await result.current.handleLoadTrace(assistantMessage);
    });
    await waitFor(() => {
      expect(result.current.executionSteps).toHaveLength(1);
    });

    await act(async () => {
      await result.current.loadHistoryChat({
        id: "thread-2",
        threadId: "thread-2",
        title: "Thread 2",
        timestamp: Date.now(),
        messages: [],
      });
    });
    expect(result.current.executionSteps).toHaveLength(0);

    await act(async () => {
      await result.current.handleLoadTrace(assistantMessage);
    });
    await waitFor(() => {
      expect(result.current.executionSteps).toHaveLength(1);
    });

    rerender({ agentId: "agent-2" as string | undefined });

    await waitFor(() => {
      expect(result.current.executionSteps).toHaveLength(0);
    });
  });

  it("builds live execution steps from streamed workflow publication events", async () => {
    const encoder = new TextEncoder();
    const streamPayload = [
      'data: {"event":"node_start","run_id":"run-live","span_id":"agent_1","name":"Agent","data":{"type":"agent","input":{"model":"model-1"}}}\n\n',
      'data: {"event":"node_end","run_id":"run-live","span_id":"agent_1","name":"Agent","data":{"type":"agent","output":{"content_length":26}}}\n\n',
      'data: {"event":"workflow.node_output_published","run_id":"run-live","span_id":"agent_1","data":{"node_id":"agent_1","node_name":"Reply Agent","published_output":{"output_text":"hello world"}}}\n\n',
      'data: {"event":"node_start","run_id":"run-live","span_id":"end","name":"End","data":{"type":"end","input":{"has_schema":true}}}\n\n',
      'data: {"event":"workflow.end_materialized","run_id":"run-live","span_id":"end","data":{"node_id":"end","node_name":"End","final_output":{"response":"hello world"}}}\n\n',
      'data: {"event":"node_end","run_id":"run-live","span_id":"end","name":"End","data":{"type":"end","output":{"has_output":true}}}\n\n',
      'data: {"event":"assistant.delta","run_id":"run-live","payload":{"content":"hello world"}}\n\n',
      'data: {"event":"run.completed","run_id":"run-live","payload":{"status":"completed"}}\n\n',
      "data: [DONE]\n\n",
    ].join("");

    mockedAgentService.streamAgent.mockResolvedValue({
      headers: {
        get: (name: string) => (name === "X-Thread-ID" ? "thread-live" : null),
      },
      body: {
        getReader: () => {
          let consumed = false;
          return {
            read: async () => {
              if (consumed) {
                return { done: true, value: undefined };
              }
              consumed = true;
              return { done: false, value: encoder.encode(streamPayload) };
            },
          };
        },
      },
    } as unknown as Response);

    const { result } = renderHook(({ agentId }) => useAgentRunController(agentId), {
      initialProps: { agentId: "agent-1" as string | undefined },
    });

    await act(async () => {
      await result.current.handleSubmit({ text: "hello", files: [] });
    });

    await waitFor(() => {
      expect(result.current.executionSteps).toHaveLength(2);
    });

    expect(result.current.executionSteps[0]).toMatchObject({
      id: "agent_1",
      nodeId: "agent_1",
      name: "Reply Agent",
      output: { output_text: "hello world" },
    });
    expect(result.current.executionSteps[1]).toMatchObject({
      id: "end",
      nodeId: "end",
      name: "End",
      output: { response: "hello world" },
    });
  });

  it("keeps live tool steps attached to the owning node via source_node_id", async () => {
    const encoder = new TextEncoder();
    const streamPayload = [
      'data: {"event":"tool.started","run_id":"run-live","payload":{"span_id":"call-1","source_node_id":"agent_1","tool":"platform sdk","display_name":"List sources","input":{"topic":"Shabbat"}}}\n\n',
      'data: {"event":"tool.completed","run_id":"run-live","payload":{"span_id":"call-1","source_node_id":"agent_1","tool":"platform sdk","display_name":"List sources","output":{"count":4}}}\n\n',
      'data: {"event":"run.completed","run_id":"run-live","payload":{"status":"completed"}}\n\n',
      "data: [DONE]\n\n",
    ].join("");

    mockedAgentService.streamAgent.mockResolvedValue({
      headers: {
        get: () => null,
      },
      body: {
        getReader: () => {
          let consumed = false;
          return {
            read: async () => {
              if (consumed) {
                return { done: true, value: undefined };
              }
              consumed = true;
              return { done: false, value: encoder.encode(streamPayload) };
            },
          };
        },
      },
    } as unknown as Response);

    const { result } = renderHook(({ agentId }) => useAgentRunController(agentId), {
      initialProps: { agentId: "agent-1" as string | undefined },
    });

    await act(async () => {
      await result.current.handleSubmit({ text: "hello", files: [] });
    });

    await waitFor(() => {
      expect(result.current.executionSteps).toHaveLength(1);
    });

    expect(result.current.executionSteps[0]).toMatchObject({
      id: "call-1",
      nodeId: "agent_1",
      name: "List sources",
      type: "tool",
      status: "completed",
      input: { topic: "Shabbat" },
      output: { count: 4 },
    });
  });

  it("passes seeded state through streamAgent submissions", async () => {
    const encoder = new TextEncoder();
    mockedAgentService.streamAgent.mockResolvedValue({
      headers: {
        get: () => null,
      },
      body: {
        getReader: () => {
          let consumed = false;
          return {
            read: async () => {
              if (consumed) return { done: true, value: undefined };
              consumed = true;
              return {
                done: false,
                value: encoder.encode('data: {"event":"run.completed","run_id":"run-state","payload":{"status":"completed"}}\n\ndata: [DONE]\n\n'),
              };
            },
          };
        },
      },
    } as unknown as Response);

    const { result } = renderHook(({ agentId }) => useAgentRunController(agentId), {
      initialProps: { agentId: "agent-1" as string | undefined },
    });

    await act(async () => {
      await result.current.handleSubmit({
        text: "",
        files: [],
        state: { customer_id: "cust-1", flag: true },
      });
    });

    await waitFor(() => {
      expect(mockedAgentService.streamAgent).toHaveBeenCalledWith(
        "agent-1",
        expect.objectContaining({
          state: { customer_id: "cust-1", flag: true },
        }),
        "debug",
      );
    });
  });

  it("finalizes live tool steps when the run is cancelled before tool completion", async () => {
    const encoder = new TextEncoder();
    const streamPayload = [
      'data: {"event":"tool.started","run_id":"run-live","payload":{"span_id":"call-1","source_node_id":"agent_1","tool":"platform sdk","display_name":"List sources","input":{"topic":"Shabbat"}}}\n\n',
      'data: {"event":"run.cancelled","run_id":"run-live","payload":{"status":"cancelled"}}\n\n',
      "data: [DONE]\n\n",
    ].join("");

    mockedAgentService.streamAgent.mockResolvedValue({
      headers: {
        get: () => null,
      },
      body: {
        getReader: () => {
          let consumed = false;
          return {
            read: async () => {
              if (consumed) {
                return { done: true, value: undefined };
              }
              consumed = true;
              return { done: false, value: encoder.encode(streamPayload) };
            },
          };
        },
      },
    } as unknown as Response);

    const { result } = renderHook(({ agentId }) => useAgentRunController(agentId), {
      initialProps: { agentId: "agent-1" as string | undefined },
    });

    await act(async () => {
      await result.current.handleSubmit({ text: "hello", files: [] });
    });

    await waitFor(() => {
      expect(result.current.executionSteps).toHaveLength(1);
    });

    expect(result.current.executionSteps[0]).toMatchObject({
      id: "call-1",
      nodeId: "agent_1",
      name: "List sources",
      type: "tool",
      status: "error",
      input: { topic: "Shabbat" },
      output: { error: "Run cancelled" },
    });
  });

  it("sends default architect_mode for platform-architect runs", async () => {
    const encoder = new TextEncoder();
    mockedAgentService.streamAgent.mockResolvedValue({
      headers: {
        get: () => null,
      },
      body: {
        getReader: () => {
          let consumed = false;
          return {
            read: async () => {
              if (consumed) return { done: true, value: undefined };
              consumed = true;
              return {
                done: false,
                value: encoder.encode('data: {"event":"run.completed","run_id":"run-architect","payload":{"status":"completed"}}\n\ndata: [DONE]\n\n'),
              };
            },
          };
        },
      },
    } as unknown as Response);

    const { result } = renderHook(
      ({ agentId, agentSlug }) => useAgentRunController(agentId, undefined, agentSlug),
      {
        initialProps: {
          agentId: "agent-architect" as string | undefined,
          agentSlug: "platform-architect" as string | undefined,
        },
      },
    );

    await act(async () => {
      await result.current.handleSubmit({ text: "build me an app", files: [] });
    });

    await waitFor(() => {
      expect(mockedAgentService.streamAgent).toHaveBeenCalledWith(
        "agent-architect",
        expect.objectContaining({
          context: { architect_mode: "default" },
        }),
        "debug",
      );
    });
  });

  it("stops the immutable root run even if later events carry another run_id", async () => {
    const encoder = new TextEncoder();
    let releaseSecondRead: (() => void) | null = null;
    const secondRead = new Promise<void>((resolve) => {
      releaseSecondRead = resolve;
    });

    mockedAgentService.cancelRun.mockResolvedValue({
      run_id: "run-root",
      status: "cancelled",
      thread_id: "thread-root",
    });
    mockedAgentService.streamAgent.mockResolvedValue({
      headers: {
        get: (name: string) => {
          if (name === "X-Run-ID") return "run-root";
          if (name === "X-Thread-ID") return "thread-root";
          return null;
        },
      },
      body: {
        getReader: () => {
          let index = 0;
          return {
            read: async () => {
              index += 1;
              if (index === 1) {
                return {
                  done: false,
                  value: encoder.encode(
                    'data: {"event":"run.accepted","run_id":"run-root","payload":{"status":"running"}}\n\n' +
                    'data: {"event":"tool.started","run_id":"run-child","payload":{"span_id":"call-1","source_node_id":"agent_1","tool":"delegate","display_name":"Delegate"}}\n\n'
                  ),
                };
              }
              if (index === 2) {
                await secondRead;
                return { done: true, value: undefined };
              }
              return { done: true, value: undefined };
            },
          };
        },
      },
    } as unknown as Response);

    const { result } = renderHook(({ agentId }) => useAgentRunController(agentId), {
      initialProps: { agentId: "agent-1" as string | undefined },
    });

    await act(async () => {
      void result.current.handleSubmit({ text: "hello", files: [] });
    });

    await waitFor(() => {
      expect(result.current.currentRunId).toBe("run-root");
    });

    await waitFor(() => {
      expect(result.current.currentResponseBlocks).toHaveLength(1);
    });

    act(() => {
      result.current.handleStop();
    });

    await waitFor(() => {
      expect(mockedAgentService.cancelRun).toHaveBeenCalledWith("run-root", {
        assistantOutputText: undefined,
      });
    });

    expect(result.current.currentRunStatus).toBe("cancelled");
    expect(result.current.executionSteps[0]).toMatchObject({
      id: "call-1",
      status: "error",
      output: { error: "Run cancelled" },
    });

    releaseSecondRead?.();

    await waitFor(() => {
      const assistantMessages = result.current.messages.filter((message) => message.role === "assistant");
      expect(assistantMessages.length).toBeLessThanOrEqual(1);
      if (assistantMessages[0]?.responseBlocks) {
        expect(assistantMessages[0].responseBlocks).toMatchObject([
          { kind: "tool_call", status: "complete" },
        ]);
      }
    });
  });
});
