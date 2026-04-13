import {
  UI_BLOCKS_OUTPUT_KIND,
  validateUIBlocksBundle,
} from "@agents24/ui-blocks-contract";
import type {
  AgentAttachmentDto,
  AgentThreadDetailDto,
  AgentThreadSummaryDto,
  StandaloneResponseBlock,
} from "./standalone-runtime";
import type {
  TemplateAttachment,
  TemplateMessage,
  TemplateRenderBlock,
  TemplateThread,
} from "./types";

const FALLBACK_PREVIEW = "Start a new conversation.";
const UI_BLOCKS_RENDERER_KIND = "ui_blocks";
const UI_BLOCKS_TOOL_SLUG = "builtin-ui-blocks";

export function createId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `id-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function titleFromPrompt(prompt: string) {
  const normalized = prompt.trim().replace(/\s+/g, " ");
  return normalized.slice(0, 48) || "New chat";
}

export function previewFromMessage(message: TemplateMessage) {
  if (message.role === "user") {
    if (message.text) return message.text;
    if (message.attachments?.length) {
      return `Attachments: ${message.attachments.map((item) => item.filename).join(", ")}`;
    }
    return "New message";
  }
  const firstText = message.blocks?.find((block) => block.kind === "text");
  return firstText?.kind === "text" ? firstText.content : "Assistant response";
}

export function mapRuntimeAttachment(
  attachment: AgentAttachmentDto,
  previewUrl?: string | null,
): TemplateAttachment {
  return {
    id: attachment.id,
    kind: attachment.kind,
    filename: attachment.filename,
    mimeType: attachment.mime_type,
    byteSize: attachment.byte_size,
    status: attachment.status,
    previewUrl: previewUrl || null,
  };
}

export function formatRelativeTimestamp(value: string | null): string {
  if (!value) return "Just now";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Just now";

  const deltaMs = Date.now() - parsed.getTime();
  const deltaMinutes = Math.max(1, Math.floor(deltaMs / 60000));
  if (deltaMinutes < 60) return `${deltaMinutes}m ago`;
  const deltaHours = Math.floor(deltaMinutes / 60);
  if (deltaHours < 24) return `${deltaHours}h ago`;
  const deltaDays = Math.floor(deltaHours / 24);
  return deltaDays === 1 ? "Yesterday" : `${deltaDays}d ago`;
}

export function mapThreadSummary(summary: AgentThreadSummaryDto): TemplateThread {
  return {
    id: summary.id,
    title: summary.title || "New chat",
    preview: FALLBACK_PREVIEW,
    updatedAt: formatRelativeTimestamp(summary.last_activity_at || summary.updated_at),
    messages: [],
    isLoaded: false,
    hasMoreHistory: false,
    nextBeforeTurnIndex: null,
    isLoadingOlderHistory: false,
  };
}

function assistantTextFromTurn(turn: AgentThreadDetailDto["turns"][number]): string {
  const responseBlocks = Array.isArray(turn.response_blocks) ? turn.response_blocks : [];
  const blockText = responseBlocks
    .filter((block) => block.kind === "assistant_text")
    .map((block) => String(block.text || ""))
    .join("")
    .trim();
  if (blockText) {
    return blockText;
  }
  if (turn.assistant_output_text) {
    return turn.assistant_output_text;
  }
  return "";
}

export function mapThreadDetail(detail: AgentThreadDetailDto): TemplateThread {
  const messages: TemplateMessage[] = [];

  for (const turn of detail.turns) {
    if (turn.user_input_text || (turn.attachments || []).length > 0) {
      messages.push({
        id: `${turn.id}-user`,
        role: "user",
        createdAt: turn.created_at,
        runStatus: "completed",
        text: turn.user_input_text || undefined,
        attachments: (turn.attachments || []).map((attachment) => mapRuntimeAttachment(attachment)),
      });
    }

    const assistantText = assistantTextFromTurn(turn);
    const blocks = mapCanonicalResponseBlocks(turn.response_blocks || [], assistantText);

    if (assistantText || blocks.length > 0) {
      messages.push({
        id: `${turn.id}-assistant`,
        role: "assistant",
        createdAt: turn.completed_at || turn.created_at,
        runStatus: turn.status === "failed" ? "error" : "completed",
        text: assistantText || undefined,
        blocks,
      });
    }
  }

  const latestMessage = messages[messages.length - 1];
  return {
    id: detail.id,
    title: detail.title || deriveThreadTitle(messages),
    preview: latestMessage ? previewFromMessage(latestMessage) : FALLBACK_PREVIEW,
    updatedAt: formatRelativeTimestamp(detail.last_activity_at || detail.updated_at),
    messages,
    isLoaded: true,
    hasMoreHistory: Boolean(detail.paging?.has_more),
    nextBeforeTurnIndex:
      detail.paging?.next_before_turn_index === null || detail.paging?.next_before_turn_index === undefined
        ? null
        : detail.paging.next_before_turn_index,
    isLoadingOlderHistory: false,
  };
}

function deriveThreadTitle(messages: TemplateMessage[]): string {
  const firstUserMessage = messages.find((message) => message.role === "user");
  if (!firstUserMessage) return "New chat";
  if (firstUserMessage.text) {
    return titleFromPrompt(firstUserMessage.text);
  }
  if (firstUserMessage.attachments?.[0]?.filename) {
    return titleFromPrompt(firstUserMessage.attachments[0].filename);
  }
  return "New chat";
}

function unwrapUIBlocksOutput(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const record = value as Record<string, unknown>;
  if (record.kind === UI_BLOCKS_OUTPUT_KIND && record.bundle && typeof record.bundle === "object") {
    return record;
  }
  if (record.body && typeof record.body === "object") {
    return unwrapUIBlocksOutput(record.body);
  }
  if (record.result && typeof record.result === "object") {
    return unwrapUIBlocksOutput(record.result);
  }
  if (record.context && typeof record.context === "object") {
    return unwrapUIBlocksOutput(record.context);
  }
  return null;
}

function isUIBlocksTool(tool: Record<string, unknown>): boolean {
  const rendererKind = String(tool.rendererKind || "").trim().toLowerCase();
  const toolSlug = String(tool.toolSlug || "").trim().toLowerCase();
  return rendererKind === UI_BLOCKS_RENDERER_KIND || toolSlug === UI_BLOCKS_TOOL_SLUG;
}

function extractUIBlocksToolResult(tool: Record<string, unknown>): { bundle: unknown } | null {
  const output = unwrapUIBlocksOutput(tool.output);
  if (!output) return null;
  return { bundle: output.bundle };
}

function blockTextContent(block: StandaloneResponseBlock): string {
  if (block.kind === "assistant_text") {
    return String(block.text || "");
  }
  if (block.kind === "approval_request" || block.kind === "error") {
    return String(block.text || "");
  }
  return "";
}

function normalizeTaskStatus(status: unknown): "running" | "done" | "error" {
  if (status === "running") return "running";
  if (status === "error") return "error";
  return "done";
}

export function mapCanonicalResponseBlocks(
  responseBlocks: StandaloneResponseBlock[] | undefined,
  fallbackText?: string,
): TemplateRenderBlock[] {
  const canonicalBlocks = Array.isArray(responseBlocks) ? responseBlocks : [];
  const mappedBlocks: TemplateRenderBlock[] = [];
  const reasoningSteps: string[] = [];

  for (const block of canonicalBlocks) {
    if (!block || typeof block !== "object") continue;

    if (block.kind === "assistant_text") {
      const content = blockTextContent(block);
      if (!content) continue;
      mappedBlocks.push({
        id: block.id,
        kind: "text",
        content,
      });
      continue;
    }

    if (block.kind === "reasoning_note") {
      const label = typeof block.label === "string" ? block.label.trim() : "";
      const description = typeof block.description === "string" ? block.description.trim() : "";
      const step = description || label;
      if (step) {
        reasoningSteps.push(step);
      }
      continue;
    }

    if (block.kind === "approval_request" || block.kind === "error") {
      const content = blockTextContent(block);
      if (!content) continue;
      mappedBlocks.push({
        id: block.id,
        kind: "text",
        content,
      });
      continue;
    }

    if (block.kind !== "tool_call") {
      continue;
    }

    const tool = block.tool && typeof block.tool === "object" ? (block.tool as Record<string, unknown>) : {};
    const uiBlocksResult = extractUIBlocksToolResult(tool);
    if (isUIBlocksTool(tool)) {
      if (block.status === "running") {
        mappedBlocks.push({
          id: block.id,
          kind: "ui_blocks_loading",
          spanId: typeof tool.toolCallId === "string" ? tool.toolCallId : undefined,
        });
        continue;
      }
      if (uiBlocksResult) {
        const parsed = validateUIBlocksBundle(uiBlocksResult.bundle);
        mappedBlocks.push(
          parsed.ok
            ? { id: block.id, kind: "ui_blocks_bundle", bundle: parsed.bundle }
            : { id: `${block.id}-invalid`, kind: "text", content: "Unable to render UI blocks bundle." },
        );
      }
      continue;
    }

    const items: string[] = [];
    const summary = typeof tool.summary === "string" ? tool.summary.trim() : "";
    const detail = typeof tool.detail === "string" ? tool.detail.trim() : "";
    if (summary) items.push(summary);
    if (detail && detail !== summary) items.push(detail);

    mappedBlocks.push({
      id: block.id,
      kind: "task",
      title:
        (typeof tool.title === "string" && tool.title.trim()) ||
        (typeof tool.displayName === "string" && tool.displayName.trim()) ||
        (typeof tool.toolName === "string" && tool.toolName.trim()) ||
        "Working...",
      spanId: typeof tool.toolCallId === "string" ? tool.toolCallId : undefined,
      status: normalizeTaskStatus(block.status),
      items,
    });
  }

  if (reasoningSteps.length > 0) {
    mappedBlocks.unshift({
      id: "reasoning",
      kind: "reasoning",
      title: "Reasoning",
      steps: reasoningSteps,
    });
  }

  if (!mappedBlocks.some((block) => block.kind === "text") && fallbackText?.trim()) {
    mappedBlocks.push({
      id: "assistant-fallback-text",
      kind: "text",
      content: fallbackText,
    });
  }

  return mappedBlocks;
}
