export type TemplateTaskStatus = "running" | "done" | "error";
export type TemplateWidgetType =
  | "stat"
  | "table"
  | "bar_chart"
  | "line_chart"
  | "pie_chart"
  | "unknown";
export type TemplateWidgetValueFormat = "number" | "currency" | "percent";

export type ComposerAttachmentInput = {
  filename: string;
  mediaType: string;
  url: string;
};

export type ComposerSubmitPayload = {
  text: string;
  files: ComposerAttachmentInput[];
};

export type TemplateAttachment = {
  id: string;
  kind: "image" | "document" | "audio";
  filename: string;
  mimeType: string;
  byteSize: number;
  status: string;
  previewUrl?: string | null;
};

export type TemplateTextBlock = {
  id: string;
  kind: "text";
  content: string;
};

export type TemplateReasoningBlock = {
  id: string;
  kind: "reasoning";
  title: string;
  steps: string[];
};

export type TemplateTaskBlock = {
  id: string;
  kind: "task";
  title: string;
  status: TemplateTaskStatus;
  spanId?: string;
  items: string[];
  files?: string[];
};

export type TemplateSource = {
  id: string;
  label: string;
  href: string;
};

export type TemplateStatWidgetSpec = {
  value: string | number;
  label?: string;
  format?: TemplateWidgetValueFormat;
  trend?: {
    value: number;
    direction: "up" | "down" | "flat";
  };
};

export type TemplateTableWidgetSpec = {
  columns: Array<{ key: string; label: string }>;
  rows: Array<Record<string, unknown>>;
};

export type TemplateCartesianChartWidgetSpec = {
  data: Array<Record<string, unknown>>;
  xKey: string;
  yKey: string;
  seriesLabel?: string;
  format?: TemplateWidgetValueFormat;
};

export type TemplatePieChartWidgetSpec = {
  data: Array<Record<string, unknown>>;
  labelKey: string;
  valueKey: string;
  format?: TemplateWidgetValueFormat;
};

export type TemplateWidgetSpec =
  | TemplateStatWidgetSpec
  | TemplateTableWidgetSpec
  | TemplateCartesianChartWidgetSpec
  | TemplatePieChartWidgetSpec
  | Record<string, unknown>;

export type TemplateWidgetBlock = {
  id: string;
  kind: "widget";
  widgetType: TemplateWidgetType;
  title?: string;
  subtitle?: string;
  spec: TemplateWidgetSpec;
  version: 1;
};

export type TemplateSourcesBlock = {
  id: string;
  kind: "sources";
  title: string;
  sources: TemplateSource[];
};

export type TemplateRenderBlock =
  | TemplateTextBlock
  | TemplateReasoningBlock
  | TemplateTaskBlock
  | TemplateWidgetBlock
  | TemplateSourcesBlock;

export type TemplateMessage = {
  id: string;
  role: "user" | "assistant";
  createdAt: string;
  runStatus?: "pending" | "streaming" | "completed" | "error";
  text?: string;
  blocks?: TemplateRenderBlock[];
  attachments?: TemplateAttachment[];
};

export type TemplateThread = {
  id: string;
  title: string;
  preview: string;
  updatedAt: string;
  messages: TemplateMessage[];
  isLoaded?: boolean;
};
