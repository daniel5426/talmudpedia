export type AgentThreadSummaryDto = {
  id: string;
  title: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  last_activity_at: string | null;
};

export type AgentThreadTurnDto = {
  id: string;
  user_input_text: string | null;
  assistant_output_text: string | null;
  created_at: string;
  completed_at: string | null;
};

export type AgentThreadDetailDto = AgentThreadSummaryDto & {
  turns: AgentThreadTurnDto[];
};

export type StandaloneRuntimeEvent = {
  version: "run-stream.v2";
  seq: number;
  ts: string;
  event: string;
  run_id: string;
  stage: string;
  payload: Record<string, unknown>;
  diagnostics: Array<Record<string, unknown>>;
};

type StreamResult = {
  threadId: string | null;
};

type StreamPayload = {
  input: string;
  threadId?: string;
  clientId: string;
};

function isStandaloneRuntimeEvent(value: unknown): value is StandaloneRuntimeEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Record<string, unknown>;
  return event.version === "run-stream.v2" && typeof event.event === "string";
}

async function parseJsonOrThrow<T>(response: Response, fallbackMessage: string): Promise<T> {
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { error?: string }
      | null;
    throw new Error(payload?.error || fallbackMessage);
  }
  return (await response.json()) as T;
}

export async function fetchAgentThreads(): Promise<{
  items: AgentThreadSummaryDto[];
  total: number;
}> {
  const response = await fetch("/api/agent/threads", { credentials: "same-origin" });
  return parseJsonOrThrow(response, "Failed to fetch thread history.");
}

export async function fetchAgentThread(threadId: string): Promise<AgentThreadDetailDto> {
  const response = await fetch(`/api/agent/threads/${threadId}`, {
    credentials: "same-origin",
  });
  return parseJsonOrThrow(response, "Failed to fetch thread details.");
}

export async function streamAgent(
  payload: StreamPayload,
  onEvent: (event: StandaloneRuntimeEvent) => void,
): Promise<StreamResult> {
  const response = await fetch("/api/agent/chat/stream", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    const errorPayload = (await response.json().catch(() => null)) as
      | { error?: string }
      | null;
    throw new Error(errorPayload?.error || "Failed to stream agent response.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let resolvedThreadId = response.headers.get("X-Thread-ID");

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let separatorIndex = buffer.indexOf("\n\n");
    while (separatorIndex !== -1) {
      const block = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      const lines = block.split("\n");
      const payloadLines = lines
        .filter((line) => line.startsWith("data: "))
        .map((line) => line.slice(6));
      if (payloadLines.length > 0) {
        const rawPayload = payloadLines.join("\n");
        const parsed = JSON.parse(rawPayload) as unknown;
        if (isStandaloneRuntimeEvent(parsed)) {
          if (!resolvedThreadId && parsed.event === "run.accepted") {
            const acceptedThreadId = parsed.payload.thread_id;
            if (typeof acceptedThreadId === "string" && acceptedThreadId.trim()) {
              resolvedThreadId = acceptedThreadId;
            }
          }
          onEvent(parsed);
        }
      }
      separatorIndex = buffer.indexOf("\n\n");
    }
  }

  return {
    threadId: resolvedThreadId,
  };
}
