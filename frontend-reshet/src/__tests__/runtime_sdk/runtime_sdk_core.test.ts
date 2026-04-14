import {
  createPublishedAppAuthClient,
  createRuntimeClient,
  fetchRuntimeBootstrap,
  normalizeRuntimeEvent,
} from "../../../../packages/runtime-sdk/src";
import type { RuntimeBootstrap } from "../../../../packages/runtime-sdk/src";
import { ReadableStream } from "node:stream/web";
import { TextDecoder, TextEncoder } from "node:util";

(globalThis as { TextDecoder?: typeof TextDecoder }).TextDecoder = TextDecoder;

function buildResponse(chunks: string[], status = 200, headers?: Record<string, string>) {
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
  };
}

describe("runtime-sdk core", () => {
  const bootstrap: RuntimeBootstrap = {
    version: "runtime-bootstrap.v1",
    stream_contract_version: "run-stream.v2",
    request_contract_version: "thread.v1",
    app_id: "app-1",
    slug: "slug-1",
    mode: "published-runtime",
    api_base_path: "/api/py",
    api_base_url: "https://api.example.com/api/py",
    chat_stream_path: "/api/py/public/external/apps/slug-1/chat/stream",
    chat_stream_url: "https://api.example.com/api/py/public/external/apps/slug-1/chat/stream",
    auth: {
      enabled: true,
      providers: ["password"],
      exchange_enabled: false,
    },
  };

  test("parses chunked SSE events and returns thread id", async () => {
    const fetchImpl = jest.fn().mockResolvedValue(
      buildResponse(
        [
          'data: {"version":"run-stream.v2","seq":1,"ts":"2026-03-02T00:00:00Z","event":"assistant.delta","run_id":"run-1","stage":"assistant","payload":{"content":"Hello"},"diagnostics":[]',
          '}\n\n',
          'data: {"version":"run-stream.v2","seq":2,"ts":"2026-03-02T00:00:01Z","event":"assistant.delta","run_id":"run-1","stage":"assistant","payload":{"content":" world"},"diagnostics":[]}\n\n',
        ],
        200,
        { "X-Thread-ID": "thread-123" },
      ),
    );

    const events: string[] = [];
    const client = createRuntimeClient({ bootstrap, fetchImpl });
    const result = await client.stream({ input: "hi" }, (event) => {
      if (event.event === "assistant.delta") {
        events.push(String(event.content || ""));
      }
    });

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(events.join("")).toBe("Hello world");
    expect(result.threadId).toBe("thread-123");
  });

  test("ignores malformed SSE payloads and calls tokenProvider", async () => {
    const tokenProvider = jest.fn().mockResolvedValue("token-abc");
    const fetchImpl = jest.fn().mockResolvedValue(
      buildResponse(
        [
          "data: not-json\n\n",
          'data: {"version":"run-stream.v2","seq":1,"ts":"2026-03-02T00:00:00Z","event":"assistant.delta","run_id":"run-1","stage":"assistant","payload":{"content":"ok"},"diagnostics":[]}\n\n',
        ],
      ),
    );

    const client = createRuntimeClient({ bootstrap, fetchImpl, tokenProvider });
    const received: string[] = [];
    await client.stream({ input: "hello" }, (event) => {
      if (event.event === "assistant.delta") {
        received.push(String(event.content || ""));
      }
    });

    expect(tokenProvider).toHaveBeenCalledTimes(1);
    expect(fetchImpl.mock.calls[0][1]?.headers?.Authorization).toBe("Bearer token-abc");
    expect(received).toEqual(["ok"]);
  });

  test("normalizes payload/content fallback", () => {
    const normalized = normalizeRuntimeEvent({
      version: "run-stream.v2",
      type: "assistant.delta",
      payload: {
        content: "delta",
        assistant_output_text: "delta",
        response_blocks: [
          {
            id: "assistant-text-1",
            kind: "assistant_text",
            seq: 1,
            status: "streaming",
            text: "delta",
          },
        ],
      },
    });

    expect(normalized.type).toBe("assistant.delta");
    expect(normalized.content).toBe("delta");
    expect(normalized.assistantOutputText).toBe("delta");
    expect(normalized.responseBlocks).toMatchObject([
      {
        id: "assistant-text-1",
        kind: "assistant_text",
        text: "delta",
      },
    ]);
  });

  test("normalizes explicit ui_blocks response blocks", () => {
    const normalized = normalizeRuntimeEvent({
      version: "run-stream.v2",
      event: "tool.completed",
      payload: {
        response_blocks: [
          {
            id: "ui-1",
            kind: "ui_blocks",
            seq: 2,
            status: "complete",
            toolCallId: "call-1",
            contractVersion: "v1",
            bundle: {
              title: "Overview",
              rows: [
                {
                  blocks: [
                    {
                      id: "kpi-1",
                      kind: "kpi",
                      title: "Users",
                      value: "42",
                      span: 12,
                    },
                  ],
                },
              ],
            },
          },
        ],
      },
    });

    expect(normalized.responseBlocks).toMatchObject([
      {
        id: "ui-1",
        kind: "ui_blocks",
        toolCallId: "call-1",
        contractVersion: "v1",
      },
    ]);
  });

  test("fetchRuntimeBootstrap sends preview auth via Authorization header only", async () => {
    const fetchImpl = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      async json() {
        return bootstrap;
      },
    });

    await fetchRuntimeBootstrap({
      apiBaseUrl: "https://api.example.com/api/py",
      revisionId: "rev-1",
      previewToken: "preview-token-123",
      fetchImpl,
    });

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, options] = fetchImpl.mock.calls[0];
    expect(String(url)).toBe("https://api.example.com/api/py/public/apps/preview/revisions/rev-1/runtime/bootstrap");
    expect(String(url)).not.toContain("preview_token=");
    expect(options).toMatchObject({
      method: "GET",
      headers: { Authorization: "Bearer preview-token-123" },
    });
  });

  test("fetchRuntimeBootstrap resolves builder preview bootstrap from the preview base path global", async () => {
    const originalBasePath = (window as Window & { __TALMUDPEDIA_BUILDER_PREVIEW_BASE_PATH?: unknown }).__TALMUDPEDIA_BUILDER_PREVIEW_BASE_PATH;
    (window as Window & { __TALMUDPEDIA_BUILDER_PREVIEW_BASE_PATH?: unknown }).__TALMUDPEDIA_BUILDER_PREVIEW_BASE_PATH =
      "/public/apps-builder/draft-dev/sessions/session-1/preview";

    const fetchImpl = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      async json() {
        return bootstrap;
      },
    });

    try {
      await fetchRuntimeBootstrap({
        apiBaseUrl: "https://api.example.com/api/py",
        fetchImpl,
      });
    } finally {
      (window as Window & { __TALMUDPEDIA_BUILDER_PREVIEW_BASE_PATH?: unknown }).__TALMUDPEDIA_BUILDER_PREVIEW_BASE_PATH = originalBasePath;
    }

    const [url, options] = fetchImpl.mock.calls[0];
    expect(String(url)).toBe("https://api.example.com/api/py/public/apps-builder/draft-dev/sessions/session-1/preview/_talmudpedia/runtime/bootstrap");
    expect(options).toMatchObject({
      method: "GET",
    });
  });

  test("fetchRuntimeBootstrap uses external published runtime path for app slugs", async () => {
    const fetchImpl = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      async json() {
        return bootstrap;
      },
    });

    await fetchRuntimeBootstrap({
      apiBaseUrl: "https://api.example.com/api/py",
      appSlug: "slug-1",
      fetchImpl,
    });

    const [url] = fetchImpl.mock.calls[0];
    expect(String(url)).toBe("https://api.example.com/api/py/public/external/apps/slug-1/runtime/bootstrap");
  });

  test("published app auth client uses external auth and history routes", async () => {
    const tokenStore = {
      get: jest.fn().mockReturnValue("stored-token"),
      set: jest.fn(),
      clear: jest.fn(),
    };
    const fetchImpl = jest.fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        statusText: "OK",
        async json() {
          return { token: "new-token", token_type: "bearer", user: { id: "u1", email: "u@example.com" } };
        },
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        statusText: "OK",
        async json() {
          return { items: [], total: 0, page: 1, pages: 1 };
        },
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        statusText: "OK",
        async json() {
          return { id: "thread-1", title: "Thread", status: "active", surface: "published_app", created_at: "", updated_at: "", last_activity_at: "", turns: [] };
        },
      });

    const client = createPublishedAppAuthClient({
      apiBaseUrl: "https://api.example.com/api/py",
      appSlug: "slug-1",
      fetchImpl,
      tokenStore,
    });

    await client.login({ email: "u@example.com", password: "secret123" });
    await client.listThreads();
    await client.getThread("thread-1");

    expect(fetchImpl.mock.calls[0][0]).toBe("https://api.example.com/api/py/public/external/apps/slug-1/auth/login");
    expect(fetchImpl.mock.calls[1][0]).toBe("https://api.example.com/api/py/public/external/apps/slug-1/threads");
    expect(fetchImpl.mock.calls[1][1]).toMatchObject({
      headers: { Authorization: "Bearer stored-token" },
    });
    expect(fetchImpl.mock.calls[2][0]).toBe("https://api.example.com/api/py/public/external/apps/slug-1/threads/thread-1");
    expect(tokenStore.set).toHaveBeenCalledWith("new-token");
  });
});
