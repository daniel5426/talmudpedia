export type RuntimeEvent = {
  type: string;
  event?: string;
  data?: Record<string, unknown>;
  payload?: Record<string, unknown>;
  content?: string;
};

export type RuntimeInput = {
  input?: string;
  messages?: Array<{ role: string; content: string }>;
  thread_id?: string;
  attachment_ids?: string[];
  context?: Record<string, unknown>;
};

function parseEventPayload(raw: string): RuntimeEvent | null {
  if (!raw.startsWith("data:")) {
    return null;
  }
  const payload = raw.slice(5).trim();
  if (!payload) {
    return null;
  }
  try {
    const parsed = JSON.parse(payload) as Record<string, unknown>;
    return {
      type: String(parsed.event || parsed.type || "event"),
      event: typeof parsed.event === "string" ? parsed.event : undefined,
      data: parsed.data as Record<string, unknown> | undefined,
      payload: parsed.payload as Record<string, unknown> | undefined,
      content:
        typeof parsed.content === "string"
          ? parsed.content
          : typeof parsed.payload === "object" && parsed.payload && typeof (parsed.payload as Record<string, unknown>).content === "string"
            ? String((parsed.payload as Record<string, unknown>).content)
            : undefined,
    };
  } catch {
    return null;
  }
}

async function readSseStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: RuntimeEvent) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const event = parseEventPayload(frame);
      if (event) {
        onEvent(event);
      }
    }
  }
}

export const createRuntimeClient = () => {
  return {
    async stream(
      input: RuntimeInput,
      onEvent: (event: RuntimeEvent) => void,
    ): Promise<{ threadId: string | null }> {
      const response = await fetch("/api/agent/chat/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          input: input.input,
          threadId: input.thread_id,
          attachmentIds: input.attachment_ids || [],
        }),
      });

      if (!response.ok) {
        let message = "Failed to stream response";
        try {
          const payload = await response.json() as { error?: string; detail?: string };
          message = String(payload.error || payload.detail || message);
        } catch {
          message = response.statusText || message;
        }
        throw new Error(message);
      }

      if (!response.body) {
        throw new Error("Streaming reader unavailable");
      }

      await readSseStream(response.body, onEvent);
      return { threadId: response.headers.get("X-Thread-ID") };
    },
  };
};
