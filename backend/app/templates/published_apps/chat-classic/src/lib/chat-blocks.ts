export type ToolBlockStatus = "running" | "completed" | "error" | "streaming";

export type ChatToolCallBlock = {
  kind: "tool_call";
  id: string;
  status: ToolBlockStatus;
  tool: {
    toolName: string;
    title: string;
    displayName?: string;
    path?: string;
    detail?: string;
    summary?: string;
  };
};

export type ChatAssistantTextBlock = {
  kind: "assistant_text";
  id: string;
  text: string;
};

export type ChatReasoningNoteBlock = {
  kind: "reasoning_note";
  id: string;
  label: string;
  description?: string;
  status: ToolBlockStatus;
};

export type ChatErrorBlock = {
  kind: "error";
  id: string;
  text: string;
};

export type ChatRenderBlock =
  | ChatToolCallBlock
  | ChatAssistantTextBlock
  | ChatReasoningNoteBlock
  | ChatErrorBlock;
