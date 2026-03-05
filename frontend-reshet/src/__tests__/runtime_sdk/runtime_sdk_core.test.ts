import { createRuntimeClient, fetchRuntimeBootstrap, normalizeRuntimeEvent } from "../../../../packages/runtime-sdk/src";
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
    chat_stream_path: "/api/py/public/apps/slug-1/chat/stream",
    chat_stream_url: "https://api.example.com/api/py/public/apps/slug-1/chat/stream",
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
      payload: { content: "delta" },
    });

    expect(normalized.type).toBe("assistant.delta");
    expect(normalized.content).toBe("delta");
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
});
