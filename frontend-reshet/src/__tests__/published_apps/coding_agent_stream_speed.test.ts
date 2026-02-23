import { consumeRunStream } from "@/features/apps-builder/workspace/chat/useAppsBuilderChat.stream";
import { publishedAppsService } from "@/services";
import { ReadableStream } from "stream/web";
import { TextDecoder, TextEncoder } from "util";

jest.mock("@/services", () => ({
  publishedAppsService: {
    streamCodingAgentRun: jest.fn(),
  },
}));

function buildSseFrame(payload: Record<string, unknown>): string {
  return `data: ${JSON.stringify(payload)}\n\n`;
}

describe("coding agent stream rendering speed", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (global as { TextDecoder?: typeof TextDecoder }).TextDecoder = TextDecoder;
  });

  it("renders assistant delta chunks without frontend coalescing", async () => {

    const sse = [
      buildSseFrame({
        event: "run.accepted",
        run_id: "run-1",
        app_id: "app-1",
        seq: 1,
        ts: "2026-02-23T10:00:00Z",
        stage: "run",
        payload: { status: "queued" },
        diagnostics: [],
      }),
      ...["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"].map((chunk, index) =>
        buildSseFrame({
          event: "assistant.delta",
          run_id: "run-1",
          app_id: "app-1",
          seq: index + 2,
          ts: "2026-02-23T10:00:00Z",
          stage: "assistant",
          payload: { content: chunk },
          diagnostics: [],
        }),
      ),
      buildSseFrame({
        event: "run.completed",
        run_id: "run-1",
        app_id: "app-1",
        seq: 12,
        ts: "2026-02-23T10:00:01Z",
        stage: "run",
        payload: { status: "completed" },
        diagnostics: [],
      }),
    ].join("");

    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(sse));
        controller.close();
      },
    });
    const response = {
      ok: true,
      status: 200,
      body,
      json: async () => ({}),
    } as unknown as Response;
    (publishedAppsService.streamCodingAgentRun as jest.Mock).mockResolvedValue(response);

    const upsertAssistantTimeline = jest.fn();
    const onError = jest.fn();

    await consumeRunStream({
      appId: "app-1",
      runId: "run-1",
      activeTab: "config",
      activeChatSessionIdRef: { current: "session-1" },
      setIsSending: jest.fn(),
      setIsStopping: jest.fn(),
      setActiveThinkingSummary: jest.fn(),
      isSendingRef: { current: false },
      pendingCancelRef: { current: false },
      intentionalAbortRef: { current: false },
      activeRunIdRef: { current: null },
      lastKnownRunIdRef: { current: null },
      abortReaderRef: { current: null },
      isMountedRef: { current: true },
      seenRunEventKeysRef: { current: new Set<string>() },
      onError,
      onSetCurrentRevisionId: jest.fn(),
      pushTimeline: jest.fn(),
      upsertAssistantTimeline,
      upsertToolTimeline: jest.fn(),
      finalizeRunningTools: jest.fn(),
      attachCheckpointToLastUser: jest.fn(),
      refreshStateSilently: jest.fn(async () => undefined),
      ensureDraftDevSession: jest.fn(async () => undefined),
      loadChatSessions: jest.fn(async () => []),
      refreshQueue: jest.fn(async () => undefined),
    });

    const nonEmptyErrors = onError.mock.calls
      .map((call) => call[0])
      .filter((value) => typeof value === "string" && value.trim().length > 0);
    expect(nonEmptyErrors).toHaveLength(0);
    expect(upsertAssistantTimeline).toHaveBeenCalled();
    expect(upsertAssistantTimeline.mock.calls.length).toBeGreaterThanOrEqual(10);
    const latestText = String(upsertAssistantTimeline.mock.calls.at(-1)?.[1] || "");
    expect(latestText).toBe("ABCDEFGHIJ");
  });
});
