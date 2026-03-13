import { act, renderHook, waitFor } from "@testing-library/react";

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
    getRunEvents: jest.fn(),
    streamAgent: jest.fn(),
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
});
