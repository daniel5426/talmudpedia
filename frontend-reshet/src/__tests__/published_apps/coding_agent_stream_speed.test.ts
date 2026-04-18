import { consumeSessionStream } from "@/features/apps-builder/workspace/chat/useAppsBuilderChat.stream";
import { publishedAppsService } from "@/services";
import { ReadableStream } from "stream/web";
import { TextDecoder, TextEncoder } from "util";

jest.mock("@/services", () => ({
  publishedAppsService: {
    streamCodingAgentChatSession: jest.fn(),
  },
}));

function buildSseFrame(payload: Record<string, unknown>): string {
  return `data: ${JSON.stringify(payload)}\n\n`;
}

describe("coding agent session stream rendering", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (global as { TextDecoder?: typeof TextDecoder }).TextDecoder = TextDecoder;
  });

  it("renders assistant delta chunks without coalescing away updates", async () => {
    const sse = [
      buildSseFrame({ event: "session.connected", session_id: "session-1", payload: {} }),
      buildSseFrame({
        event: "message.updated",
        session_id: "session-1",
        payload: { info: { id: "assistant-1", role: "assistant" } },
      }),
      ...["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"].map((chunk) => buildSseFrame({
        event: "message.part.updated",
        session_id: "session-1",
        payload: {
          delta: chunk,
          part: {
            id: `part-${chunk}`,
            messageID: "assistant-1",
            type: "text",
          },
        },
      })),
      buildSseFrame({ event: "session.idle", session_id: "session-1", payload: {} }),
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
      headers: new Headers({ "content-type": "text/event-stream" }),
      json: async () => ({}),
    } as unknown as Response;
    (publishedAppsService.streamCodingAgentChatSession as jest.Mock).mockResolvedValue(response);

    const onUpsertAssistant = jest.fn();
    const onError = jest.fn();

    const attachmentIdRef = { current: 1 };
    const intentionalAbortRef = { current: false };
    await consumeSessionStream({
      appId: "app-1",
      sessionId: "session-1",
      streamAttachmentId: 1,
      getCurrentStreamAttachmentId: () => attachmentIdRef.current,
      abortReaderRef: { current: null },
      intentionalAbortRef,
      isMountedRef: { current: true },
      onError,
      onSetSending: jest.fn(),
      onSetStopping: jest.fn(),
      onSetThinkingSummary: jest.fn(),
      onUpsertAssistant,
      onUpsertTool: jest.fn(),
      onFinalizeRunningTools: jest.fn(),
      onPermissionUpdated: jest.fn(),
      onPermissionResolved: jest.fn(),
      onSessionIdle: async () => {
        attachmentIdRef.current = 2;
        intentionalAbortRef.current = true;
      },
    });

    const nonEmptyErrors = onError.mock.calls
      .map((call) => call[0])
      .filter((value) => typeof value === "string" && value.trim().length > 0);
    expect(nonEmptyErrors).toHaveLength(0);
    expect(onUpsertAssistant.mock.calls.length).toBeGreaterThanOrEqual(10);
    expect(String(onUpsertAssistant.mock.calls.at(-1)?.[1] || "")).toBe("J");
  });

  it("surfaces permission events to the question callbacks", async () => {
    const sse = [
      buildSseFrame({
        event: "permission.updated",
        session_id: "session-1",
        payload: {
          request_id: "perm-1",
          questions: [
            {
              header: "Permission",
              question: "Allow command?",
              multiple: false,
              options: [
                { label: "Allow", description: "Allow once" },
                { label: "Deny", description: "Reject" },
              ],
            },
          ],
          tool: {
            call_id: "call-1",
            message_id: "message-1",
          },
        },
      }),
      buildSseFrame({
        event: "permission.replied",
        session_id: "session-1",
        payload: { request_id: "perm-1", answers: [["Allow"]] },
      }),
      buildSseFrame({ event: "session.idle", session_id: "session-1", payload: {} }),
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
      headers: new Headers({ "content-type": "text/event-stream" }),
      json: async () => ({}),
    } as unknown as Response;
    (publishedAppsService.streamCodingAgentChatSession as jest.Mock).mockResolvedValue(response);

    const onPermissionUpdated = jest.fn();
    const onPermissionResolved = jest.fn();
    const attachmentIdRef = { current: 1 };
    const intentionalAbortRef = { current: false };

    await consumeSessionStream({
      appId: "app-1",
      sessionId: "session-1",
      streamAttachmentId: 1,
      getCurrentStreamAttachmentId: () => attachmentIdRef.current,
      abortReaderRef: { current: null },
      intentionalAbortRef,
      isMountedRef: { current: true },
      onError: jest.fn(),
      onSetSending: jest.fn(),
      onSetStopping: jest.fn(),
      onSetThinkingSummary: jest.fn(),
      onUpsertAssistant: jest.fn(),
      onUpsertTool: jest.fn(),
      onFinalizeRunningTools: jest.fn(),
      onPermissionUpdated,
      onPermissionResolved,
      onSessionIdle: async () => {
        attachmentIdRef.current = 2;
        intentionalAbortRef.current = true;
      },
    });

    expect(onPermissionUpdated).toHaveBeenCalledWith({
      requestId: "perm-1",
      questions: [
        {
          header: "Permission",
          question: "Allow command?",
          multiple: false,
          options: [
            { label: "Allow", description: "Allow once" },
            { label: "Deny", description: "Reject" },
          ],
        },
      ],
      toolCallId: "call-1",
      toolMessageId: "message-1",
    });
    expect(onPermissionResolved).toHaveBeenCalledWith("perm-1");
  });

  it("ignores user text part updates while still rendering assistant text", async () => {
    const sse = [
      buildSseFrame({ event: "session.connected", session_id: "session-1", payload: {} }),
      buildSseFrame({
        event: "message.updated",
        session_id: "session-1",
        payload: { info: { id: "user-1", role: "user" } },
      }),
      buildSseFrame({
        event: "message.part.updated",
        session_id: "session-1",
        payload: {
          part: {
            id: "user-part-1",
            messageID: "user-1",
            type: "text",
            text: "how are you",
          },
        },
      }),
      buildSseFrame({
        event: "message.updated",
        session_id: "session-1",
        payload: { info: { id: "assistant-1", role: "assistant" } },
      }),
      buildSseFrame({
        event: "message.part.updated",
        session_id: "session-1",
        payload: {
          part: {
            id: "assistant-part-1",
            messageID: "assistant-1",
            type: "text",
            text: "I am well.",
          },
        },
      }),
      buildSseFrame({ event: "session.idle", session_id: "session-1", payload: {} }),
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
      headers: new Headers({ "content-type": "text/event-stream" }),
      json: async () => ({}),
    } as unknown as Response;
    (publishedAppsService.streamCodingAgentChatSession as jest.Mock).mockResolvedValue(response);

    const onUpsertAssistant = jest.fn();
    const attachmentIdRef = { current: 1 };
    const intentionalAbortRef = { current: false };

    await consumeSessionStream({
      appId: "app-1",
      sessionId: "session-1",
      streamAttachmentId: 1,
      getCurrentStreamAttachmentId: () => attachmentIdRef.current,
      abortReaderRef: { current: null },
      intentionalAbortRef,
      isMountedRef: { current: true },
      onError: jest.fn(),
      onSetSending: jest.fn(),
      onSetStopping: jest.fn(),
      onSetThinkingSummary: jest.fn(),
      onUpsertAssistant,
      onUpsertTool: jest.fn(),
      onFinalizeRunningTools: jest.fn(),
      onPermissionUpdated: jest.fn(),
      onPermissionResolved: jest.fn(),
      onSessionIdle: async () => {
        attachmentIdRef.current = 2;
        intentionalAbortRef.current = true;
      },
    });

    expect(onUpsertAssistant).toHaveBeenCalledTimes(1);
    expect(onUpsertAssistant).toHaveBeenCalledWith("assistant-1", "I am well.");
    expect(onUpsertAssistant).not.toHaveBeenCalledWith("user-1", "how are you");
  });

  it("fails fast when the stream endpoint returns non-SSE content", async () => {
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("<html>login</html>"));
        controller.close();
      },
    });
    const response = {
      ok: true,
      status: 200,
      body,
      headers: new Headers({ "content-type": "text/html; charset=utf-8" }),
      json: async () => ({}),
    } as unknown as Response;
    (publishedAppsService.streamCodingAgentChatSession as jest.Mock).mockResolvedValue(response);

    const onError = jest.fn(() => {
      attachmentIdRef.current = 2;
      intentionalAbortRef.current = true;
    });
    const attachmentIdRef = { current: 1 };
    const intentionalAbortRef = { current: false };

    await consumeSessionStream({
      appId: "app-1",
      sessionId: "session-1",
      streamAttachmentId: 1,
      getCurrentStreamAttachmentId: () => attachmentIdRef.current,
      abortReaderRef: { current: null },
      intentionalAbortRef,
      isMountedRef: { current: true },
      onError,
      onSetSending: jest.fn(),
      onSetStopping: jest.fn(),
      onSetThinkingSummary: jest.fn(),
      onUpsertAssistant: jest.fn(),
      onUpsertTool: jest.fn(),
      onFinalizeRunningTools: jest.fn(),
      onPermissionUpdated: jest.fn(),
      onPermissionResolved: jest.fn(),
      onSessionIdle: async () => {
        attachmentIdRef.current = 2;
        intentionalAbortRef.current = true;
      },
    });

    expect(onError).toHaveBeenCalledWith(
      expect.stringContaining("non-SSE content"),
    );
  });
});
