"use client";

import {
  extractToolDetailForEvent,
  extractToolPathForEvent,
  extractToolTitleForEvent,
  isExplorationToolName,
} from "@/features/apps-builder/workspace/chat/chat-model";

export type ChatRenderBlockKind =
  | "assistant_text"
  | "tool_call"
  | "ui_blocks"
  | "reasoning_note"
  | "approval_request"
  | "error"
  | "artifact"
  | "user_message";

export type ChatRenderBlockStatus =
  | "pending"
  | "running"
  | "streaming"
  | "complete"
  | "error";

export type ChatToolPresentation = {
  toolCallId?: string;
  toolName: string;
  builtinKey?: string;
  action?: string;
  displayName?: string;
  summary?: string;
  title: string;
  detail?: string | null;
  path?: string | null;
  threadId?: string | null;
  isExploration?: boolean;
  input?: unknown;
  output?: unknown;
};

type ChatRenderBlockBase = {
  id: string;
  kind: ChatRenderBlockKind;
  runId?: string | null;
  seq: number;
  status: ChatRenderBlockStatus;
  ts?: string;
  source?: {
    event?: string;
    stage?: string;
  };
};

export type ChatAssistantTextBlock = ChatRenderBlockBase & {
  kind: "assistant_text";
  text: string;
};

export type ChatToolCallBlock = ChatRenderBlockBase & {
  kind: "tool_call";
  tool: ChatToolPresentation;
};

export type ChatUIBlocksBlock = ChatRenderBlockBase & {
  kind: "ui_blocks";
  toolCallId?: string;
  contractVersion?: string;
  bundle?: Record<string, unknown>;
  error?: string | null;
};

export type ChatReasoningNoteBlock = ChatRenderBlockBase & {
  kind: "reasoning_note";
  label: string;
  description?: string;
  stepId?: string;
};

export type ChatApprovalRequestBlock = ChatRenderBlockBase & {
  kind: "approval_request";
  text: string;
};

export type ChatErrorBlock = ChatRenderBlockBase & {
  kind: "error";
  text: string;
};

export type ChatArtifactBlock = ChatRenderBlockBase & {
  kind: "artifact";
  text: string;
};

export type ChatUserMessageBlock = ChatRenderBlockBase & {
  kind: "user_message";
  text: string;
};

export type ChatRenderBlock =
  | ChatAssistantTextBlock
  | ChatToolCallBlock
  | ChatUIBlocksBlock
  | ChatReasoningNoteBlock
  | ChatApprovalRequestBlock
  | ChatErrorBlock
  | ChatArtifactBlock
  | ChatUserMessageBlock;

type RunStreamBase = {
  runId?: string;
  seq: number;
  ts?: string;
  sourceEvent?: string;
  stage?: string;
};

export type NormalizedRunStreamEvent =
  | (RunStreamBase & {
      kind: "token";
      content: string;
    })
  | (RunStreamBase & {
      kind: "tool_start";
      toolCallId?: string;
      toolName: string;
      input?: unknown;
      message?: string;
      builtinKey?: string;
      action?: string;
      displayName?: string;
      summary?: string;
    })
  | (RunStreamBase & {
      kind: "tool_end";
      toolCallId?: string;
      toolName: string;
      output?: unknown;
      builtinKey?: string;
      action?: string;
      displayName?: string;
      summary?: string;
    })
  | (RunStreamBase & {
      kind: "reasoning";
      step: string;
      stepId?: string;
      message?: string;
      status?: string;
    })
  | (RunStreamBase & {
      kind: "approval_request";
      text: string;
    })
  | (RunStreamBase & {
      kind: "error";
      error: string;
    })
  | (RunStreamBase & {
      kind: "other";
      data?: Record<string, unknown>;
    });

function completeStreamingAssistantTextBlocks(blocks: ChatRenderBlock[]): ChatRenderBlock[] {
  return blocks.map((block) =>
    block.kind === "assistant_text" && block.status === "streaming"
      ? { ...block, status: "complete" as const }
      : block,
  );
}

function toSafeSeq(value: unknown, fallback: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return parsed;
}

function toSafeText(value: unknown): string {
  return typeof value === "string" ? value : String(value ?? "");
}

