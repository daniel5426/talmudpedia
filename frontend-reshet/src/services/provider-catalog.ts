import { ModelCapabilityType, ModelProviderType } from "./agent";

export interface ProviderOption {
  key: string;
  label: string;
}

type LLMProviderOption = { key: ModelProviderType; label: string };

const MODEL_PROVIDER_OPTIONS_BY_CAPABILITY: Record<ModelCapabilityType, LLMProviderOption[]> = {
  chat: [
    { key: "openai", label: "OpenAI" },
    { key: "anthropic", label: "Anthropic" },
    { key: "google", label: "Google AI" },
    { key: "xai", label: "xAI" },
  ],
  completion: [
    { key: "openai", label: "OpenAI" },
    { key: "anthropic", label: "Anthropic" },
    { key: "google", label: "Google AI" },
    { key: "xai", label: "xAI" },
  ],
  embedding: [{ key: "openai", label: "OpenAI" }],
  vision: [
    { key: "openai", label: "OpenAI" },
    { key: "anthropic", label: "Anthropic" },
    { key: "google", label: "Google AI" },
    { key: "xai", label: "xAI" },
  ],
  image: [],
  audio: [],
  rerank: [],
  speech_to_text: [],
  text_to_speech: [],
};

export const LLM_PROVIDER_OPTIONS: LLMProviderOption[] = Array.from(
  new Map(
    Object.values(MODEL_PROVIDER_OPTIONS_BY_CAPABILITY)
      .flat()
      .map((option) => [option.key, option])
  ).values()
);

export function getModelProviderOptions(
  capability: ModelCapabilityType
): LLMProviderOption[] {
  return MODEL_PROVIDER_OPTIONS_BY_CAPABILITY[capability] || [];
}

export const VECTOR_STORE_PROVIDER_OPTIONS: ProviderOption[] = [
  { key: "pinecone", label: "Pinecone" },
  { key: "qdrant", label: "Qdrant" },
  { key: "pgvector", label: "PGVector" },
];

export const TOOL_PROVIDER_OPTIONS: ProviderOption[] = [
  { key: "serper", label: "Serper" },
  { key: "tavily", label: "Tavily" },
  { key: "exa", label: "Exa" },
];
