import {
  UI_BLOCKS_OUTPUT_KIND,
  validateUIBlocksBundle,
} from "@agents24/ui-blocks-contract";
import type {
  AgentAttachmentDto,
  AgentThreadDetailDto,
  AgentThreadSummaryDto,
  StandaloneRuntimeEvent,
} from "./standalone-runtime";
import type {
  TemplateAttachment,
  TemplateMessage,
  TemplateRenderBlock,
  TemplateTextBlock,
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

export function mapThreadDetail(detail: AgentThreadDetailDto): TemplateThread {
  const messages: TemplateMessage[] = [];
  for (const turn of detail.turns) {
    if (turn.user_input_text) {
      messages.push({
        id: `${turn.id}-user`,
        role: "user",
        createdAt: turn.created_at,
        runStatus: "completed",
        text: turn.user_input_text,
        attachments: (turn.attachments || []).map((attachment) => mapRuntimeAttachment(attachment)),
      });
    }
    if (turn.assistant_output_text) {
      let blocks: TemplateRenderBlock[] = [];
      for (const event of turn.run_events || []) {
        blocks = applyRuntimeEvent(blocks, event);
      }
      const textBlock: TemplateTextBlock = {
        id: `${turn.id}-assistant-text`,
        kind: "text",
        content: turn.assistant_output_text,
      };
      messages.push({
        id: `${turn.id}-assistant`,
        role: "assistant",
        createdAt: turn.completed_at || turn.created_at,
        runStatus: "completed",
        text: turn.assistant_output_text,
        blocks: [...blocks, textBlock],
      });
    } else if ((turn.run_events || []).length > 0) {
      let blocks: TemplateRenderBlock[] = [];
      for (const event of turn.run_events || []) {
        blocks = applyRuntimeEvent(blocks, event);
      }
      if (blocks.length > 0) {
        messages.push({
          id: `${turn.id}-assistant`,
          role: "assistant",
          createdAt: turn.completed_at || turn.created_at,
          runStatus: "completed",
          blocks,
        });
      }
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

export function applyRuntimeEvent(
  blocks: TemplateRenderBlock[],
  event: StandaloneRuntimeEvent,
): TemplateRenderBlock[] {
  const uiBlocksResult = extractUIBlocksToolResult(event);

  if (event.event === "assistant.delta") {
    const content = String(event.payload.content || "");
    const lastBlock = blocks[blocks.length - 1];
    if (lastBlock?.kind === "text") {
      return [
        ...blocks.slice(0, -1),
        {
          ...lastBlock,
          content: lastBlock.content + content,
        },
      ];
    }
    return [
      ...blocks,
      {
        id: createId(),
        kind: "text",
        content,
      },
    ];
  }

  if (event.event === "reasoning.update") {
    const content = String(event.payload.content || event.payload.text || "");
    const lastBlock = blocks[blocks.length - 1];
    if (lastBlock?.kind === "reasoning") {
      const nextSteps = content
        ? [...lastBlock.steps, content].filter(Boolean)
        : lastBlock.steps;
      return [
        ...blocks.slice(0, -1),
        {
          ...lastBlock,
          steps: nextSteps,
        },
      ];
    }
    return [
      ...blocks,
      {
        id: createId(),
        kind: "reasoning",
        title: "Reasoning",
        steps: content ? [content] : [],
      },
    ];
  }

  if (event.event === "tool.started") {
    if (isUIBlocksToolEvent(event)) {
      return [
        ...blocks,
        {
          id: createId(),
          kind: "ui_blocks_loading",
          spanId: typeof event.payload.span_id === "string" ? event.payload.span_id : undefined,
        },
      ];
    }
    return [
      ...blocks,
      {
        id: createId(),
        kind: "task",
        title: String(event.payload.display_name || event.payload.summary || event.payload.tool || "Working..."),
        spanId: typeof event.payload.span_id === "string" ? event.payload.span_id : undefined,
        status: "running",
        items: [],
      },
    ];
  }

  if (event.event === "tool.completed" || event.event === "tool.failed") {
    const uiBlocksLoadingIndex = [...blocks]
      .map((block, index) => ({ block, index }))
      .reverse()
      .find(({ block }) => {
        if (block.kind !== "ui_blocks_loading") {
          return false;
        }
        const spanId = typeof event.payload.span_id === "string" ? event.payload.span_id : null;
        if (!spanId) {
          return true;
        }
        return block.spanId === spanId;
      })?.index;

    if (event.event === "tool.completed" && uiBlocksResult) {
      const parsed = validateUIBlocksBundle(uiBlocksResult.bundle);
      const nextBlock = parsed.ok
        ? {
            id: createId(),
            kind: "ui_blocks_bundle" as const,
            bundle: parsed.bundle,
          }
        : {
            id: createId(),
            kind: "text" as const,
            content: "Unable to render UI blocks bundle.",
          };
      if (typeof uiBlocksLoadingIndex === "number") {
        return [
          ...blocks.slice(0, uiBlocksLoadingIndex),
          nextBlock,
          ...blocks.slice(uiBlocksLoadingIndex + 1),
        ];
      }
      return [...blocks, nextBlock];
    }

    if (event.event === "tool.failed" && typeof uiBlocksLoadingIndex === "number") {
      return blocks.filter((_, index) => index !== uiBlocksLoadingIndex);
    }
    const spanId = typeof event.payload.span_id === "string" ? event.payload.span_id : null;
    const taskIndex = [...blocks]
      .map((block, index) => ({ block, index }))
      .reverse()
      .find(({ block }) => {
        if (block.kind !== "task" || block.status !== "running") {
          return false;
        }
        if (!spanId) {
          return true;
        }
        return block.spanId === spanId;
      })?.index;
    if (typeof taskIndex !== "number") return blocks;
    const taskBlock = blocks[taskIndex];
    if (taskBlock.kind !== "task") return blocks;
    const summary = event.payload.summary;
    const error = event.payload.error;
    const items = [...taskBlock.items];
    if (typeof summary === "string" && summary.trim()) {
      items.push(summary);
    }
    if (typeof error === "string" && error.trim()) {
      items.push(error);
    }
    return [
      ...blocks.slice(0, taskIndex),
      {
        ...taskBlock,
        status: event.event === "tool.failed" ? "error" : "done",
        items,
      },
      ...blocks.slice(taskIndex + 1),
    ];
  }

  return blocks;
}

export function isUIBlocksToolEvent(event: StandaloneRuntimeEvent): boolean {
  const rendererKind = String(event.payload.renderer_kind || "").trim().toLowerCase();
  const toolSlug = String(event.payload.tool_slug || "").trim().toLowerCase();
  return rendererKind === UI_BLOCKS_RENDERER_KIND || toolSlug === UI_BLOCKS_TOOL_SLUG;
}

export const isWidgetToolEvent = isUIBlocksToolEvent;

type UIBlocksToolResult = {
  bundle: unknown;
};

function extractUIBlocksToolResult(event: StandaloneRuntimeEvent): UIBlocksToolResult | null {
  if (!isUIBlocksToolEvent(event)) {
    return null;
  }
  const output = unwrapUIBlocksOutput(event.payload.output);
  if (!output) {
    return null;
  }
  const bundle = output.bundle;
  if (!bundle || typeof bundle !== "object") {
    return null;
  }
  return {
    bundle,
  };
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