function isProviderStructuredToolDeltaText(value: unknown): boolean {
  if (typeof value !== "string") return false;
  const trimmed = value.trim();
  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) return false;
  const normalized = trimmed.replace(/"/g, "'").replace(/\s+/g, " ");
  const structuredTypes = [
    "tool_use",
    "input_json_delta",
    "tool_call",
    "tool_call_chunk",
    "server_tool_call",
    "server_tool_call_chunk",
  ];
  return structuredTypes.some((type) => normalized.includes(`'type': '${type}'`));
}

function stripProviderStructuredToolDeltaText(value: string): string {
  if (!value) return "";

  const patterns = [
    /\{['"]id['"]:\s*['"][^'"]+['"],\s*['"]caller['"]:\s*\{[^{}]*\},\s*['"]input['"]:\s*\{[^{}]*\},\s*['"]name['"]:\s*['"][^'"]+['"],\s*['"]type['"]:\s*['"]tool_use['"],\s*['"]index['"]:\s*\d+\}/g,
    /\{['"]partial_json['"]:\s*.*?['"]type['"]:\s*['"]input_json_delta['"],\s*['"]index['"]:\s*\d+\}/g,
  ];

  let next = value;
  for (const pattern of patterns) {
    next = next.replace(pattern, "");
  }

  return next.replace(/\}\{/g, "").replace(/[ \t]{2,}/g, " ").trim();
}

function extractThreadIdFromRecord(record: Record<string, unknown>): string | null {
  const directKeys = ["thread_id", "threadId"];
  for (const key of directKeys) {
    const value = record[key];
    if (typeof value !== "string") continue;
    const trimmed = value.trim();
    if (trimmed) return trimmed;
  }
  return null;
}

function extractThreadIdFromValue(value: unknown): string | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;

  const record = value as Record<string, unknown>;
  const directMatch = extractThreadIdFromRecord(record);
  if (directMatch) return directMatch;

  const wrapperKeys = ["context", "output", "result", "data", "payload"];
  for (const key of wrapperKeys) {
    const nested = record[key];
    if (!nested || typeof nested !== "object" || Array.isArray(nested)) continue;
    const nestedMatch = extractThreadIdFromRecord(nested as Record<string, unknown>);
    if (nestedMatch) return nestedMatch;
  }

  return null;
}

function extractStructuredResponsePayloadText(content: string): string | null {
  const trimmed = stripProviderStructuredToolDeltaText(String(content || "").trim());
  if (!trimmed) return null;

  const raw = trimmed.startsWith("```")
    ? trimmed.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "")
    : trimmed;

  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return null;
    }

    if (typeof (parsed as { message?: unknown }).message === "string") {
      const direct = String((parsed as { message?: unknown }).message || "").trim();
      if (direct) return direct;
    }

    const nextActions = Array.isArray((parsed as { next_actions?: unknown[] }).next_actions)
      ? ((parsed as { next_actions?: unknown[] }).next_actions as Array<Record<string, unknown>>)
      : [];
    for (const action of nextActions) {
      if (String(action?.action_type || "").trim() !== "respond_to_user") continue;
      const payload = action?.payload;
      if (typeof payload === "string" && payload.trim()) {
        return payload.trim();
      }
      if (payload && typeof payload === "object") {
        const nestedMessage = String((payload as Record<string, unknown>).message || "").trim();
        if (nestedMessage) return nestedMessage;
        const nestedText = String((payload as Record<string, unknown>).text || "").trim();
        if (nestedText) return nestedText;
      }
    }
  } catch {
    return null;
  }

  return null;
}

export function extractStructuredAssistantText(content: string): string {
  const trimmed = stripProviderStructuredToolDeltaText(String(content || "").trim());
  if (!trimmed) return "";
  return extractStructuredResponsePayloadText(trimmed) || trimmed;
}

