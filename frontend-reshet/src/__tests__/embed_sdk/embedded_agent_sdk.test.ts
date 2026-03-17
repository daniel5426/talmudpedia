/** @jest-environment node */

import { ReadableStream } from "node:stream/web";
import { TextDecoder, TextEncoder } from "node:util";

import {
  EmbeddedAgentClient,
  EmbeddedAgentSDKError,
  type EmbeddedAgentRuntimeEvent,
} from "../../../../packages/embed-sdk/src";

(globalThis as { TextDecoder?: typeof TextDecoder }).TextDecoder = TextDecoder;
(globalThis as { TextEncoder?: typeof TextEncoder }).TextEncoder = TextEncoder;

function buildStreamResponse(chunks: string[], status = 200, headers?: Record<string, string>) {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(new TextEncoder().encode(chunk));
      }
      controller.close();
    },
  });
  const normalizedHeaders = new Map<string, string>();
  for (const [key, value] of Object.entries(headers || {})) {
    normalizedHeaders.set(key.toLowerCase(), value);
  }
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status >= 200 && status < 300 ? "OK" : "ERROR",
    headers: {
      get(name: string) {
        return normalizedHeaders.get(name.toLowerCase()) || null;
      },
    },
    body: stream,
    async text() {
      return "";
    },
    async json() {
      return {};
    },
  } as Response;
}

function buildJsonResponse(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status >= 200 && status < 300 ? "OK" : "ERROR",
    headers: { get() { return null; } },
    body: null,
    async text() {
      return JSON.stringify(payload);
    },
    async json() {
      return payload;
    },
  } as Response;
}

function buildTextErrorResponse(body: string, status = 502) {
  return {
    ok: false,
    status,
    statusText: "Bad Gateway",
    headers: { get() { return null; } },
    body: null,
    async text() {
      return body;
    },
  } as Response;
}

