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
    { key: "local", label: "Local" },
    { key: "custom", label: "Custom" },
  ],
  completion: [
    { key: "openai", label: "OpenAI" },
    { key: "anthropic", label: "Anthropic" },
    { key: "google", label: "Google AI" },
    { key: "xai", label: "xAI" },
    { key: "local", label: "Local" },
    { key: "custom", label: "Custom" },
  ],
  embedding: [
    { key: "openai", label: "OpenAI" },
    { key: "local", label: "Local" },
    { key: "custom", label: "Custom" },
  ],
  vision: [
    { key: "openai", label: "OpenAI" },
    { key: "anthropic", label: "Anthropic" },
    { key: "google", label: "Google AI" },
    { key: "xai", label: "xAI" },
    { key: "local", label: "Local" },
    { key: "custom", label: "Custom" },
  ],
  image: [
    { key: "local", label: "Local" },
    { key: "custom", label: "Custom" },
  ],
  audio: [
    { key: "local", label: "Local" },
    { key: "custom", label: "Custom" },
  ],
  rerank: [
    { key: "local", label: "Local" },
    { key: "custom", label: "Custom" },
  ],
  speech_to_text: [
    { key: "google", label: "Google AI" },
  ],
  text_to_speech: [
    { key: "local", label: "Local" },
    { key: "custom", label: "Custom" },
  ],
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

export function isTenantManagedPricingProvider(provider: ModelProviderType): boolean {
  return provider === "local" || provider === "custom";
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
