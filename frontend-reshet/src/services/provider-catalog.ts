import { ModelProviderType } from "./agent";

export interface ProviderOption {
  key: string;
  label: string;
}

export const LLM_PROVIDER_OPTIONS: Array<{ key: ModelProviderType; label: string }> = [
  { key: "openai", label: "OpenAI" },
  { key: "azure", label: "Azure OpenAI" },
  { key: "anthropic", label: "Anthropic" },
  { key: "google", label: "Google AI" },
  { key: "xai", label: "xAI" },
  { key: "gemini", label: "Google Gemini" },
  { key: "cohere", label: "Cohere" },
  { key: "groq", label: "Groq" },
  { key: "mistral", label: "Mistral" },
  { key: "together", label: "Together AI" },
  { key: "huggingface", label: "HuggingFace" },
  { key: "local", label: "Local" },
  { key: "custom", label: "Custom" },
];

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