describe("embed-sdk", () => {
  test("streamAgent normalizes baseUrl, sends auth headers, parses multi-line SSE, and returns thread id", async () => {
    const fetchImpl = jest.fn().mockResolvedValue(
      buildStreamResponse(
        [
          ": keepalive\n\n",
          'data: {"version":"run-stream.v2","seq":1,"ts":"2026-03-17T12:00:00Z","event":"run.accepted","run_id":"run-1","stage":"run","payload":{"status":"running"},"diagnostics":[]}\n\n',
          'data: {"version":"run-stream.v2","seq":2,"ts":"2026-03-17T12:00:01Z","event":"assistant.delta","run_id":"run-1","stage":"assistant",\n',
          'data: "payload":{"content":"Hello"},"diagnostics":[]}\n\n',
          'data: {"version":"run-stream.v2","seq":3,"ts":"2026-03-17T12:00:02Z","event":"assistant.delta","run_id":"run-1","stage":"assistant","payload":{"content":"world"},"diagnostics":[]}\n\n',
        ],
        200,
        { "X-Thread-ID": "thread-123" },
      ),
    );

    const client = new EmbeddedAgentClient({
      baseUrl: "https://api.example.com/",
      apiKey: "tpk_demo.secret",
      fetchImpl,
    });

    const events: EmbeddedAgentRuntimeEvent[] = [];
    const result = await client.streamAgent(
      "agent-1",
      {
        input: "Hi",
        external_user_id: "user-1",
      },
      (event) => {
        events.push(event);
      },
    );

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, options] = fetchImpl.mock.calls[0];
    expect(String(url)).toBe("https://api.example.com/public/embed/agents/agent-1/chat/stream");
    expect(options).toMatchObject({
      method: "POST",
      headers: {
        Authorization: "Bearer tpk_demo.secret",
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
    });
    expect(events).toHaveLength(3);
    expect(events[0].event).toBe("run.accepted");
    expect(events[1].payload).toEqual({ content: "Hello" });
    expect(result.threadId).toBe("thread-123");
  });

  test("history helpers serialize query params with json accept headers", async () => {
    const fetchImpl = jest
      .fn()
      .mockResolvedValueOnce(buildJsonResponse({ items: [], total: 0 }))
      .mockResolvedValueOnce(buildJsonResponse({ id: "thread-1", turns: [] }));

    const client = new EmbeddedAgentClient({
      baseUrl: "https://api.example.com/api",
      apiKey: "tpk_demo.secret",
      fetchImpl,
    });

    await client.listAgentThreads("agent-1", {
      externalUserId: "user-1",
      externalSessionId: "session-1",
      skip: 3,
      limit: 7,
    });
    await client.getAgentThread("agent-1", "thread-1", {
      externalUserId: "user-1",
      externalSessionId: "session-1",
    });

    expect(fetchImpl.mock.calls[0][0]).toBe(
      "https://api.example.com/api/public/embed/agents/agent-1/threads?external_user_id=user-1&skip=3&limit=7&external_session_id=session-1",
    );
    expect(fetchImpl.mock.calls[0][1]).toMatchObject({
      method: "GET",
      headers: {
        Authorization: "Bearer tpk_demo.secret",
        Accept: "application/json",
      },
    });
    expect(fetchImpl.mock.calls[1][0]).toBe(
      "https://api.example.com/api/public/embed/agents/agent-1/threads/thread-1?external_user_id=user-1&external_session_id=session-1",
    );
  });

  test("malformed or wrong-version SSE events raise protocol errors", async () => {
    const fetchImpl = jest.fn().mockResolvedValue(
      buildStreamResponse([
        'data: {"version":"run-stream.v1","seq":1,"ts":"2026-03-17T12:00:00Z","event":"run.accepted","run_id":"run-1","stage":"run","payload":{},"diagnostics":[]}\n\n',
      ]),
    );

    const client = new EmbeddedAgentClient({
      baseUrl: "https://api.example.com",
      apiKey: "tpk_demo.secret",
      fetchImpl,
    });

    await expect(
      client.streamAgent("agent-1", {
        input: "Hi",
        external_user_id: "user-1",
      }),
    ).rejects.toMatchObject<Partial<EmbeddedAgentSDKError>>({
      name: "EmbeddedAgentSDKError",
      kind: "protocol",
    });
  });

  test("http and text errors map to EmbeddedAgentSDKError", async () => {
    const fetchImpl = jest
      .fn()
      .mockResolvedValueOnce(buildJsonResponse({ detail: "Missing required scopes: agents.embed" }, 403))
      .mockResolvedValueOnce(buildTextErrorResponse("Upstream gateway exploded", 502));

    const client = new EmbeddedAgentClient({
      baseUrl: "https://api.example.com",
      apiKey: "tpk_demo.secret",
      fetchImpl,
    });

    await expect(
      client.listAgentThreads("agent-1", { externalUserId: "user-1" }),
    ).rejects.toMatchObject<Partial<EmbeddedAgentSDKError>>({
      kind: "http",
      status: 403,
      message: "Missing required scopes: agents.embed",
    });

    await expect(
      client.getAgentThread("agent-1", "thread-1", { externalUserId: "user-1" }),
    ).rejects.toMatchObject<Partial<EmbeddedAgentSDKError>>({
      kind: "http",
      status: 502,
      message: "Upstream gateway exploded",
    });
  });

  test("network failures map to network errors", async () => {
    const fetchImpl = jest.fn().mockRejectedValue(new Error("socket hang up"));
    const client = new EmbeddedAgentClient({
      baseUrl: "https://api.example.com",
      apiKey: "tpk_demo.secret",
      fetchImpl,
    });

    await expect(
      client.listAgentThreads("agent-1", { externalUserId: "user-1" }),
    ).rejects.toMatchObject<Partial<EmbeddedAgentSDKError>>({
      kind: "network",
      message: "Failed to connect to the embedded-agent API.",
    });
  });

  test("constructor rejects browser runtime usage", () => {
    const originalWindow = (globalThis as { window?: unknown }).window;
    const originalDocument = (globalThis as { document?: unknown }).document;
    (globalThis as { window?: unknown }).window = {};
    (globalThis as { document?: unknown }).document = {};

    try {
      expect(
        () =>
          new EmbeddedAgentClient({
            baseUrl: "https://api.example.com",
            apiKey: "tpk_demo.secret",
            fetchImpl: jest.fn() as unknown as typeof fetch,
          }),
      ).toThrow(/server-only/i);
    } finally {
      if (originalWindow === undefined) {
        delete (globalThis as { window?: unknown }).window;
      } else {
        (globalThis as { window?: unknown }).window = originalWindow;
      }
      if (originalDocument === undefined) {
        delete (globalThis as { document?: unknown }).document;
      } else {
        (globalThis as { document?: unknown }).document = originalDocument;
      }
    }
  });
});
