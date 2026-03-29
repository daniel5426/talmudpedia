import test from "node:test";
import assert from "node:assert/strict";

import { PricoToolError } from "./contracts.js";
import { renderPricoWidgetOutput } from "./widget-output-service.js";

test("renderPricoWidgetOutput normalizes a valid payload", async () => {
  const response = await renderPricoWidgetOutput({
    screen_title: "Client Activity",
    rows: [
      {
        widgets: [
          {
            kind: "note",
            id: "dq",
            span: 12,
            title: "Data quality",
            text: "Based on booked recent deals only",
          },
        ],
      },
    ],
  });

  assert.equal(response.kind, "prico_widget_bundle");
  assert.equal(response.contract_version, "v1");
  assert.equal(response.bundle.title, "Client Activity");
});

test("renderPricoWidgetOutput rejects invalid compare widgets with structured retryable error", async () => {
  await assert.rejects(
    () =>
      renderPricoWidgetOutput({
        rows: [
          {
            widgets: [
              {
                kind: "compare",
                id: "banks",
                span: 12,
                title: "Bank Deal Count",
              } as never,
            ],
          },
        ],
      } as never),
    (error: unknown) => {
      assert.ok(error instanceof PricoToolError);
      assert.equal(error.code, "INVALID_WIDGET_DSL");
      assert.equal(error.status, 400);
      assert.equal(error.details?.retryable, true);
      assert.match(String(error.details?.hint || ""), /compare/i);
      return true;
    },
  );
});
