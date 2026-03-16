import { ReadableStream } from "node:stream/web";
import { TextDecoder, TextEncoder } from "node:util";

import {
  EmbeddedAgentClient,
  EmbeddedAgentSDKError,
} from "@/services/embedded-agent-sdk";

(globalThis as { TextDecoder?: typeof TextDecoder }).TextDecoder = TextDecoder;

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
    async json() {
      return {};
    },
  } as Response;
}

describe("embedded-agent-sdk", () => {
  test("streamAgent sends bearer auth, parses SSE, and returns thread id", async () => {
    const fetchImpl = jest.fn().mockResolvedValue(
      buildStreamResponse(
        [
          'data: {"version":"run-stream.v2","event":"assistant.delta","payload":{"content":"Hello"}}\n\n',
          'data: {"version":"run-stream.v2","event":"assistant.delta","payload":{"content":" world"}}\n\n',
        ],
        200,
        { "X-Thread-ID": "thread-123" },
      ),
    );

    const client = new EmbeddedAgentClient({
      baseUrl: "https://api.example.com/api/py",
      apiKey: "tpk_demo.secret",
      fetchImpl,
    });

    const events: Array<Record<string, unknown>> = [];
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
    expect(String(url)).toBe("https://api.example.com/api/py/public/embed/agents/agent-1/chat/stream");
    expect(options).toMatchObject({
      method: "POST",
      headers: {
        Authorization: "Bearer tpk_demo.secret",
        "Content-Type": "application/json",
      },
    });
    expect(events).toHaveLength(2);
    expect(result.threadId).toBe("thread-123");
  });

  test("history helpers serialize required external-user params", async () => {
    const fetchImpl = jest
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        statusText: "OK",
        async json() {
          return { items: [], total: 0 };
        },
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        statusText: "OK",
        async json() {
          return { id: "thread-1", turns: [] };
        },
      });

    const client = new EmbeddedAgentClient({
      baseUrl: "https://api.example.com/api/py",
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
      "https://api.example.com/api/py/public/embed/agents/agent-1/threads?external_user_id=user-1&skip=3&limit=7&external_session_id=session-1",
    );
    expect(fetchImpl.mock.calls[1][0]).toBe(
      "https://api.example.com/api/py/public/embed/agents/agent-1/threads/thread-1?external_user_id=user-1&external_session_id=session-1",
    );
  });

  test("non-2xx embed responses map to EmbeddedAgentSDKError", async () => {
    const fetchImpl = jest.fn().mockResolvedValue({
      ok: false,
      status: 403,
      statusText: "Forbidden",
      async json() {
        return { detail: "Missing required scopes: agents.embed" };
      },
    });

    const client = new EmbeddedAgentClient({
      baseUrl: "https://api.example.com/api/py",
      apiKey: "tpk_demo.secret",
      fetchImpl,
    });

    await expect(
      client.listAgentThreads("agent-1", { externalUserId: "user-1" }),
    ).rejects.toEqual(
      expect.objectContaining<Partial<EmbeddedAgentSDKError>>({
        name: "EmbeddedAgentSDKError",
        message: "Missing required scopes: agents.embed",
        status: 403,
      }),
    );
  });
});
