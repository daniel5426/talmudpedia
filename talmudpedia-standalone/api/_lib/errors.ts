import { EmbeddedAgentSDKError } from "@agents24/embed-sdk";

import { PricoToolError } from "../../server/prico-demo/contracts.js";

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

export function toPricoErrorPayload(error: unknown) {
  if (error instanceof PricoToolError) {
    return {
      error: error.message,
      code: error.code,
      status: error.status,
      details: error.details,
    };
  }

  return {
    error: error instanceof Error ? error.message : "Unexpected PRICO demo server error.",
    code: "INTERNAL_ERROR",
    status: 500,
    details: null,
  };
}
