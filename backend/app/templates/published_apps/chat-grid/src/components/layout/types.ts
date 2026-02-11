export type ChatRole = "user" | "assistant";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
};

export type SourceItem = {
  id: string;
  title: string;
  category: string;
  preview: string;
  content: string;
};
