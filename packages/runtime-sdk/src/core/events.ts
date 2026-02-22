import type { NormalizedRuntimeEvent, RawRuntimeEvent } from "./types";

function asRecord(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  return value as Record<string, unknown>;
}

function asString(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

export function normalizeRuntimeEvent(raw: RawRuntimeEvent): NormalizedRuntimeEvent {
  const eventName = asString(raw.event);
  const eventType = asString(raw.type) || eventName || "unknown";
  const data = asRecord(raw.data);
  const payload = asRecord(raw.payload);

  const content =
    asString(raw.content) ||
    asString((data || {}).content) ||
    asString((payload || {}).content);

  return {
    type: eventType,
    event: eventName,
    data,
    payload,
    content,
    raw,
  };
}
