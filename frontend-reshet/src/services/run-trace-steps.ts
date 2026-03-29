import { agentService, type AgentRunEventsResponse } from "@/services/agent";

export interface ExecutionStep {
  id: string;
  nodeId?: string;
  spanId?: string;
  name: string;
  type: string;
  status: "pending" | "running" | "completed" | "error";
  input?: unknown;
  output?: unknown;
  timestamp: Date;
}

type FetchRunEvents = (runId: string) => Promise<AgentRunEventsResponse>;

export interface LoadedRunTrace {
  response: AgentRunEventsResponse;
  steps: ExecutionStep[];
  serialized: string;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function toText(value: unknown): string {
  return typeof value === "string" ? value : String(value ?? "");
}

function toDate(value: unknown, fallbackIndex: number): Date {
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    if (!Number.isNaN(parsed)) return new Date(parsed);
  }
  return new Date(Date.UTC(1970, 0, 1, 0, 0, fallbackIndex));
}

function toSeq(rawEvent: Record<string, unknown>, fallback: number): number {
  const raw = rawEvent.seq ?? rawEvent.sequence;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function resolveEventPayload(
  rawEvent: Record<string, unknown>,
): Record<string, unknown> {
  const directPayload = asRecord(rawEvent.payload) || asRecord(rawEvent.data) || {};
  const nestedData = asRecord(directPayload.data);
  const eventName = toText(rawEvent.event || "");

  if (
    nestedData &&
    (eventName.startsWith("node_") ||
      eventName.startsWith("on_chain_") ||
      eventName.startsWith("orchestration."))
  ) {
    return nestedData;
  }

  return directPayload;
}

function resolveStepId(
  rawEvent: Record<string, unknown>,
  payload: Record<string, unknown>,
  fallback: string,
): string {
  const fromPayload = toText(payload.span_id || "").trim();
  if (fromPayload) return fromPayload;

  const fromEvent = toText(rawEvent.span_id || "").trim();
  if (fromEvent) return fromEvent;

  return fallback;
}

function resolveSpanId(
  rawEvent: Record<string, unknown>,
  payload: Record<string, unknown>,
): string | undefined {
  const payloadSpanId = toText(payload.span_id || "").trim();
  if (payloadSpanId) return payloadSpanId;
  const rawSpanId = toText(rawEvent.span_id || "").trim();
  return rawSpanId || undefined;
}

function resolveNodeId(
  rawEvent: Record<string, unknown>,
  payload: Record<string, unknown>,
  eventName: string,
): string | undefined {
  const payloadNodeId = toText(payload.node_id || payload.source_node_id || "").trim();
  if (payloadNodeId) return payloadNodeId;

  const spanId = resolveSpanId(rawEvent, payload);
  if (
    spanId &&
    (eventName.startsWith("node_") ||
      eventName.startsWith("on_chain_") ||
      eventName === "workflow.node_output_published" ||
      eventName === "workflow.end_materialized")
  ) {
    return spanId;
  }

  return undefined;
}

function resolveStartInput(
  rawEvent: Record<string, unknown>,
  payload: Record<string, unknown>,
): unknown {
  if (payload.input !== undefined) return payload.input;
  if (rawEvent.inputs !== undefined) return rawEvent.inputs;
  return undefined;
}

function resolveEndOutput(
  rawEvent: Record<string, unknown>,
  payload: Record<string, unknown>,
): unknown {
  if (payload.output !== undefined) return payload.output;
  if (rawEvent.outputs !== undefined) return rawEvent.outputs;
  return undefined;
}

function resolveErrorOutput(
  rawEvent: Record<string, unknown>,
  payload: Record<string, unknown>,
): unknown {
  if (payload.error !== undefined) return { error: payload.error };
  if (payload.output !== undefined) return payload.output;
  if (rawEvent.outputs !== undefined) return rawEvent.outputs;
  if (Object.keys(payload).length > 0) return payload;
  return { error: "Run failed" };
}

function resolveToolName(
  rawEvent: Record<string, unknown>,
  payload: Record<string, unknown>,
): string {
  return (
    toText(payload.display_name || "").trim() ||
    toText(payload.summary || "").trim() ||
    toText(payload.tool || "").trim() ||
    toText(rawEvent.name || "").trim() ||
    "Tool"
  );
}

function resolveNodeName(
  rawEvent: Record<string, unknown>,
  payload: Record<string, unknown>,
  eventName: string,
): string {
  return (
    toText(rawEvent.name || "").trim() ||
    toText(payload.name || "").trim() ||
    toText(payload.type || "").trim() ||
    eventName
  );
}

function updateExistingStepOutput(
  steps: ExecutionStep[],
  stepId: string,
  output: unknown,
  name?: string,
  nodeId?: string,
) {
  const index = steps.findIndex((step) => step.id === stepId)
  if (index === -1) return
  steps[index] = {
    ...steps[index],
    name: name || steps[index].name,
    nodeId: nodeId || steps[index].nodeId,
    output,
  }
}

function buildCompletedStep(
  rawEvent: Record<string, unknown>,
  payload: Record<string, unknown>,
  stepType: "tool" | "node",
  eventName: string,
  fallbackId: string,
  index: number,
): ExecutionStep {
  return {
    id: resolveStepId(rawEvent, payload, fallbackId),
    nodeId: stepType === "node" ? resolveNodeId(rawEvent, payload, eventName) : undefined,
    spanId: resolveSpanId(rawEvent, payload),
    name:
      stepType === "tool"
        ? resolveToolName(rawEvent, payload)
        : resolveNodeName(rawEvent, payload, eventName),
    type: stepType,
    status: "completed",
    output: resolveEndOutput(rawEvent, payload),
    timestamp: toDate(rawEvent.ts ?? rawEvent.timestamp, index),
  };
}

export function buildExecutionStepsFromRunEvents(
  rawEvents: Record<string, unknown>[],
): ExecutionStep[] {
  const normalized = [...rawEvents]
    .map((rawEvent, index) => ({
      rawEvent,
      index,
      seq: toSeq(rawEvent, index + 1),
      timestamp: toDate(rawEvent.ts ?? rawEvent.timestamp, index),
    }))
    .sort((left, right) => {
      if (left.seq !== right.seq) return left.seq - right.seq;
      const tsDiff = left.timestamp.getTime() - right.timestamp.getTime();
      if (tsDiff !== 0) return tsDiff;
      return left.index - right.index;
    });

  const steps: ExecutionStep[] = [];
  const activeStepIndexById = new Map<string, number>();

  normalized.forEach(({ rawEvent, index }) => {
    const eventName = toText(rawEvent.event || "").trim();
    const payload = resolveEventPayload(rawEvent);
    const fallbackId = `event:${index}:${eventName || "unknown"}`;
    const stepId = resolveStepId(rawEvent, payload, fallbackId);

    if (eventName === "on_tool_start" || eventName === "tool.started") {
      const step: ExecutionStep = {
        id: stepId,
        nodeId: resolveNodeId(rawEvent, payload, eventName),
        spanId: resolveSpanId(rawEvent, payload),
        name: resolveToolName(rawEvent, payload),
        type: "tool",
        status: "running",
        input: resolveStartInput(rawEvent, payload),
        timestamp: toDate(rawEvent.ts ?? rawEvent.timestamp, index),
      };
      activeStepIndexById.set(step.id, steps.push(step) - 1);
      return;
    }

    if (eventName === "on_tool_end" || eventName === "tool.completed") {
      const existingIndex = activeStepIndexById.get(stepId);
      if (existingIndex === undefined) {
        steps.push(buildCompletedStep(rawEvent, payload, "tool", eventName, fallbackId, index));
        return;
      }
      steps[existingIndex] = {
        ...steps[existingIndex],
        status: "completed",
        output: resolveEndOutput(rawEvent, payload),
      };
      activeStepIndexById.delete(stepId);
      return;
    }

    if (eventName === "tool.failed") {
      const existingIndex = activeStepIndexById.get(stepId);
      if (existingIndex === undefined) {
        steps.push({
          ...buildCompletedStep(rawEvent, payload, "tool", eventName, fallbackId, index),
          status: "error",
          output: resolveErrorOutput(rawEvent, payload),
        });
        return;
      }
      steps[existingIndex] = {
        ...steps[existingIndex],
        status: "error",
        output: resolveErrorOutput(rawEvent, payload),
      };
      activeStepIndexById.delete(stepId);
      return;
    }

    if (eventName === "node_start" || eventName === "on_chain_start") {
      const step: ExecutionStep = {
        id: stepId,
        nodeId: resolveNodeId(rawEvent, payload, eventName),
        spanId: resolveSpanId(rawEvent, payload),
        name: resolveNodeName(rawEvent, payload, eventName),
        type: "node",
        status: "running",
        input: resolveStartInput(rawEvent, payload),
        timestamp: toDate(rawEvent.ts ?? rawEvent.timestamp, index),
      };
      activeStepIndexById.set(step.id, steps.push(step) - 1);
      return;
    }

    if (eventName === "node_end" || eventName === "on_chain_end") {
      const existingIndex = activeStepIndexById.get(stepId);
      if (existingIndex === undefined) {
        steps.push(buildCompletedStep(rawEvent, payload, "node", eventName, fallbackId, index));
        return;
      }
      const existingOutput = steps[existingIndex]?.output;
      steps[existingIndex] = {
        ...steps[existingIndex],
        status: "completed",
        output: existingOutput !== undefined ? existingOutput : resolveEndOutput(rawEvent, payload),
      };
      activeStepIndexById.delete(stepId);
      return;
    }

    if (eventName === "workflow.node_output_published") {
      const publishedOutput = payload.published_output;
      if (publishedOutput !== undefined) {
        updateExistingStepOutput(
          steps,
          stepId,
          publishedOutput,
          toText(payload.node_name || "").trim() || undefined,
          resolveNodeId(rawEvent, payload, eventName),
        );
      }
      return;
    }

    if (eventName === "workflow.end_materialized") {
      if (payload.final_output !== undefined) {
        updateExistingStepOutput(
          steps,
          stepId,
          payload.final_output,
          toText(payload.node_name || "").trim() || undefined,
          resolveNodeId(rawEvent, payload, eventName),
        );
      }
      return;
    }

    if (eventName === "error" || eventName === "run.failed") {
      const existingIndex = activeStepIndexById.get(stepId);
      const fallbackIndex =
        existingIndex ??
        [...activeStepIndexById.values()].sort((left, right) => right - left)[0];
      if (fallbackIndex === undefined) return;
      steps[fallbackIndex] = {
        ...steps[fallbackIndex],
        status: "error",
        output: resolveErrorOutput(rawEvent, payload),
      };
      activeStepIndexById.delete(steps[fallbackIndex].id);
    }
  });

  return steps;
}

export function isExecutionTraceEvent(eventName: string): boolean {
  return new Set([
    "on_tool_start",
    "on_tool_end",
    "tool.started",
    "tool.completed",
    "tool.failed",
    "node_start",
    "node_end",
    "on_chain_start",
    "on_chain_end",
    "workflow.node_output_published",
    "workflow.end_materialized",
    "error",
    "run.failed",
  ]).has(String(eventName || "").trim());
}

export async function buildExecutionStepsFromRunTrace(
  runId: string,
  fetchRunEvents: FetchRunEvents = agentService.getRunEvents,
): Promise<ExecutionStep[] | undefined> {
  const loaded = await loadRunTraceInspection(runId, fetchRunEvents);
  return loaded?.steps.length ? loaded.steps : undefined;
}

export async function loadRunTraceInspection(
  runId: string,
  fetchRunEvents: FetchRunEvents = agentService.getRunEvents,
): Promise<LoadedRunTrace | undefined> {
  const normalizedRunId = String(runId || "").trim();
  if (!normalizedRunId) return undefined;

  const response = await fetchRunEvents(normalizedRunId);
  const rawEvents = Array.isArray(response.events) ? response.events : [];
  return {
    response,
    steps: buildExecutionStepsFromRunEvents(rawEvents),
    serialized: JSON.stringify(response, null, 2),
  };
}
