import { act, renderHook, waitFor } from "@testing-library/react";

import { mapTurnsToMessages, useAgentThreadHistory } from "@/hooks/useAgentThreadHistory";
import { adminService, agentService } from "@/services";

jest.mock("@/services", () => ({
  adminService: {
    getUserThreads: jest.fn(),
    getThread: jest.fn(),
  },
  agentService: {
    getRunEvents: jest.fn(),
  },
}));

const mockedAdminService = adminService as jest.Mocked<typeof adminService>;
const mockedAgentService = agentService as jest.Mocked<typeof agentService>;

describe("useAgentThreadHistory", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("requests only the current user's threads for the selected agent", async () => {
    mockedAdminService.getUserThreads.mockResolvedValue({
      items: [
        {
          id: "thread-1",
          title: "Agent 1 thread",
          updated_at: "2026-04-05T09:00:00Z",
          agent_id: "agent-1",
        },
      ],
      total: 1,
      page: 1,
      pages: 1,
    } as any);

    const { result } = renderHook(() => useAgentThreadHistory("user-1", "agent-1"));

    await waitFor(() => {
      expect(result.current.history).toHaveLength(1);
    });

    expect(mockedAdminService.getUserThreads).toHaveBeenCalledWith("user-1", 1, 50, "", {
      agentId: "agent-1",
    });
    expect(result.current.history[0]?.agentId).toBe("agent-1");
  });

  it("replays architect-worker threads in stable order and hydrates trace blocks for every assistant turn", async () => {
    mockedAdminService.getUserThreads.mockResolvedValue({
      items: [
        {
          id: "thread-1",
          title: "Worker thread",
          updated_at: "2026-03-16T12:45:00Z",
          agent_id: "agent-1",
        },
      ],
      total: 1,
      page: 1,
      pages: 1,
    } as any);

    mockedAdminService.getThread.mockResolvedValue({
      id: "thread-1",
      title: "Worker thread",
      agent_id: "agent-1",
      turns: [
        {
          id: "turn-newer",
          run_id: "run-newer",
          turn_index: 0,
          user_input_text: "Python",
          assistant_output_text:
            "What is your favorite programming language? Please reply via the worker interactive channel — after you reply I'll update the draft to include it and return a short demo output. I will not persist the artifact yet.",
          created_at: "2026-03-16T12:44:01Z",
          completed_at: "2026-03-16T12:44:50Z",
          run_usage: {
            input_tokens: 30,
            output_tokens: 12,
            total_tokens: 42,
            source: "exact",
          },
          metadata: {
            response_blocks: [
              {
                id: "call-newer",
                kind: "tool_call",
                runId: "run-newer",
                seq: 1,
                status: "complete",
                tool: {
                  toolCallId: "call-newer",
                  toolName: "Artifact Coding Read File",
                  title: "Artifact Coding Read File",
                },
              },
              {
                id: "assistant-newer",
                kind: "assistant_text",
                runId: "run-newer",
                seq: 2,
                status: "complete",
                text: "What is your favorite programming language? Please reply via the worker interactive channel — after you reply I'll update the draft to include it and return a short demo output. I will not persist the artifact yet.",
              },
            ],
          },
        },
        {
          id: "turn-older",
          run_id: "run-older",
          turn_index: 0,
          user_input_text:
            "Create or update the draft tool_impl to implement a small interactive script (main.py)...",
          assistant_output_text: "What is your favorite programming language?",
          created_at: "2026-03-16T12:42:06Z",
          completed_at: "2026-03-16T12:43:44Z",
          run_usage: {
            input_tokens: 18,
            output_tokens: 6,
            total_tokens: 24,
            source: "exact",
          },
          metadata: {
            response_blocks: [
              {
                id: "call-older",
                kind: "tool_call",
                runId: "run-older",
                seq: 1,
                status: "complete",
                tool: {
                  toolCallId: "call-older",
                  toolName: "Artifact Coding Update File Range",
                  title: "Artifact Coding Update File Range",
                },
              },
              {
                id: "assistant-older",
                kind: "assistant_text",
                runId: "run-older",
                seq: 2,
                status: "complete",
                text: "What is your favorite programming language?",
              },
            ],
          },
        },
      ],
    } as any);

    const { result } = renderHook(() => useAgentThreadHistory("user-1"));

    await waitFor(() => {
      expect(result.current.history).toHaveLength(1);
    });

    let loaded: Awaited<ReturnType<typeof result.current.loadThreadMessages>> = null;
    await act(async () => {
      loaded = await result.current.loadThreadMessages(result.current.history[0]);
    });

    await waitFor(() => {
      expect(loaded?.messages).toHaveLength(4);
    });

    const messages = loaded!.messages;
    expect(messages.map((message) => message.content)).toEqual([
      "Create or update the draft tool_impl to implement a small interactive script (main.py)...",
      "What is your favorite programming language?",
      "Python",
      "Please reply via the worker interactive channel — after you reply I'll update the draft to include it and return a short demo output. I will not persist the artifact yet.",
    ]);

    const assistantMessages = messages.filter((message) => message.role === "assistant");
    expect(assistantMessages).toHaveLength(2);
    expect(assistantMessages[0].runId).toBe("run-older");
    expect(assistantMessages[1].runId).toBe("run-newer");
    expect(assistantMessages[0].tokenUsage).toEqual({
      inputTokens: 18,
      outputTokens: 6,
      totalTokens: 24,
      usageSource: "exact",
    });
    expect(assistantMessages[1].tokenUsage).toEqual({
      inputTokens: 30,
      outputTokens: 12,
      totalTokens: 42,
      usageSource: "exact",
    });
    expect(assistantMessages[0].responseBlocks?.some((block) => block.kind === "tool_call")).toBe(true);
    expect(assistantMessages[1].responseBlocks?.some((block) => block.kind === "tool_call")).toBe(true);
    expect(
      assistantMessages[1].responseBlocks?.filter((block) => block.kind === "assistant_text").length,
    ).toBe(1);
    expect(
      assistantMessages[1].responseBlocks?.find((block) => block.kind === "assistant_text" && block.text.includes("What is your favorite programming language?")),
    ).toBeTruthy();
  });

  it("falls back to persisted assistant text for legacy turns without response blocks", async () => {
    const messages = await mapTurnsToMessages("thread-1", [
      {
        id: "turn-1",
        run_id: "run-aborted",
        turn_index: 0,
        user_input_text: "Inspect the file",
        assistant_output_text: "The file was inspected.",
        created_at: "2026-03-29T15:00:00Z",
        completed_at: "2026-03-29T15:00:03Z",
      },
    ]);

    expect(messages).toHaveLength(2);
    expect(messages[1].role).toBe("assistant");
    expect(messages[1].content).toBe("The file was inspected.");
    expect(messages[1].runId).toBe("run-aborted");
    expect(messages[1].responseBlocks).toMatchObject([
      {
        kind: "assistant_text",
        text: "The file was inspected.",
      },
    ]);
  });

  it("uses persisted assistant_output_text as the only legacy fallback when response blocks are missing", async () => {
    const messages = await mapTurnsToMessages("thread-1", [
      {
        id: "turn-1",
        run_id: "run-markdown",
        turn_index: 0,
        user_input_text: "Give me bullets",
        assistant_output_text: "Title item one item two",
        created_at: "2026-04-12T09:00:00Z",
        completed_at: "2026-04-12T09:00:03Z",
      },
    ]);

    expect(messages).toHaveLength(2);
    expect(messages[1].role).toBe("assistant");
    expect(messages[1].content).toBe("Title item one item two");
    expect(messages[1].responseBlocks).toMatchObject([
      {
        kind: "assistant_text",
        text: "Title item one item two",
      },
    ]);
  });
});
