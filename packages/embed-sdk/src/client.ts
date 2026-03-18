import { EmbeddedAgentSDKError } from "./errors";
import {
  assertOk,
  assertServerRuntime,
  buildJsonHeaders,
  buildStreamHeaders,
  normalizeBaseUrl,
  resolveFetchImpl,
  wrapNetworkError,
} from "./http";
import { consumeEventStream } from "./sse";
import type {
  EmbeddedAgentClientOptions,
  EmbeddedAgentRuntimeEvent,
  EmbeddedAgentStreamRequest,
  EmbeddedAgentThreadDetail,
  EmbeddedAgentThreadDeleteOptions,
  EmbeddedAgentThreadDeleteResult,
  EmbeddedAgentThreadDetailOptions,
  EmbeddedAgentThreadListOptions,
  EmbeddedAgentThreadsResponse,
  StreamAgentResult,
} from "./types";

export class EmbeddedAgentClient {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly fetchImpl: typeof fetch;

  constructor({ baseUrl, apiKey, fetchImpl }: EmbeddedAgentClientOptions) {
    assertServerRuntime();
    const normalizedApiKey = String(apiKey || "").trim();
    if (!normalizedApiKey) {
      throw new EmbeddedAgentSDKError("EmbeddedAgentClient requires a non-empty apiKey.", {
        kind: "protocol",
      });
    }
    this.baseUrl = normalizeBaseUrl(baseUrl);
    this.apiKey = normalizedApiKey;
    this.fetchImpl = resolveFetchImpl(fetchImpl);
  }

  async streamAgent(
    agentId: string,
    payload: EmbeddedAgentStreamRequest,
    onEvent?: (event: EmbeddedAgentRuntimeEvent) => void | Promise<void>,
  ): Promise<StreamAgentResult> {
    const response = await this.fetchOrThrow(
      `${this.baseUrl}/public/embed/agents/${agentId}/chat/stream`,
      {
        method: "POST",
        headers: buildStreamHeaders(this.apiKey),
        body: JSON.stringify(payload),
      },
      "Failed to connect to the embedded-agent stream endpoint.",
    );

    await assertOk(response);
    const threadId = response.headers.get("X-Thread-ID");
    await consumeEventStream(response, onEvent);
    return { threadId };
  }

  async listAgentThreads(
    agentId: string,
    {
      externalUserId,
      externalSessionId,
      skip = 0,
      limit = 20,
    }: EmbeddedAgentThreadListOptions,
  ): Promise<EmbeddedAgentThreadsResponse> {
    const search = new URLSearchParams({
      external_user_id: externalUserId,
      skip: String(skip),
      limit: String(limit),
    });
    if (externalSessionId) {
      search.set("external_session_id", externalSessionId);
    }
    return this.requestJson<EmbeddedAgentThreadsResponse>(
      `${this.baseUrl}/public/embed/agents/${agentId}/threads?${search.toString()}`,
    );
  }

  async getAgentThread(
    agentId: string,
    threadId: string,
    {
      externalUserId,
      externalSessionId,
    }: EmbeddedAgentThreadDetailOptions,
  ): Promise<EmbeddedAgentThreadDetail> {
    const search = new URLSearchParams({
      external_user_id: externalUserId,
    });
    if (externalSessionId) {
      search.set("external_session_id", externalSessionId);
    }
    return this.requestJson<EmbeddedAgentThreadDetail>(
      `${this.baseUrl}/public/embed/agents/${agentId}/threads/${threadId}?${search.toString()}`,
    );
  }

  async deleteAgentThread(
    agentId: string,
    threadId: string,
    {
      externalUserId,
      externalSessionId,
    }: EmbeddedAgentThreadDeleteOptions,
  ): Promise<EmbeddedAgentThreadDeleteResult> {
    const search = new URLSearchParams({
      external_user_id: externalUserId,
    });
    if (externalSessionId) {
      search.set("external_session_id", externalSessionId);
    }
    return this.requestJson<EmbeddedAgentThreadDeleteResult>(
      `${this.baseUrl}/public/embed/agents/${agentId}/threads/${threadId}?${search.toString()}`,
      {
        method: "DELETE",
        headers: buildJsonHeaders(this.apiKey),
      },
    );
  }

  private async requestJson<T>(url: string, init?: RequestInit): Promise<T> {
    const response = await this.fetchOrThrow(
      url,
      init || {
        method: "GET",
        headers: buildJsonHeaders(this.apiKey),
      },
      "Failed to connect to the embedded-agent API.",
    );
    await assertOk(response);
    return (await response.json()) as T;
  }

  private async fetchOrThrow(url: string, init: RequestInit, networkMessage: string): Promise<Response> {
    try {
      return await this.fetchImpl(url, init);
    } catch (cause) {
      throw wrapNetworkError(networkMessage, cause);
    }
  }
}
