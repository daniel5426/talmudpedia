import type { UIBlocksBundle } from "@agents24/ui-blocks-contract";

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

export type TemplateSourcesBlock = {
  id: string;
  kind: "sources";
  title: string;
  sources: TemplateSource[];
};

export type TemplateUIBlocksBundleBlock = {
  id: string;
  kind: "ui_blocks_bundle";
  bundle: UIBlocksBundle;
};

export type TemplateUIBlocksLoadingBlock = {
  id: string;
  kind: "ui_blocks_loading";
  spanId?: string;
};

export type TemplateRenderBlock =
  | TemplateTextBlock
  | TemplateReasoningBlock
  | TemplateTaskBlock
  | TemplateSourcesBlock
  | TemplateUIBlocksBundleBlock
  | TemplateUIBlocksLoadingBlock;

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
  hasMoreHistory?: boolean;
  nextBeforeTurnIndex?: number | null;
  isLoadingOlderHistory?: boolean;
};
