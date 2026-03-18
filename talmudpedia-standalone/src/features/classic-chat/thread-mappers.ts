import type {
  AgentThreadDetailDto,
  AgentThreadSummaryDto,
  StandaloneRuntimeEvent,
} from "./standalone-runtime";
import type {
  TemplateMessage,
  TemplateRenderBlock,
  TemplateTextBlock,
  TemplateThread,
} from "./types";

const FALLBACK_PREVIEW = "Start a new conversation.";

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
  if (message.role === "user") return message.text || "New message";
  const firstText = message.blocks?.find((block) => block.kind === "text");
  return firstText?.kind === "text" ? firstText.content : "Assistant response";
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
      });
    }
    if (turn.assistant_output_text) {
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
        blocks: [textBlock],
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
  };
}

function deriveThreadTitle(messages: TemplateMessage[]): string {
  const firstUserMessage = messages.find((message) => message.role === "user" && message.text);
  return firstUserMessage?.text ? titleFromPrompt(firstUserMessage.text) : "New chat";
}

export function applyRuntimeEvent(
  blocks: TemplateRenderBlock[],
  event: StandaloneRuntimeEvent,
): TemplateRenderBlock[] {
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
    return [
      ...blocks,
      {
        id: createId(),
        kind: "task",
        title: String(event.payload.display_name || event.payload.summary || event.payload.tool || "Working..."),
        status: "running",
        items: [],
      },
    ];
  }

  if (event.event === "tool.completed" || event.event === "tool.failed") {
    const lastBlock = blocks[blocks.length - 1];
    if (lastBlock?.kind !== "task") return blocks;
    const summary = event.payload.summary;
    const error = event.payload.error;
    const items = [...lastBlock.items];
    if (typeof summary === "string" && summary.trim()) {
      items.push(summary);
    }
    if (typeof error === "string" && error.trim()) {
      items.push(error);
    }
    return [
      ...blocks.slice(0, -1),
      {
        ...lastBlock,
        status: event.event === "tool.failed" ? "error" : "done",
        items,
      },
    ];
  }

  return blocks;
}
