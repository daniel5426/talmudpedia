import { PricoToolError } from "../../server/prico-demo/contracts.js";

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
