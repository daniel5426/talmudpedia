import type { NormalizedRuntimeEvent, RawRuntimeEvent, RuntimeResponseBlock } from "./types";

function asRecord(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  return value as Record<string, unknown>;
}

function asString(value: unknown, trim: boolean = true): string | undefined {
  if (typeof value !== "string") return undefined;
  if (!trim) return value;
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function asResponseBlocks(value: unknown): RuntimeResponseBlock[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value.filter((item): item is RuntimeResponseBlock => Boolean(item && typeof item === "object"));
}

export function normalizeRuntimeEvent(raw: RawRuntimeEvent): NormalizedRuntimeEvent {
  if (String(raw.version || "") !== "run-stream.v2") {
    throw new Error("Runtime stream contract mismatch: expected run-stream.v2 event envelope.");
  }
  const eventName = asString(raw.event);
  const eventType = asString(raw.type) || eventName || "unknown";
  const data = asRecord(raw.data);
  const payload = asRecord(raw.payload);

  const content =
    asString(raw.content, false) ||
    asString((data || {}).content, false) ||
    asString((payload || {}).content, false);
  const responseBlocks = asResponseBlocks((payload || {}).response_blocks);
  const assistantOutputText =
    asString((payload || {}).assistant_output_text, false) ||
    asString((data || {}).assistant_output_text, false);

  return {
    type: eventType,
    event: eventName,
    data,
    payload,
    content,
    responseBlocks,
    assistantOutputText,
    raw,
  };
}
