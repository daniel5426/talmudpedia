import type { NormalizedRuntimeEvent, RawRuntimeEvent } from "./types";

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

  return {
    type: eventType,
    event: eventName,
    data,
    payload,
    content,
    raw,
  };
}
