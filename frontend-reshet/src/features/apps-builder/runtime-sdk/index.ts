export type AppRuntimeInput = {
  input?: string;
  messages?: Array<{ role: string; content: string }>;
  chat_id?: string;
  context?: Record<string, unknown>;
};

export type AppRuntimeEvent = {
  type?: string;
  event?: string;
  data?: Record<string, unknown>;
  content?: string;
};