export function extractAssistantTextFromUnknown(value: unknown): string {
  if (typeof value === "string") {
    return extractStructuredAssistantText(value);
  }

  if (!value || typeof value !== "object") {
    return "";
  }

  const record = value as Record<string, unknown>;
  const directKeys = ["message", "response", "text", "content"];
  for (const key of directKeys) {
    if (typeof record[key] === "string" && String(record[key] || "").trim()) {
      return extractStructuredAssistantText(String(record[key]));
    }
  }

  const nestedKeys = ["payload", "data", "result", "output"];
  for (const key of nestedKeys) {
    const nestedText = extractAssistantTextFromUnknown(record[key]);
    if (nestedText) {
      return nestedText;
    }
  }

  try {
    return extractStructuredAssistantText(JSON.stringify(value));
  } catch {
    return "";
  }
}

export function createAssistantTextBlock(params: {
  id: string;
  text: string;
  runId?: string | null;
  seq?: number;
  status?: ChatRenderBlockStatus;
  ts?: string;
}): ChatAssistantTextBlock {
  return {
    id: params.id,
    kind: "assistant_text",
    runId: params.runId,
    seq: params.seq ?? Number.MAX_SAFE_INTEGER,
    status: params.status ?? "complete",
    text: params.text,
    ts: params.ts,
    source: { event: "assistant.text", stage: "assistant" },
  };
}

export function createApprovalRequestBlock(params: {
  id: string;
  text: string;
  runId?: string | null;
  seq?: number;
  ts?: string;
}): ChatApprovalRequestBlock {
  return {
    id: params.id,
    kind: "approval_request",
    runId: params.runId,
    seq: params.seq ?? Number.MAX_SAFE_INTEGER,
    status: "pending",
    text: params.text,
    ts: params.ts,
    source: { event: "approval.request", stage: "assistant" },
  };
}

export function blocksFromLegacyAssistantContent(params: {
  messageId: string;
  content: string;
  runId?: string | null;
}): ChatRenderBlock[] {
  const text = extractStructuredAssistantText(params.content);
  if (!text) return [];
  return [
    createAssistantTextBlock({
      id: `${params.messageId}:assistant-text`,
      text,
      runId: params.runId,
    }),
  ];
}

