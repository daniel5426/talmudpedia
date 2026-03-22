import { EmbeddedAgentSDKError } from "@agents24/embed-sdk";

export function toEmbedErrorPayload(error: unknown) {
  if (error instanceof EmbeddedAgentSDKError) {
    return {
      error: error.message,
      kind: error.kind,
      status: error.status ?? 502,
      details: error.details ?? null,
    };
  }

  return {
    error: error instanceof Error ? error.message : "Unexpected server error",
    kind: "internal",
    status: 500,
    details: null,
  };
}
