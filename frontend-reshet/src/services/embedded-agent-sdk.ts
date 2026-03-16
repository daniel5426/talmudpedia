export type EmbeddedAgentStreamRequest = {
  input?: string;
  messages?: Array<Record<string, unknown>>;
  thread_id?: string;
  external_user_id: string;
  external_session_id?: string;
  metadata?: Record<string, unknown>;
  client?: Record<string, unknown>;
};

export type EmbeddedAgentThreadSummary = {
  id: string;
  agent_id: string | null;
  external_user_id: string | null;
  external_session_id: string | null;
  title: string | null;
  status: string;
  surface: string;
  last_run_id: string | null;
  last_activity_at: string | null;
  created_at: string;
  updated_at: string;
};

export type EmbeddedAgentThreadTurn = {
  id: string;
  run_id: string;
  turn_index: number;
  user_input_text: string | null;
  assistant_output_text: string | null;
  status: string;
  usage_tokens: number;
  metadata: Record<string, unknown>;
  created_at: string;
  completed_at: string | null;
};

export type EmbeddedAgentThreadDetail = EmbeddedAgentThreadSummary & {
  turns: EmbeddedAgentThreadTurn[];
};

export type EmbeddedAgentThreadsResponse = {
  items: EmbeddedAgentThreadSummary[];
  total: number;
};

export type EmbeddedAgentRuntimeEvent = Record<string, unknown>;

type FetchLike = typeof fetch;

export class EmbeddedAgentSDKError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "EmbeddedAgentSDKError";
  }
}

export class EmbeddedAgentClient {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly fetchImpl: FetchLike;

  constructor({
    baseUrl,
    apiKey,
    fetchImpl,
  }: {
    baseUrl: string;
    apiKey: string;
    fetchImpl?: FetchLike;
  }) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.apiKey = apiKey;
    this.fetchImpl = fetchImpl ?? fetch;
  }

  async streamAgent(
    agentId: string,
    payload: EmbeddedAgentStreamRequest,
    onEvent?: (event: EmbeddedAgentRuntimeEvent) => void | Promise<void>,
  ): Promise<{ threadId: string | null }> {
    const response = await this.fetchImpl(
      `${this.baseUrl}/public/embed/agents/${agentId}/chat/stream`,
      {
        method: "POST",
        headers: this.buildHeaders(),
        body: JSON.stringify(payload),
      },
    );
    await this.assertOk(response);
    await this.consumeSSE(response, onEvent);
    return { threadId: response.headers.get("X-Thread-ID") };
  }

  async listAgentThreads(
    agentId: string,
    {
      externalUserId,
      externalSessionId,
      skip = 0,
      limit = 20,
    }: {
      externalUserId: string;
      externalSessionId?: string;
      skip?: number;
      limit?: number;
    },
  ): Promise<EmbeddedAgentThreadsResponse> {
    const search = new URLSearchParams({
      external_user_id: externalUserId,
      skip: String(skip),
      limit: String(limit),
    });
    if (externalSessionId) {
      search.set("external_session_id", externalSessionId);
    }
    const response = await this.fetchImpl(
      `${this.baseUrl}/public/embed/agents/${agentId}/threads?${search.toString()}`,
      { method: "GET", headers: this.buildHeaders() },
    );
    await this.assertOk(response);
    return response.json();
  }

  async getAgentThread(
    agentId: string,
    threadId: string,
    {
      externalUserId,
      externalSessionId,
    }: {
      externalUserId: string;
      externalSessionId?: string;
    },
  ): Promise<EmbeddedAgentThreadDetail> {
    const search = new URLSearchParams({
      external_user_id: externalUserId,
    });
    if (externalSessionId) {
      search.set("external_session_id", externalSessionId);
    }
    const response = await this.fetchImpl(
      `${this.baseUrl}/public/embed/agents/${agentId}/threads/${threadId}?${search.toString()}`,
      { method: "GET", headers: this.buildHeaders() },
    );
    await this.assertOk(response);
    return response.json();
  }

  private buildHeaders(): HeadersInit {
    return {
      Authorization: `Bearer ${this.apiKey}`,
      "Content-Type": "application/json",
    };
  }

  private async assertOk(response: Response): Promise<void> {
    if (response.ok) {
      return;
    }

    let details: unknown = null;
    try {
      details = await response.json();
    } catch {
      details = null;
    }
    const message =
      (typeof details === "object" &&
      details !== null &&
      "detail" in details &&
      typeof (details as { detail?: unknown }).detail === "string"
        ? (details as { detail: string }).detail
        : response.statusText) || "Request failed";
    throw new EmbeddedAgentSDKError(message, response.status, details);
  }

  private async consumeSSE(
    response: Response,
    onEvent?: (event: EmbeddedAgentRuntimeEvent) => void | Promise<void>,
  ): Promise<void> {
    if (!onEvent || !response.body) {
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() ?? "";
      for (const chunk of chunks) {
        for (const line of chunk.split("\n")) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data:")) {
            continue;
          }
          const payload = trimmed.slice(5).trim();
          if (!payload) {
            continue;
          }
          try {
            const parsed = JSON.parse(payload) as EmbeddedAgentRuntimeEvent;
            await onEvent(parsed);
          } catch {
            continue;
          }
        }
      }
    }
  }
}
