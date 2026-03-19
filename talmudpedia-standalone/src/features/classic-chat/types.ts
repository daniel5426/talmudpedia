export type TemplateTaskStatus = "running" | "done" | "error";

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

export type TemplateUiBlock = {
  id: string;
  kind: "ui";
  format: "openui";
  content: string;
  componentLibraryId?: string | null;
  surface?: string | null;
  ast?: Record<string, unknown> | null;
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
  | TemplateUiBlock
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