export function adaptRunStreamEvent(rawEvent: Record<string, unknown>, index: number): NormalizedRunStreamEvent {
  const fallbackSeq = index + 1;
  const eventData = rawEvent.data && typeof rawEvent.data === "object"
    ? (rawEvent.data as Record<string, unknown>)
    : {};
  const payload = rawEvent.payload && typeof rawEvent.payload === "object"
    ? (rawEvent.payload as Record<string, unknown>)
    : eventData;
  const base: RunStreamBase = {
    runId:
      typeof rawEvent.run_id === "string"
        ? rawEvent.run_id
        : typeof rawEvent.source_run_id === "string"
          ? rawEvent.source_run_id
          : undefined,
    seq: toSafeSeq(rawEvent.seq ?? rawEvent.sequence, fallbackSeq),
    ts:
      typeof rawEvent.ts === "string"
        ? rawEvent.ts
        : typeof rawEvent.timestamp === "string"
          ? rawEvent.timestamp
          : undefined,
    sourceEvent: typeof rawEvent.event === "string" ? rawEvent.event : undefined,
    stage: typeof rawEvent.stage === "string" ? rawEvent.stage : undefined,
  };

  const eventName = String(rawEvent.event || "");
  const diagnostics = Array.isArray(rawEvent.diagnostics)
    ? (rawEvent.diagnostics as Array<Record<string, unknown>>)
    : [];

  if (eventName === "assistant.delta") {
    const content = toSafeText(payload.content);
    if (isProviderStructuredToolDeltaText(content)) {
      return {
        ...base,
        kind: "other",
        data: payload,
      };
    }
    return {
      ...base,
      kind: "token",
      content,
    };
  }

  if (eventName === "tool.started") {
    return {
      ...base,
      kind: "tool_start",
      toolCallId: typeof payload.span_id === "string" ? payload.span_id : undefined,
      toolName: toSafeText(payload.tool) || "tool",
      input: payload.input,
      message: typeof payload.message === "string" ? payload.message : undefined,
      builtinKey: typeof payload.builtin_key === "string" ? payload.builtin_key : undefined,
      action: typeof payload.action === "string" ? payload.action : undefined,
      displayName: typeof payload.display_name === "string" ? payload.display_name : undefined,
      summary: typeof payload.summary === "string" ? payload.summary : undefined,
    };
  }

  if (eventName === "on_tool_start") {
    return {
      ...base,
      kind: "tool_start",
      toolCallId: typeof rawEvent.span_id === "string" ? rawEvent.span_id : undefined,
      toolName: toSafeText(rawEvent.name) || "tool",
      input: payload.input ?? rawEvent.inputs,
      message: typeof payload.message === "string" ? payload.message : undefined,
      builtinKey: typeof payload.builtin_key === "string" ? payload.builtin_key : undefined,
      action: typeof payload.action === "string" ? payload.action : undefined,
      displayName: typeof payload.display_name === "string" ? payload.display_name : undefined,
      summary: typeof payload.summary === "string" ? payload.summary : undefined,
    };
  }

  if (eventName === "tool.completed") {
    return {
      ...base,
      kind: "tool_end",
      toolCallId: typeof payload.span_id === "string" ? payload.span_id : undefined,
      toolName: toSafeText(payload.tool) || "tool",
      output: payload.output,
      builtinKey: typeof payload.builtin_key === "string" ? payload.builtin_key : undefined,
      action: typeof payload.action === "string" ? payload.action : undefined,
      displayName: typeof payload.display_name === "string" ? payload.display_name : undefined,
      summary: typeof payload.summary === "string" ? payload.summary : undefined,
    };
  }

  if (eventName === "on_tool_end") {
    return {
      ...base,
      kind: "tool_end",
      toolCallId: typeof rawEvent.span_id === "string" ? rawEvent.span_id : undefined,
      toolName: toSafeText(rawEvent.name) || "tool",
      output: payload.output ?? rawEvent.outputs,
      builtinKey: typeof payload.builtin_key === "string" ? payload.builtin_key : undefined,
      action: typeof payload.action === "string" ? payload.action : undefined,
      displayName: typeof payload.display_name === "string" ? payload.display_name : undefined,
      summary: typeof payload.summary === "string" ? payload.summary : undefined,
    };
  }

  if (eventName === "reasoning.update") {
    return {
      ...base,
      kind: "reasoning",
      step: toSafeText(payload.step) || "Reasoning",
      stepId: typeof payload.step_id === "string" ? payload.step_id : undefined,
      message: typeof payload.message === "string" ? payload.message : undefined,
      status: typeof payload.status === "string" ? payload.status : undefined,
    };
  }

  if (eventName === "approval.request" || eventName === "mcp.auth_required") {
    return {
      ...base,
      kind: "approval_request",
      text:
        toSafeText(payload.message) ||
        (eventName === "mcp.auth_required" ? "Connect your account to continue." : "Approval required."),
    };
  }

  if (eventName === "run.failed") {
    return {
      ...base,
      kind: "error",
      error:
        toSafeText(payload.error) ||
        toSafeText(diagnostics[0]?.message) ||
        "Agent error",
    };
  }

  return {
    ...base,
    kind: "other",
    data: payload,
  };
}

function buildToolBlockFromStart(event: Extract<NormalizedRunStreamEvent, { kind: "tool_start" }>): ChatToolCallBlock {
  const presentationPayload = {
    input: event.input,
    message: event.message,
    builtin_key: event.builtinKey,
    action: event.action,
    display_name: event.displayName,
    summary: event.summary,
  };
  const path = extractToolPathForEvent(event.toolName, presentationPayload);
  return {
    id: event.toolCallId || `tool:${event.seq}:${event.toolName}`,
    kind: "tool_call",
    runId: event.runId,
    seq: event.seq,
    status: "running",
    ts: event.ts,
    source: { event: event.sourceEvent, stage: event.stage },
    tool: {
      toolCallId: event.toolCallId,
      toolName: event.toolName,
      builtinKey: event.builtinKey,
      action: event.action,
      displayName: event.displayName,
      summary: event.summary,
      title: extractToolTitleForEvent(event.toolName, presentationPayload, "running", path),
      detail: extractToolDetailForEvent(event.toolName, presentationPayload),
      path,
      threadId: extractThreadIdFromValue(event.input),
      isExploration: isExplorationToolName(event.toolName),
      input: event.input,
    },
  };
}

