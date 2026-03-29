export interface ContextStatusUsage {
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
  cached_input_tokens?: number | null;
  cached_output_tokens?: number | null;
  reasoning_tokens?: number | null;
}

export interface ContextStatus {
  model_id?: string | null;
  max_tokens?: number | null;
  max_tokens_source?: string | null;
  reserved_output_tokens?: number | null;
  estimated_input_tokens?: number | null;
  estimated_total_tokens?: number | null;
  estimated_remaining_tokens?: number | null;
  estimated_usage_ratio?: number | null;
  near_limit: boolean;
  compaction_recommended: boolean;
  source: "estimated_pre_run" | "estimated_in_flight" | "estimated_plus_actual";
  actual_usage?: ContextStatusUsage | null;
}

const SOURCE_PRIORITY: Record<ContextStatus["source"], number> = {
  estimated_pre_run: 1,
  estimated_in_flight: 2,
  estimated_plus_actual: 3,
};

function numericOrNull(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function statusWeight(status: ContextStatus | null | undefined): [number, number, number] {
  if (!status) {
    return [0, 0, 0];
  }
  return [
    SOURCE_PRIORITY[status.source] || 0,
    numericOrNull(status.actual_usage?.total_tokens) || 0,
    numericOrNull(status.estimated_total_tokens) || 0,
  ];
}

export function mergeContextStatus(
  current: ContextStatus | null | undefined,
  incoming: ContextStatus | null | undefined,
): ContextStatus | null {
  const normalizedCurrent = current || null;
  const normalizedIncoming = incoming || null;
  if (!normalizedIncoming) {
    return normalizedCurrent;
  }
  if (!normalizedCurrent) {
    return normalizedIncoming;
  }

  const currentWeight = statusWeight(normalizedCurrent);
  const incomingWeight = statusWeight(normalizedIncoming);
  if (
    incomingWeight[0] > currentWeight[0]
    || (incomingWeight[0] === currentWeight[0] && incomingWeight[1] > currentWeight[1])
    || (
      incomingWeight[0] === currentWeight[0]
      && incomingWeight[1] === currentWeight[1]
      && incomingWeight[2] >= currentWeight[2]
    )
  ) {
    return normalizedIncoming;
  }
  return normalizedCurrent;
}
