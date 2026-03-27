import { act, renderHook, waitFor } from "@testing-library/react";

import { useAgentThreadHistory } from "@/hooks/useAgentThreadHistory";
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

  it("replays architect-worker threads in stable order and hydrates trace blocks for every assistant turn", async () => {
    mockedAdminService.getUserThreads.mockResolvedValue({
      items: [
        {
          id: "thread-1",
          title: "Worker thread",
          updated_at: "2026-03-16T12:45:00Z",
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
            usage_source: "provider_reported",
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
            usage_source: "sdk_reported",
          },
        },
      ],
    } as any);

    mockedAgentService.getRunEvents.mockImplementation(async (runId: string) => {
      if (runId === "run-older") {
        return {
          run_id: runId,
          event_count: 2,
          events: [
            {
              version: "run-stream.v2",
              seq: 1,
              ts: "2026-03-16T12:42:10Z",
              event: "tool.started",
              run_id: runId,
              stage: "tool",
              payload: {
                span_id: "call-older",
                tool: "Artifact Coding Update File Range",
                display_name: "Artifact Coding Update File Range",
                summary: "Artifact Coding Update File Range",
              },
              diagnostics: [],
            },
            {
              version: "run-stream.v2",
              seq: 2,
              ts: "2026-03-16T12:42:20Z",
              event: "tool.completed",
              run_id: runId,
              stage: "tool",
              payload: {
                span_id: "call-older",
                tool: "Artifact Coding Update File Range",
                display_name: "Artifact Coding Update File Range",
                summary: "Artifact Coding Update File Range",
                output: { ok: true },
              },
              diagnostics: [],
            },
          ],
        } as any;
      }

      return {
        run_id: runId,
        event_count: 2,
        events: [
          {
            version: "run-stream.v2",
            seq: 1,
            ts: "2026-03-16T12:44:05Z",
            event: "tool.started",
            run_id: runId,
            stage: "tool",
            payload: {
              span_id: "call-newer",
              tool: "Artifact Coding Read File",
              display_name: "Artifact Coding Read File",
              summary: "Artifact Coding Read File",
            },
            diagnostics: [],
          },
          {
            version: "run-stream.v2",
            seq: 2,
            ts: "2026-03-16T12:44:10Z",
            event: "tool.completed",
            run_id: runId,
            stage: "tool",
            payload: {
              span_id: "call-newer",
              tool: "Artifact Coding Read File",
              display_name: "Artifact Coding Read File",
              summary: "Artifact Coding Read File",
              output: { path: "main.py" },
            },
            diagnostics: [],
          },
        ],
      } as any;
    });

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
      usageSource: "sdk_reported",
    });
    expect(assistantMessages[1].tokenUsage).toEqual({
      inputTokens: 30,
      outputTokens: 12,
      totalTokens: 42,
      usageSource: "provider_reported",
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
});
