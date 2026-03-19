import type {
  AgentAttachmentDto,
  AgentThreadDetailDto,
  AgentThreadSummaryDto,
  StandaloneRuntimeEvent,
} from "./standalone-runtime";
import type {
  TemplateAttachment,
  TemplateCartesianChartWidgetSpec,
  TemplateMessage,
  TemplatePieChartWidgetSpec,
  TemplateRenderBlock,
  TemplateStatWidgetSpec,
  TemplateTableWidgetSpec,
  TemplateTextBlock,
  TemplateThread,
  TemplateWidgetBlock,
  TemplateWidgetType,
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
        spanId: typeof event.payload.span_id === "string" ? event.payload.span_id : undefined,
        status: "running",
        items: [],
      },
    ];
  }

  if (event.event === "tool.completed" || event.event === "tool.failed") {
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

  if (event.event === "assistant.widget") {
    const widgetBlock = parseWidgetBlock(event.payload);
    if (!widgetBlock) {
      return blocks;
    }
    return [
      ...blocks,
      {
        id: createId(),
        kind: "widget",
        widgetType: widgetBlock.widgetType,
        title: widgetBlock.title,
        subtitle: widgetBlock.subtitle,
        spec: widgetBlock.spec,
        version: widgetBlock.version,
      },
    ];
  }

  return blocks;
}

function parseWidgetBlock(payload: Record<string, unknown>): Omit<TemplateWidgetBlock, "id" | "kind"> | null {
  const widgetType = typeof payload.widget_type === "string" ? payload.widget_type : null;
  const rawSpec = payload.spec;
  if (!widgetType || !rawSpec || typeof rawSpec !== "object") {
    return null;
  }

  if (widgetType === "stat") {
    const spec = rawSpec as TemplateStatWidgetSpec;
    if (typeof spec.value !== "string" && typeof spec.value !== "number") {
      return null;
    }
    return {
      widgetType,
      title: typeof payload.title === "string" ? payload.title : undefined,
      subtitle: typeof payload.subtitle === "string" ? payload.subtitle : undefined,
      spec,
      version: 1,
    };
  }

  if (widgetType === "table") {
    const spec = rawSpec as TemplateTableWidgetSpec;
    if (!Array.isArray(spec.columns) || !Array.isArray(spec.rows)) {
      return null;
    }
    return {
      widgetType,
      title: typeof payload.title === "string" ? payload.title : undefined,
      subtitle: typeof payload.subtitle === "string" ? payload.subtitle : undefined,
      spec,
      version: 1,
    };
  }

  if (widgetType === "bar_chart" || widgetType === "line_chart") {
    const spec = rawSpec as TemplateCartesianChartWidgetSpec;
    if (!Array.isArray(spec.data) || typeof spec.xKey !== "string" || typeof spec.yKey !== "string") {
      return null;
    }
    return {
      widgetType: widgetType as Extract<TemplateWidgetType, "bar_chart" | "line_chart">,
      title: typeof payload.title === "string" ? payload.title : undefined,
      subtitle: typeof payload.subtitle === "string" ? payload.subtitle : undefined,
      spec,
      version: 1,
    };
  }

  if (widgetType === "pie_chart") {
    const spec = rawSpec as TemplatePieChartWidgetSpec;
    if (!Array.isArray(spec.data) || typeof spec.labelKey !== "string" || typeof spec.valueKey !== "string") {
      return null;
    }
    return {
      widgetType,
      title: typeof payload.title === "string" ? payload.title : undefined,
      subtitle: typeof payload.subtitle === "string" ? payload.subtitle : undefined,
      spec,
      version: 1,
    };
  }

  return {
    widgetType: "unknown",
    title: typeof payload.title === "string" ? payload.title : undefined,
    subtitle: typeof payload.subtitle === "string" ? payload.subtitle : undefined,
    spec: rawSpec as Record<string, unknown>,
    version: 1,
  };
}
