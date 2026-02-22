import type { RawRuntimeEvent } from "./types";

const EVENT_SPLIT_RE = /\r?\n\r?\n/;

function parseEventBlock(block: string): RawRuntimeEvent | null {
  if (!block.trim()) return null;

  const lines = block.split(/\r?\n/);
  const dataLines: string[] = [];

  for (const line of lines) {
    if (!line) continue;
    if (line.startsWith(":")) continue;
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (!dataLines.length) return null;

  const payload = dataLines.join("\n");
  try {
    const parsed = JSON.parse(payload);
    if (parsed && typeof parsed === "object") {
      return parsed as RawRuntimeEvent;
    }
    return null;
  } catch {
    return null;
  }
}

export async function parseSseStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: RawRuntimeEvent) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    while (true) {
      const match = EVENT_SPLIT_RE.exec(buffer);
      if (!match || match.index < 0) break;
      const chunk = buffer.slice(0, match.index);
      buffer = buffer.slice(match.index + match[0].length);
      const event = parseEventBlock(chunk);
      if (event) {
        onEvent(event);
      }
    }
  }

  if (buffer.trim()) {
    const trailing = parseEventBlock(buffer);
    if (trailing) {
      onEvent(trailing);
    }
  }
}
