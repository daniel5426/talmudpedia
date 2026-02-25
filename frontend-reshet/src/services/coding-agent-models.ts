export interface OpenCodeCodingModelOption {
  id: string;
  name: string;
  is_free: boolean;
}

export const OPENCODE_CODING_MODEL_AUTO_ID = "opencode/big-pickle";

const MODEL_OPTIONS: OpenCodeCodingModelOption[] = [
  { id: OPENCODE_CODING_MODEL_AUTO_ID, name: "Big Pickle", is_free: true },
  { id: "opencode/minimax-m2.5-free", name: "MiniMax M2.5 Free", is_free: true },
  { id: "opencode/minimax-m2.1-free", name: "MiniMax M2.1 Free", is_free: true },
  { id: "opencode/kimi-k2.5-free", name: "Kimi K2.5 Free", is_free: true },
  { id: "opencode/glm-5-free", name: "GLM 5 Free", is_free: true },
  { id: "opencode/trinity-large-preview-free", name: "Trinity Large Preview Free", is_free: true },
  { id: "opencode/gpt-5-nano", name: "GPT 5 Nano", is_free: true },
  { id: "opencode/claude-sonnet-4.5", name: "Claude Sonnet 4.5", is_free: false },
  { id: "opencode/claude-sonnet-4", name: "Claude Sonnet 4", is_free: false },
  { id: "opencode/gpt-5", name: "GPT 5", is_free: false },
  { id: "opencode/gpt-5-mini", name: "GPT 5 Mini", is_free: false },
  { id: "opencode/kimi-k2.5", name: "Kimi K2.5", is_free: false },
  { id: "opencode/kimi-k2", name: "Kimi K2", is_free: false },
  { id: "opencode/minimax-m2.5", name: "MiniMax M2.5", is_free: false },
  { id: "opencode/minimax-m2.1", name: "MiniMax M2.1", is_free: false },
  { id: "opencode/qwen-3-coder", name: "Qwen 3 Coder", is_free: false },
  { id: "opencode/glm-5", name: "GLM 5", is_free: false },
  { id: "opencode/trinity-large", name: "Trinity Large", is_free: false },
];

export const OPENCODE_CODING_MODELS: ReadonlyArray<OpenCodeCodingModelOption> = Object.freeze(
  MODEL_OPTIONS.map((item) => Object.freeze({ ...item })),
);

export function listOpenCodeCodingModels(): OpenCodeCodingModelOption[] {
  return MODEL_OPTIONS.map((item) => ({ ...item }));
}
