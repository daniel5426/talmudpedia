import type { PricoWidgetOutputRequest, PricoWidgetOutputResponse } from "./contracts.js";
import { PricoToolError } from "./contracts.js";
import { validatePricoWidgetBundle } from "../../../src/features/prico-widgets/contract.js";

export async function renderPricoWidgetOutput(
  payload: PricoWidgetOutputRequest,
): Promise<PricoWidgetOutputResponse> {
  const rows = Array.isArray(payload.rows) ? payload.rows : [];
  if (rows.length === 0) {
    throw new PricoToolError(
      "INVALID_WIDGET_DSL",
      "At least one widget row is required.",
      400,
      {
        path: "rows",
        widget_id: null,
        widget_kind: null,
        hint: "Pass rows as a JSON array, and include at least one row with widgets.",
        retryable: true,
      },
    );
  }

  const validation = validatePricoWidgetBundle({
    title: String(payload.screen_title || "").trim() || undefined,
    subtitle: String(payload.screen_subtitle || "").trim() || undefined,
    rows,
  });

  if (!validation.ok) {
    throw new PricoToolError(
      "INVALID_WIDGET_DSL",
      validation.error,
      400,
      {
        ...validation.details,
        retryable: true,
      },
    );
  }

  return {
    kind: "prico_widget_bundle",
    contract_version: "v1",
    bundle: validation.bundle,
  };
}
