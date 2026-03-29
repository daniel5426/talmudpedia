export interface ContextWindow {
  source: "exact" | "estimated" | "unknown";
  model_id?: string | null;
  max_tokens?: number | null;
  max_tokens_source?: string | null;
  input_tokens?: number | null;
  remaining_tokens?: number | null;
  usage_ratio?: number | null;
}

const SOURCE_PRIORITY: Record<ContextWindow["source"], number> = {
  unknown: 0,
  estimated: 1,
  exact: 2,
};

function numericOrNull(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function windowWeight(window: ContextWindow | null | undefined): [number, number] {
  if (!window) {
    return [0, 0];
  }
  return [
    SOURCE_PRIORITY[window.source] || 0,
    numericOrNull(window.input_tokens) || 0,
  ];
}

export function mergeContextWindow(
  current: ContextWindow | null | undefined,
  incoming: ContextWindow | null | undefined,
): ContextWindow | null {
  const normalizedCurrent = current || null;
  const normalizedIncoming = incoming || null;
  if (!normalizedIncoming) {
    return normalizedCurrent;
  }
  if (!normalizedCurrent) {
    return normalizedIncoming;
  }

  const currentWeight = windowWeight(normalizedCurrent);
  const incomingWeight = windowWeight(normalizedIncoming);
  if (
    incomingWeight[0] > currentWeight[0]
    || (incomingWeight[0] === currentWeight[0] && incomingWeight[1] >= currentWeight[1])
  ) {
    return normalizedIncoming;
  }
  return normalizedCurrent;
}