function buildToolBlockFromEnd(
  event: Extract<NormalizedRunStreamEvent, { kind: "tool_end" }>,
  existing?: ChatToolCallBlock,
): ChatToolCallBlock {
  const presentationPayload = {
    input: existing?.tool.input,
    output: event.output,
    builtin_key: event.builtinKey,
    action: event.action,
    display_name: event.displayName,
    summary: event.summary,
  };
  const path =
    existing?.tool.path ||
    extractToolPathForEvent(event.toolName, presentationPayload);
  return {
    id: existing?.id || event.toolCallId || `tool:${event.seq}:${event.toolName}`,
    kind: "tool_call",
    runId: event.runId,
    seq: existing?.seq ?? event.seq,
    status: "complete",
    ts: event.ts,
    source: { event: event.sourceEvent, stage: event.stage },
    tool: {
      toolCallId: event.toolCallId || existing?.tool.toolCallId,
      toolName: event.toolName,
      builtinKey: event.builtinKey || existing?.tool.builtinKey,
      action: event.action || existing?.tool.action,
      displayName: event.displayName || existing?.tool.displayName,
      summary: event.summary || existing?.tool.summary,
      title: extractToolTitleForEvent(event.toolName, presentationPayload, "completed", path),
      detail:
        extractToolDetailForEvent(event.toolName, presentationPayload) ||
        existing?.tool.detail,
      path,
      threadId:
        extractThreadIdFromValue(event.output) ||
        extractThreadIdFromValue(existing?.tool.input) ||
        existing?.tool.threadId ||
        null,
      isExploration: isExplorationToolName(event.toolName),
      input: existing?.tool.input,
      output: event.output,
    },
  };
}

export function applyRunStreamEventToBlocks(
  blocks: ChatRenderBlock[],
  event: NormalizedRunStreamEvent,
): ChatRenderBlock[] {
  if (event.kind === "token") {
    const next = [...blocks];
    const lastBlock = next[next.length - 1];
    if (lastBlock?.kind === "assistant_text") {
      next[next.length - 1] = {
        ...lastBlock,
        status: "streaming",
        text: `${lastBlock.text}${event.content}`,
      };
      return next;
    }
    next.push({
      id: `assistant-text:${event.runId || "run"}:${event.seq}`,
      kind: "assistant_text",
      runId: event.runId,
      seq: event.seq,
      status: "streaming",
      text: event.content,
      ts: event.ts,
      source: { event: event.sourceEvent, stage: event.stage },
    });
    return next;
  }

  if (event.kind === "tool_start") {
    const next = completeStreamingAssistantTextBlocks(blocks);
    const toolBlock = buildToolBlockFromStart(event);
    const existingIndex = next.findIndex(
      (block) => block.kind === "tool_call" && block.id === toolBlock.id,
    );
    if (existingIndex >= 0) {
      next[existingIndex] = toolBlock;
      return next;
    }
    next.push(toolBlock);
    return next;
  }

  if (event.kind === "tool_end") {
    const next = completeStreamingAssistantTextBlocks(blocks);
    const existingIndex = next.findIndex(
      (block) => block.kind === "tool_call" && block.id === (event.toolCallId || ""),
    );
    const existing = existingIndex >= 0 ? (next[existingIndex] as ChatToolCallBlock) : undefined;
    const toolBlock = buildToolBlockFromEnd(event, existing);
    if (existingIndex >= 0) {
      next[existingIndex] = toolBlock;
      return next;
    }
    next.push(toolBlock);
    return next;
  }

  if (event.kind === "reasoning") {
    if (
      event.stepId &&
      blocks.some((block) => block.kind === "tool_call" && block.tool.toolCallId === event.stepId)
    ) {
      return blocks;
    }
    const next = completeStreamingAssistantTextBlocks(blocks);
    const existingIndex = event.stepId
      ? next.findIndex(
          (block) => block.kind === "reasoning_note" && block.stepId === event.stepId,
        )
      : -1;
    const nextBlock: ChatReasoningNoteBlock = {
      id: event.stepId || `reasoning:${event.seq}:${event.step}`,
      kind: "reasoning_note",
      runId: event.runId,
      seq: existingIndex >= 0 ? next[existingIndex].seq : event.seq,
      status:
        event.status === "active"
          ? "running"
          : event.status === "pending"
            ? "pending"
            : "complete",
      label: event.step,
      description: event.message,
      stepId: event.stepId,
      ts: event.ts,
      source: { event: event.sourceEvent, stage: event.stage },
    };
    if (existingIndex >= 0) {
      next[existingIndex] = nextBlock;
      return next;
    }
    next.push(nextBlock);
    return next;
  }

  if (event.kind === "approval_request") {
    const next = completeStreamingAssistantTextBlocks(blocks);
    next.push(
      createApprovalRequestBlock({
        id: `approval:${event.runId || "run"}:${event.seq}`,
        text: event.text,
        runId: event.runId,
        seq: event.seq,
        ts: event.ts,
      }),
    );
    return next;
  }

  if (event.kind === "error") {
    const next = completeStreamingAssistantTextBlocks(blocks);
    next.push({
      id: `error:${event.runId || "run"}:${event.seq}`,
      kind: "error",
      runId: event.runId,
      seq: event.seq,
      status: "error",
      text: event.error,
      ts: event.ts,
      source: { event: event.sourceEvent, stage: event.stage },
    });
    return next;
  }

  return blocks;
}

