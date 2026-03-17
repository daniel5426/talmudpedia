import { EmbeddedAgentSDKError } from "./errors";
import type { EmbeddedAgentRuntimeDiagnostic, EmbeddedAgentRuntimeEvent } from "./types";

function parseSSEBlock(block: string): string | null {
  const dataLines: string[] = [];
  const lines = block.split("\n");
  for (const line of lines) {
    if (!line || line.startsWith(":")) {
      continue;
    }
    const separatorIndex = line.indexOf(":");
    const field = separatorIndex === -1 ? line : line.slice(0, separatorIndex);
    let value = separatorIndex === -1 ? "" : line.slice(separatorIndex + 1);
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }
    if (field === "data") {
      dataLines.push(value);
    }
  }
  if (dataLines.length === 0) {
    return null;
  }
  return dataLines.join("\n");
}

function assertDiagnostics(value: unknown): EmbeddedAgentRuntimeDiagnostic[] {
  if (!Array.isArray(value)) {
    throw new EmbeddedAgentSDKError("Malformed embedded-agent SSE event: diagnostics must be an array.", {
      kind: "protocol",
      details: value,
    });
  }
  return value.map((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      throw new EmbeddedAgentSDKError("Malformed embedded-agent SSE event: diagnostics entries must be objects.", {
        kind: "protocol",
        details: item,
      });
    }
    return item as EmbeddedAgentRuntimeDiagnostic;
  });
}

function assertPayload(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new EmbeddedAgentSDKError("Malformed embedded-agent SSE event: payload must be an object.", {
      kind: "protocol",
      details: value,
    });
  }
  return value as Record<string, unknown>;
}

export function parseRuntimeEvent(rawPayload: string): EmbeddedAgentRuntimeEvent {
  let parsed: unknown;
  try {
    parsed = JSON.parse(rawPayload) as unknown;
  } catch (cause) {
    throw new EmbeddedAgentSDKError("Malformed embedded-agent SSE event: invalid JSON payload.", {
      kind: "protocol",
      cause,
      details: rawPayload,
    });
  }

  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new EmbeddedAgentSDKError("Malformed embedded-agent SSE event: expected an object envelope.", {
      kind: "protocol",
      details: parsed,
    });
  }

  const candidate = parsed as Record<string, unknown>;
  if (candidate.version !== "run-stream.v2") {
    throw new EmbeddedAgentSDKError(
      "Embedded-agent SSE protocol mismatch: expected run-stream.v2 event envelopes.",
      {
        kind: "protocol",
        details: candidate,
      },
    );
  }

  if (
    typeof candidate.seq !== "number" ||
    !Number.isFinite(candidate.seq) ||
    typeof candidate.ts !== "string" ||
    typeof candidate.event !== "string" ||
    typeof candidate.run_id !== "string" ||
    typeof candidate.stage !== "string"
  ) {
    throw new EmbeddedAgentSDKError("Malformed embedded-agent SSE event: missing required envelope fields.", {
      kind: "protocol",
      details: candidate,
    });
  }

  return {
    version: "run-stream.v2",
    seq: candidate.seq,
    ts: candidate.ts,
    event: candidate.event,
    run_id: candidate.run_id,
    stage: candidate.stage,
    payload: assertPayload(candidate.payload ?? {}),
    diagnostics: assertDiagnostics(candidate.diagnostics ?? []),
  };
}

export async function consumeEventStream(
  response: Response,
  onEvent?: (event: EmbeddedAgentRuntimeEvent) => void | Promise<void>,
): Promise<void> {
  if (!response.body) {
    throw new EmbeddedAgentSDKError("Embedded-agent stream response did not include a readable body.", {
      kind: "protocol",
    });
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done }).replace(/\r\n/g, "\n").replace(/\r/g, "\n");

    let separatorIndex = buffer.indexOf("\n\n");
    while (separatorIndex !== -1) {
      const block = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      const payload = parseSSEBlock(block);
      if (payload) {
        const event = parseRuntimeEvent(payload);
        if (onEvent) {
          await onEvent(event);
        }
      }
      separatorIndex = buffer.indexOf("\n\n");
    }

    if (done) {
      break;
    }
  }

  const trailingPayload = parseSSEBlock(buffer.trim());
  if (trailingPayload) {
    const event = parseRuntimeEvent(trailingPayload);
    if (onEvent) {
      await onEvent(event);
    }
  }
}
