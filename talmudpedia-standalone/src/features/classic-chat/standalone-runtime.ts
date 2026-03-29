export type AgentThreadSummaryDto = {
  id: string;
  title: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  last_activity_at: string | null;
};

export type AgentAttachmentDto = {
  id: string;
  thread_id: string | null;
  kind: "image" | "document" | "audio";
  filename: string;
  mime_type: string;
  byte_size: number;
  status: string;
  processing_error: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AgentThreadTurnDto = {
  id: string;
  run_id: string;
  user_input_text: string | null;
  assistant_output_text: string | null;
  status: string;
  usage_tokens: number;
  metadata: Record<string, unknown>;
  attachments: AgentAttachmentDto[];
  created_at: string;
  completed_at: string | null;
  run_events: StandaloneRuntimeEvent[];
};

export type AgentThreadDetailDto = AgentThreadSummaryDto & {
  turns: AgentThreadTurnDto[];
  paging: {
    has_more: boolean;
    next_before_turn_index: number | null;
  };
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
  input?: string;
  attachmentIds?: string[];
  threadId?: string;
  clientId: string;
};

export type UploadAgentAttachmentsPayload = {
  files: Array<{
    filename: string;
    mediaType: string;
    url: string;
  }>;
  threadId?: string;
};

async function fileUrlToFile(file: UploadAgentAttachmentsPayload["files"][number]): Promise<File> {
  const response = await fetch(file.url);
  const blob = await response.blob();
  return new File([blob], file.filename, {
    type: file.mediaType || blob.type || "application/octet-stream",
  });
}

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

export async function fetchAgentThread(
  threadId: string,
  options?: { beforeTurnIndex?: number; limit?: number },
): Promise<AgentThreadDetailDto> {
  const query = new URLSearchParams();
  if (typeof options?.beforeTurnIndex === "number") {
    query.set("before_turn_index", String(options.beforeTurnIndex));
  }
  if (typeof options?.limit === "number") {
    query.set("limit", String(options.limit));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const response = await fetch(`/api/agent/threads/${threadId}${suffix}`, {
    credentials: "same-origin",
  });
  return parseJsonOrThrow(response, "Failed to fetch thread details.");
}

export async function deleteAgentThread(threadId: string): Promise<{ deleted: boolean }> {
  const response = await fetch(`/api/agent/threads/${threadId}`, {
    method: "DELETE",
    credentials: "same-origin",
  });
  return parseJsonOrThrow(response, "Failed to delete thread.");
}

export async function uploadAgentAttachments(
  payload: UploadAgentAttachmentsPayload,
): Promise<{ items: AgentAttachmentDto[] }> {
  const formData = new FormData();
  if (payload.threadId) {
    formData.set("threadId", payload.threadId);
  }
  for (const item of payload.files) {
    const file = await fileUrlToFile(item);
    formData.append("files", file, item.filename);
  }
  const response = await fetch("/api/agent/attachments/upload", {
    method: "POST",
    credentials: "same-origin",
    body: formData,
  });
  return parseJsonOrThrow(response, "Failed to upload attachments.");
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

  const processBlock = (block: string) => {
    const lines = block.split("\n");
    const payloadLines = lines
      .filter((line) => line.startsWith("data: "))
      .map((line) => line.slice(6));
    if (payloadLines.length === 0) {
      return;
    }
    const rawPayload = payloadLines.join("\n");
    const parsed = JSON.parse(rawPayload) as unknown;
    if (!isStandaloneRuntimeEvent(parsed)) {
      return;
    }
    if (!resolvedThreadId && parsed.event === "run.accepted") {
      const acceptedThreadId = parsed.payload.thread_id;
      if (typeof acceptedThreadId === "string" && acceptedThreadId.trim()) {
        resolvedThreadId = acceptedThreadId;
      }
    }
    onEvent(parsed);
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let separatorIndex = buffer.indexOf("\n\n");
    while (separatorIndex !== -1) {
      const block = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      processBlock(block);
      separatorIndex = buffer.indexOf("\n\n");
    }
  }

  const tail = buffer.trim();
  if (tail) {
    processBlock(tail);
  }

  return {
    threadId: resolvedThreadId,
  };
}