export function finalizeAssistantRenderBlocks(
  blocks: ChatRenderBlock[],
  finalContent: string,
  options?: {
    runId?: string | null;
    fallbackSeq?: number;
  },
): ChatRenderBlock[] {
  const parsedText = extractStructuredAssistantText(finalContent);
  const next: ChatRenderBlock[] = blocks.map((block) => {
    if (block.kind === "tool_call" && block.status === "running") {
      return { ...block, status: "complete" as const };
    }
    if (block.kind === "assistant_text") {
      return { ...block, status: "complete" as const };
    }
    if (block.kind === "reasoning_note" && block.status === "running") {
      return { ...block, status: "complete" as const };
    }
    return block;
  });

  if (!parsedText.trim()) {
    return next;
  }

  const assistantTextIndices = next
    .map((block, index) => ({ block, index }))
    .filter(({ block }) => block.kind === "assistant_text")
    .map(({ index }) => index);

  if (assistantTextIndices.length === 0) {
    next.push(
      createAssistantTextBlock({
        id: `assistant-text:${options?.runId || "run"}:${options?.fallbackSeq ?? next.length + 1}`,
        text: parsedText,
        runId: options?.runId,
        seq: options?.fallbackSeq ?? next.length + 1,
        status: "complete",
      }),
    );
    return next;
  }

  const concatenatedText = assistantTextIndices
    .map((index) => (next[index] as ChatAssistantTextBlock).text)
    .join("");
  if (concatenatedText.trim() === parsedText.trim()) {
    return next;
  }

  const structuredOverrideText = extractStructuredResponsePayloadText(finalContent);

  if (assistantTextIndices.length === 1) {
    if (!structuredOverrideText) {
      return next;
    }
    const assistantTextIndex = assistantTextIndices[0];
    const current = next[assistantTextIndex] as ChatAssistantTextBlock;
    next[assistantTextIndex] = {
      ...current,
      text: structuredOverrideText,
      status: "complete",
    };
    return next;
  }

  if (next.some((block) => block.kind !== "assistant_text")) {
    return next;
  }

  const keepIndex = assistantTextIndices[0];
  next[keepIndex] = {
    ...(next[keepIndex] as ChatAssistantTextBlock),
    text: parsedText,
    status: "complete",
  };

  return next.filter(
    (block, index) => block.kind !== "assistant_text" || index === keepIndex,
  );
}

export function extractAssistantTextFromBlocks(
  blocks: ChatRenderBlock[],
): string {
  return blocks
    .filter((block): block is ChatAssistantTextBlock => block.kind === "assistant_text")
    .map((block) => block.text)
    .join("")
    .trim();
}

export function sortChatRenderBlocks(blocks: ChatRenderBlock[]): ChatRenderBlock[] {
  return [...blocks].sort((left, right) => {
    if (left.seq !== right.seq) return left.seq - right.seq;
    return left.id.localeCompare(right.id);
  });
}
